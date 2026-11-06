"""SDK adapter and deterministic demo. All units on the wire are SI.

One worker owns the SDK. HTTP threads only read complete JSON-safe snapshots.
Unavailable telemetry stays null; live never silently falls back to demo.
"""
import copy
from .buttonbox import ButtonBox, read_states
import queue
from .pit import commands, read_pit, validate_compound, read_compounds
from .track import TrackRecorder, MapStore, data_directory
from .race import RaceState
from .records import LapRecords, FuelRecords
from .coaching import CoachingRecorder, ReferenceStore, sector_layout
import math
import platform
import re
import threading
import time
import json
from functools import lru_cache
from pathlib import Path
from collections import deque


def number(value, default=None):
    return value if type(value) in (int, float) and math.isfinite(value) else default


def quantity(value, multiplier=1):
    if isinstance(value, str):
        match = re.match(r'^\s*([\d.+-]+)', value)
        try:
            parsed = number(float(match[1])) if match else None
        except ValueError:
            parsed = None
        return parsed * multiplier if parsed is not None else None
    value = number(value)
    return value * multiplier if value is not None else None


def json_safe(value):
    if isinstance(value, dict):
        return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if type(value) is float:
        return value if math.isfinite(value) else None
    return value if value is None or isinstance(value, (str,int,bool)) else None


SYSTEM_LABELS = {
    'dcBrakeBias':('Brake bias','bias','%'), 'dcABS':('ABS','abs',''),
    'dcTractionControl':('Traction control','tc',''), 'dcTractionControl2':('Traction control 2','tc2',''),
    'dcEnginePower':('Engine map','engine',''), 'dcThrottleShape':('Throttle shape','throttleShape',''),
    'dcFuelMixture':('Fuel mixture','mixture',''), 'dcBrakeBiasFine':('Brake fine adjustment','brakeFine',''),
    'dcBrakeMisc':('Brake adjustment','brakeMisc',''), 'dcPeakBrakeBias':('Peak brake setting','peakBrake',''),
    'dcAntiRollFront':('Front anti-roll','antiRollFront',''), 'dcAntiRollRear':('Rear anti-roll','antiRollRear',''),
    'dcWeightJackerRight':('Weight jacker','weightJacker',''), 'dcDiffEntry':('Differential entry','diffEntry',''),
    'dcDiffMiddle':('Differential middle','diffMiddle',''), 'dcDiffExit':('Differential exit','diffExit',''),
    'dcMGUKDeployMode':('Hybrid deployment','deployment',''), 'dcMGUKRegenGain':('Hybrid regeneration','regeneration',''),
}


def speed_quantity(value):
    """Session speed strings carry their own units, independent of DisplayUnits."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(kph|km/h|mph|m/s)\s*', value, re.I)
    if not match:
        return None
    return float(match[1]) * {'kph': 1/3.6, 'km/h': 1/3.6, 'mph': .44704, 'm/s': 1}[match[2].lower()]


def rpm_limits(info, live=None):
    live = live or {}
    def positive(key):
        value = number(live.get(key.replace('DriverCar', 'PlayerCar')))
        if value is None or value <= 0:
            value = number(info.get(key))
        return value if value is not None and value > 0 else None
    maximum = positive('DriverCarRedLine')
    last = positive('DriverCarSLLastRPM')
    blink = positive('DriverCarSLBlinkRPM')
    shift = positive('DriverCarSLShiftRPM') or blink or last
    if shift is None and maximum:
        shift = maximum * .95
    return dict(max_rpm=maximum, shift_rpm=shift, blink_rpm=blink or shift,
                shift_first_rpm=positive('DriverCarSLFirstRPM') or (shift * .65 if shift else None),
                shift_last_rpm=last or shift)


def empty(mode='live', message='Waiting for iRacing'):
    return dict(mode=mode, connected=False, message=message, timestamp=time.time(),
                session={}, car={}, drivers=[], history=[], fuel={}, trace=[], reference=[],
                sectors=[], input_trace=[], raw={}, pit={}, coaching={}, buttonbox={}, track_map=dict(source='sdk-gps',status='waiting',progress=0,points=[],message='Waiting for SDK GPS telemetry'))


@lru_cache(maxsize=1)
def country_codes():
    countries = json.loads((Path(__file__).parent/'static/countries.json').read_text(encoding='utf-8'))
    codes = {}
    for country in countries:
        codes[country['code']] = country['code']
        codes[country['name'].upper()] = country['code']
    codes.update({'UK':'GB', 'UNITED STATES OF AMERICA':'US', 'USA':'US', 'GBR':'GB', 'POL':'PL', 'DEU':'DE'})
    for alpha3, alpha2 in zip(
        'ESP FRA ITA NLD CAN AUS BRA PRT CZE FIN SWE NOR DNK CHE AUT BEL UKR HUN ROU SVK GRC JPN CHN KOR MEX ARG NZL ZAF IRL'.split(),
        'ES FR IT NL CA AU BR PT CZ FI SE NO DK CH AT BE UA HU RO SK GR JP CN KR MX AR NZ ZA IE'.split()):
        codes[alpha3] = alpha2
    return codes


def driver_profile(driver):
    license_text = str(driver.get('LicString') or '')
    match = re.search(r'\b([0-4]\.\d{2})\b', license_text)
    rating = float(match[1]) if match else number(driver.get('LicSubLevel'))
    if not match and rating is not None:
        rating /= 100
    if rating is not None and not 0 <= rating <= 4.99:
        rating = None
    country = flair_countries().get(str(driver.get('FlairID')))
    for key in ('CountryCode', 'Country', 'Nationality', 'CountryName'):
        if country:
            break
        value = driver.get(key)
        if isinstance(value, str):
            country = country_codes().get(value.strip().upper())
            if country:
                break
    if country is None:
        country = country_codes().get(str(driver.get('FlairName') or '').strip().upper())
    return dict(user_id=number(driver.get('UserID')), safety_rating=rating,
                country=country,
                license_color=f"#{driver['LicColor']:06x}" if type(driver.get('LicColor')) is int and 0<=driver['LicColor']<=0xffffff else None)


@lru_cache(maxsize=1)
def flair_countries():
    """Numeric country identifiers from the iRacing flair lookup response."""
    return json.loads((Path(__file__).parent/'static/sdk-flairs.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=256)
def car_brand(name):
    name = str(name or '').strip()
    aliases = {'mercedes': 'Mercedes-Benz', 'aston martin': 'Aston Martin',
               'alfa romeo': 'Alfa Romeo', 'land rover': 'Land Rover',
               'vw': 'Volkswagen', 'chevy': 'Chevrolet'}
    brands = ('Porsche', 'Ferrari', 'BMW', 'Audi', 'McLaren', 'Lamborghini',
              'Ford', 'Chevrolet', 'Toyota', 'Honda', 'Acura', 'Nissan', 'Mazda',
              'Renault', 'Volkswagen', 'Subaru', 'Hyundai', 'Kia', 'Cadillac',
              'Pontiac', 'Buick', 'Dallara', 'Ligier', 'Oreca', 'Lotus', 'Radical',
              'Ginetta', 'Holden')
    for prefix, brand in aliases.items():
        if re.search(r'\b' + re.escape(prefix) + r'\b', name, re.I): return brand
    for brand in brands:
        if re.search(r'\b' + re.escape(brand) + r'\b', name, re.I): return brand
    return None


def relative_seconds(offset, opponent_time, player_time, duration):
    """Use a shared class timing scale; retain the spatial estimate if unavailable."""
    if offset is None or duration is None or duration <= 0:
        return None
    if offset == 0:
        return 0
    if all(number(t) is not None and 0 <= t <= duration for t in (opponent_time, player_time)):
        difference = opponent_time - player_time
        if offset > 0 and difference < 0:
            difference += duration
        elif offset < 0 and difference > 0:
            difference -= duration
        if 0 < abs(difference) < duration:
            return difference
    return offset * duration


def driver_compound(driver, player, info, index):
    """Resolve per-car metadata first; GT3 shares the SDK hard/wet tire set."""
    own = {r['index']: r['name'] for r in read_compounds(driver)}
    if index in own:
        return own[index]
    shared = {r['index']: r['name'] for r in read_compounds(info)}
    if ((driver.get('CarID') is not None and driver.get('CarID') == player.get('CarID'))
            or (driver.get('CarIdx') is not None and driver.get('CarIdx') == player.get('CarIdx'))):
        return shared.get(index)
    def gt3(car):
        return bool(re.search(r'\bGT3\b', str(car.get('CarClassShortName') or car.get('CarClassName') or ''), re.I))
    if (gt3(driver) and gt3(player) and driver.get('CarClassID') is not None
            and driver.get('CarClassID') == player.get('CarClassID')
            and shared.get(index, '').lower() in ('hard', 'wet')):
        return shared[index]
    return None


class LapState:
    def __init__(self, fuel_store=None):
        self.fuel_store = fuel_store
        self.reset()

    def reset(self):
        self.key = None
        self.lap = None
        self.start_fuel = None
        self.previous_fuel = None
        self.clean = False
        self.incidents = None
        self.history = deque(maxlen=20)
        self.consumption = deque(maxlen=20)
        self.historical_consumption = []
        self.trace = []
        self.reference = []
        self.reference_time = None

    def update(self, key, car, record_key=None):
        if key != self.key:
            self.reset()
            self.key = key
            if self.fuel_store and record_key is not None:
                self.historical_consumption = self.fuel_store.load(record_key)
        lap, fuel = number(car.get('lap_completed', car.get('lap'))), number(car.get('fuel'))
        if lap is None: lap = number(car.get('lap'))
        incidents = car.get('incidents')
        eligible = (bool(car.get('on_track')) and not any(car.get(k) for k in ('pit', 'garage', 'replay'))
                    and car.get('surface') in (None,3)
                    and not (car.get('session_flags',0) or 0) & 0xC118)
        if lap is not None and self.lap is not None and lap < self.lap:
            self.reset()
            self.key = key
            if self.fuel_store and record_key is not None:
                self.historical_consumption = self.fuel_store.load(record_key)
        refueling = fuel is not None and self.previous_fuel is not None and fuel > self.previous_fuel + .2
        if lap is not None and lap != self.lap:
            first_observation = self.lap is None
            if self.lap is not None:
                lap_time = car.get('last_lap')
                valid = self.clean and eligible and not refueling and incidents == self.incidents and lap == self.lap + 1
                used = self.start_fuel - fuel if fuel is not None and self.start_fuel is not None else None
                if lap_time and lap_time > 0:
                    self.history.appendleft(dict(lap=self.lap + (1 if car.get('lap_completed') is not None else 0), time=lap_time, clean=valid))
                if valid and used is not None and 0 < used <= 100:
                    self.consumption.append(used)
                    if self.fuel_store and record_key is not None:
                        self.fuel_store.save(record_key, self.consumption)
                if valid and lap_time and lap_time > 0 and len(self.trace) > 30 and self.trace[0]['pct'] < .03 and (self.reference_time is None or lap_time < self.reference_time):
                    self.reference = self.trace[:]
                    self.reference_time = lap_time
            self.trace = []
            self.lap, self.start_fuel = lap, fuel
            self.incidents, self.clean = incidents, eligible
            if first_observation and (car.get('lap_pct') is None or car['lap_pct'] > .002):
                self.clean = False
        if (not eligible or incidents != self.incidents or fuel is None
                or refueling):
            self.clean = False
        self.previous_fuel = fuel
        pct = car.get('lap_pct')
        if pct is not None and 0 <= pct <= 1 and eligible:
            if not self.trace or abs(pct - self.trace[-1]['pct']) >= .002:
                self.trace.append({k: car.get(k) for k in ('throttle', 'brake', 'speed', 'gear')} | {'pct': pct})
                self.trace = self.trace[-650:]
        rows = list(self.consumption) or self.historical_consumption
        historical = bool(rows and not self.consumption)
        avg = sum(rows) / len(rows) if rows else None
        return dict(average=avg, last=self.consumption[-1] if self.consumption else None,
                    minimum=min(rows) if rows else None,
                    maximum=max(rows) if rows else None,
                    laps_left=fuel / avg if fuel is not None and avg else None,
                    samples=rows, historical=historical,
                    source='historical' if historical else 'session',
                    status='historical' if historical else 'measured' if avg else 'recording' if self.clean else 'waiting',
                    message='Historical clean-lap fuel measurement for this car and layout.' if historical else 'Fuel consumption measured.' if avg else
                    'Recording a full clean lap.' if self.clean else
                    'Cross the start line, then complete a full clean on-track lap without refueling.')


SCALARS = {
    'speed': 'Speed', 'rpm': 'RPM', 'gear': 'Gear', 'throttle': 'Throttle', 'brake': 'Brake',
    'clutch': 'Clutch', 'steering': 'SteeringWheelAngle', 'fuel': 'FuelLevel', 'lap': 'Lap',
    'lap_completed': 'LapCompleted', 'lap_pct': 'LapDistPct', 'current_lap': 'LapCurrentLapTime', 'last_lap': 'LapLastLapTime',
    'best_lap': 'LapBestLapTime', 'delta': 'LapDeltaToSessionBestLap',
    'delta_speed': 'LapDeltaToSessionBestLap_DD', 'water': 'WaterTemp', 'oil': 'OilTemp',
    'bias': 'dcBrakeBias', 'abs': 'dcABS', 'tc': 'dcTractionControl', 'map': 'dcEnginePower',
    'incidents': 'PlayerCarMyIncidentCount', 'position': 'PlayerCarPosition',
    'left_right': 'CarLeftRight', 'surface':'PlayerTrackSurface', 'lat': 'Lat', 'lon': 'Lon', 'pit_service': 'PitSvStatus',
    'yaw':'Yaw', 'velocity_x':'VelocityX', 'velocity_y':'VelocityY',
    'steering_max':'SteeringWheelAngleMax', 'throttle_raw':'ThrottleRaw', 'brake_raw':'BrakeRaw', 'clutch_raw':'ClutchRaw',
    'engine_warnings':'EngineWarnings', 'oil_pressure':'OilPress', 'fuel_pressure':'FuelPress', 'voltage':'Voltage',
    'tow_time':'PlayerCarTowTime', 'fuel_rate':'FuelUsePerHour', 'drs_status':'DRS_Status', 'drs_count':'DRS_Count',
    'delta_best':'LapDeltaToBestLap', 'delta_optimal':'LapDeltaToOptimalLap', 'delta_session_optimal':'LapDeltaToSessionOptimalLap',
    'delta_last':'LapDeltaToSessionLastlLap', 'team_incidents':'PlayerCarTeamIncidentCount',
}


class LiveSource:
    def __init__(self, sdk, map_directory=None):
        self.sdk = sdk
        self.recorder=TrackRecorder(MapStore(map_directory))
        coaching_directory=Path(map_directory).parent if map_directory else data_directory()
        self.coaching=CoachingRecorder(ReferenceStore(coaching_directory/'coaching'))
        self.laps = LapState(FuelRecords(coaching_directory/'fuel-records'))
        self.previous = {}
        self.previous_time = None
        self.last_session_time = None
        self.race = RaceState()
        self.system_keys = set()
        self.system_car = None
        self.inputs = deque(maxlen=180)
        self.input_key = None
        self.previous_key = None
        self.records = LapRecords(Path(map_directory).parent/'lap-records' if map_directory else data_directory()/'lap-records')

    def read(self, include_raw=False):
        ir = self.sdk
        if not ir.is_initialized:
            ir.startup()
        if not ir.is_connected:
            ir.shutdown()
            self.laps.reset()
            self.recorder.reset_attempt()
            self.coaching.reset_attempt()
            self.previous = {}
            self.previous_time = None
            self.race.reset()
            self.last_session_time = None
            self.inputs.clear()
            return empty(message='Start iRacing and join a session. Reconnecting…')
        ir.freeze_var_buffer_latest()
        try:
            def get(key, fallback=None):
                value = ir[key]
                return fallback if value is None else value
            car = {key: number(get(sdk_key)) for key, sdk_key in SCALARS.items()}
            for pedal in ('throttle','brake','throttle_raw','brake_raw','clutch','clutch_raw'):
                if car[pedal] is not None:
                    car[pedal] = max(0, min(1, 1-car[pedal] if pedal.startswith('clutch') else car[pedal]))
            warnings = get('EngineWarnings')
            car['pit_limiter'] = bool(warnings & 0x10) if type(warnings) is int else None
            car.update(on_track=bool(get('IsOnTrack', get('IsOnTrackCar', False))), pit=bool(get('OnPitRoad', False)),
                       garage=bool(get('IsInGarage', False)), replay=bool(get('IsReplayPlaying', False)), abs_active=get('BrakeABSactive'))
            car['in_car'] = bool(get('IsOnTrack', False)) and not car['garage'] and not car['replay']
            car['p2p_active'] = get('P2P_Status',get('PushToPass'))
            car['p2p_count'] = number(get('P2P_Count'))
            if car['p2p_count'] is not None and car['p2p_count']<0:
                car['p2p_count'] = None
            if car['p2p_active'] is False and car['p2p_count'] is None:
                car['p2p_active'] = None
            car['session_flags'] = number(get('SessionFlags'),0)
            for value, valid in [('delta','LapDeltaToSessionBestLap_OK'),('delta_best','LapDeltaToBestLap_OK'),
                                 ('delta_optimal','LapDeltaToOptimalLap_OK'),('delta_session_optimal','LapDeltaToSessionOptimalLap_OK'),
                                 ('delta_last','LapDeltaToSessionLastlLap_OK')]:
                if get(valid) is False:
                    car[value] = None
            weekend, info, driver_info = get('WeekendInfo', {}), get('SessionInfo', {}), get('DriverInfo', {})
            session_num = get('SessionNum', 0)
            session = next((s for s in (info.get('Sessions') or []) if s.get('SessionNum') == session_num), {})
            player = get('PlayerCarIdx', driver_info.get('DriverCarIdx', -1))
            player_driver = next((d for d in (driver_info.get('Drivers') or []) if d.get('CarIdx') == player), {})
            model = player_driver.get('CarID'), player_driver.get('CarPath')
            if model != self.system_car:
                self.system_car, self.system_keys = model, set()
            headers = getattr(ir, 'var_headers_names', None) or []
            system_names = set(SYSTEM_LABELS) | {name for name in headers if name.startswith('dc')}
            excluded = {'dcDashPage','dcDashPage2','dcTearOffVisor','dcStarter','dcHeadlightFlash'}
            observed = {name:number(get(name)) for name in system_names-excluded} if car['in_car'] else {}
            self.system_keys.update(name for name,value in observed.items() if value is not None)
            car['systems'] = []
            for name in sorted(self.system_keys, key=lambda k:(k not in SYSTEM_LABELS, list(SYSTEM_LABELS).index(k) if k in SYSTEM_LABELS else k)):
                label,role,unit = SYSTEM_LABELS.get(name,(re.sub(r'(?<=[a-z])(?=[A-Z])',' ',name[2:]),name,''))
                car['systems'].append(dict(key=name,label=label,role=role,unit=unit,value=observed.get(name)))
            car.update(rpm_limits(driver_info, {key: get(key) for key in (
                'PlayerCarSLFirstRPM', 'PlayerCarSLShiftRPM', 'PlayerCarSLLastRPM', 'PlayerCarSLBlinkRPM')}))
            car['speed_unit'] = 'mph' if get('DisplayUnits') == 0 else 'km/h'
            now = number(get('SessionTime'), 0)
            key = (weekend.get('SessionID'), weekend.get('SubSessionID'), session_num, player, weekend.get('TrackName'), weekend.get('TrackID'), weekend.get('TrackLength'), model)
            if key != self.previous_key:
                self.previous = {}
                self.previous_time = None
                self.previous_key = key
                self.recorder.reset_attempt()
            if self.last_session_time is not None and now < self.last_session_time:
                self.laps.reset()
                self.recorder.reset_attempt()
                self.coaching.reset_attempt()
                self.previous = {}
                self.previous_time = None
            self.last_session_time = now
            if not car['in_car']:
                self.inputs.clear()
            if key != self.input_key or self.inputs and now < self.inputs[-1]['time']:
                self.inputs.clear()
                self.input_key = key
            if car['in_car'] and (not self.inputs or now > self.inputs[-1]['time']):
                self.inputs.append({k:car.get(k) for k in ('throttle','brake','clutch','steering','abs_active')} | {'time':now})
            record_key = (weekend.get('TrackID'),weekend.get('TrackName'),*model)
            fuel_key = (*record_key, quantity(weekend.get('TrackLength'), 1000))
            fuel = self.laps.update(key, car, fuel_key)
            car['recorded_best'] = self.records.observe(record_key,self.laps.reference_time)
            car['predicted_lap'] = car['best_lap']+car['delta'] if car['best_lap'] is not None and car['best_lap']>0 and car['delta'] is not None else None
            length = quantity(weekend.get('TrackLength'), 1000)
            arrays = {name: get(name, []) for name in ['CarIdxLapDistPct', 'CarIdxPosition', 'CarIdxClassPosition',
                       'CarIdxLapCompleted', 'CarIdxOnPitRoad', 'CarIdxLastLapTime', 'CarIdxBestLapTime', 'CarIdxTrackSurface', 'CarIdxEstTime',
                       'CarIdxLap','CarIdxSessionFlags','CarIdxTireCompound','CarIdxF2Time','CarIdxP2P_Status','CarIdxP2P_Count']}
            def idx(name, i, fallback=None):
                arr = arrays[name]
                return arr[i] if isinstance(arr,(list,tuple)) and type(i) is int and 0 <= i < len(arr) else fallback
            drivers = []
            camera = get('CamCarIdx')
            camera_pct = number(idx('CarIdxLapDistPct',camera))
            focus = camera if not car['in_car'] and type(camera) is int and camera>=0 and camera_pct is not None and 0<=camera_pct<=1 else player
            focus_driver = next((d for d in (driver_info.get('Drivers') or []) if d.get('CarIdx')==focus),{})
            focus_pct = number(idx('CarIdxLapDistPct',focus))
            if focus==player and focus_pct is None:
                focus_pct = car['lap_pct']
            results = {row.get('CarIdx'): row for row in (session.get('ResultsPositions') or [])}
            qualifying = get('QualifyResultsInfo', {}) or {}
            grid = {row.get('CarIdx'):row for row in (qualifying.get('Results') or [])}
            elapsed = now - self.previous_time if self.previous_time is not None else 0
            for d in (driver_info.get('Drivers') or []):
                i = d.get('CarIdx', -1)
                pct = number(idx('CarIdxLapDistPct', i))
                if type(i) is not int or i<0 or d.get('IsSpectator') or d.get('CarIsPaceCar'):
                    continue
                if pct is not None and not 0 <= pct <= 1:
                    pct = None
                old = self.previous.get(i)
                speed = None
                if pct is not None and old is not None and elapsed > 0 and length:
                    distance = ((pct - old + .5) % 1 - .5) * length
                    if 0 <= distance / elapsed <= 150:
                        speed = distance / elapsed
                self.previous[i] = pct
                relative = ((pct - focus_pct + .5) % 1 - .5) if pct is not None and focus_pct is not None and 0 <= focus_pct <= 1 else None
                reference_time = car['best_lap'] if focus==player else number(idx('CarIdxBestLapTime',focus))
                lap_time = reference_time if reference_time and reference_time>0 else number(focus_driver.get('CarClassEstLapTime'))
                if not lap_time and focus==player and length and car['speed'] and car['speed']>5:
                    lap_time = length/car['speed']
                gap = relative * lap_time if relative is not None and lap_time else None
                class_lap = number(focus_driver.get('CarClassEstLapTime'))
                if focus_driver.get('CarClassID') is not None and d.get('CarClassID') == focus_driver['CarClassID'] and class_lap and class_lap > 0:
                    gap = relative_seconds(relative, number(idx('CarIdxEstTime', i)), number(idx('CarIdxEstTime', focus)), class_lap)
                if i==focus and pct is not None:
                    gap = 0
                result = results.get(i, {})
                position = number(idx('CarIdxPosition', i))
                if position is None or position <= 0:
                    position = number(result.get('Position'), 0)
                class_position = number(idx('CarIdxClassPosition',i))
                if class_position is None or class_position <= 0:
                    class_position = number(result.get('ClassPosition'))
                    class_position = class_position+1 if class_position is not None and class_position>=0 else None
                start = grid.get(i,{})
                grid_position = number(start.get('Position'))
                grid_position = grid_position+1 if grid_position is not None and grid_position>=0 else None
                compound = number(idx('CarIdxTireCompound',i))
                compound = compound if compound is not None and compound>=0 else None
                p2p_count = number(idx('CarIdxP2P_Count',i))
                last_lap = number(idx('CarIdxLastLapTime',i))
                best_lap = number(idx('CarIdxBestLapTime',i))
                if last_lap is None or last_lap<=0:
                    last_lap=number(result.get('LastTime'))
                if best_lap is None or best_lap<=0:
                    best_lap=number(result.get('FastestTime'))
                if (best_lap is None or best_lap<=0) and str(session.get('SessionType') or '').lower()!='race':
                    best_lap=number(idx('CarIdxF2Time',i))
                drivers.append(dict(id=i, name=d.get('UserName', 'Driver'), number=str(d.get('CarNumber', '')),
                    position=position, class_position=class_position, grid_position=grid_position,
                    position_change=grid_position-position if grid_position and position>0 and str(session.get('SessionType') or '').lower()=='race' else None,
                    team=d.get('TeamName') or None, team_id=number(d.get('TeamID')), car_id=number(d.get('CarID')),
                    ai=bool(d.get('CarIsAI')), class_id=number(d.get('CarClassID')),
                    class_color=f"#{d['CarClassColor']:06x}" if type(d.get('CarClassColor')) is int and 0<=d['CarClassColor']<=0xffffff else None,
                    class_lap_time=number(d.get('CarClassEstLapTime')),
                    car_brand=car_brand(d.get('CarScreenName') or d.get('CarScreenNameShort') or d.get('CarPath')),
                    class_name=str(d.get('CarClassShortName') or d.get('CarClassName') or d.get('CarClassID', '')),
                    rating=number(d.get('IRating')), license=d.get('LicString', ''), player=i == player, **driver_profile(d),
                    focus=i==focus, relation_is_focus=focus!=player,
                    pct=pct, laps=number(idx('CarIdxLapCompleted', i)), lap=number(idx('CarIdxLap',i)),
                    flags=idx('CarIdxSessionFlags',i), compound_index=compound,
                    compound=driver_compound(d, player_driver, driver_info, compound),
                    f2_time=number(idx('CarIdxF2Time',i)),
                    radio=get('RadioTransmitCarIdx')==i,
                    p2p_active=idx('CarIdxP2P_Status',i), p2p_count=p2p_count if p2p_count is not None and p2p_count>=0 else None,
                    tow_time=car['tow_time'] if i==player else None,
                    result_status=result.get('ReasonOutStr') if number(result.get('ReasonOutId'),0)>0 else None,
                    relative=gap,
                    distance=relative * length if relative is not None and length else None,
                    speed=speed, pit=idx('CarIdxOnPitRoad', i),
                    surface=idx('CarIdxTrackSurface', i), last_lap=last_lap,best_lap=best_lap))
            self.previous_time = now
            classes = self.race.update(key,now,drivers,focus,str(session.get('SessionType') or ''),get('SessionState'))
            player_row = next((d for d in drivers if d['id']==player),{})
            car['finished'] = player_row.get('finished',False)
            data = empty()
            data.update(connected=True, message='Connected to the iRacing SDK', car=car, drivers=drivers, fuel=fuel,
                history=list(self.laps.history), trace=self.laps.trace[:], reference=self.laps.reference[:], input_trace=list(self.inputs),
                session=dict(key=f"{weekend.get('SessionID')}/{weekend.get('SubSessionID')}/{session_num}/{player}/{model}", track_id=weekend.get('TrackID'), track=weekend.get('TrackDisplayName', weekend.get('TrackName', 'iRacing')),
                    car=next((d.get('CarScreenName') for d in (driver_info.get('Drivers') or []) if d.get('CarIdx') == player), 'iRacing'),
                    type=session.get('SessionType', 'Session'), time=now,
                    remaining=number(get('SessionTimeRemain')), laps_remaining=number(get('SessionLapsRemainEx')),
                    total_laps=quantity(session.get('SessionLaps')), track_length=length,
                    flags=get('SessionFlags', 0), air=number(get('AirTemp')), track_temp=number(get('TrackTempCrew')),
                    humidity=number(get('RelativeHumidity')), wind=number(get('WindVel')), wind_dir=number(get('WindDir')),
                    wetness=number(get('TrackWetness')), rain=number(get('Precipitation')), state=get('SessionState'),
                    classes=classes, incidents=car['incidents'], team_incidents=car['team_incidents'],
                    incident_limit=quantity((weekend.get('WeekendOptions') or {}).get('IncidentLimit')),
                    clock_seconds=number(get('SessionTimeOfDay')), player_class=player_driver.get('CarClassID'),
                    player_idx=player, lap=car.get('lap'), total_time=quantity(session.get('SessionTime')),
                    focus_idx=focus, focus_name=focus_driver.get('UserName') if focus!=player else None,
                    pit_limit=speed_quantity(weekend.get('TrackPitSpeedLimit'))))
            track_key=(weekend.get('TrackID'),weekend.get('TrackName'),length)
            coaching_key=(*track_key,*model,player_driver.get('CarScreenName'))
            data['track_map']=self.recorder.update(coaching_key,car,now)
            data['coaching']=self.coaching.update(key,coaching_key,car,now)
            data['sectors']=sector_layout(get('SplitTimeInfo'))
            data['sector_source']='sdk' if data['sectors'] else 'unavailable'
            data['pit'] = read_pit(get, driver_info, car['in_car'])
            data['buttonbox'] = read_states(get, car)
            data['raw'] = {k: get(k) for k in list(SCALARS.values()) + ['SessionFlags', 'SessionState', 'SessionTime', 'TrackWetness']}
            if include_raw:
                data['raw'].update({name:get(name) for name in headers})
                data['raw'].update({f'Session.{name}':get(name) for name in ('WeekendInfo','SessionInfo','DriverInfo','QualifyResultsInfo')})
            data['raw'] = json_safe(data['raw'])
            return json_safe(data)
        finally:
            ir.unfreeze_var_buffer_latest()


class DemoSource:
    def __init__(self):
        self.started = time.monotonic()
        self.race = RaceState()

    def read(self):
        t = time.monotonic() - self.started
        pct = (t / 102.4 + .37) % 1
        completed = 11 + int(t / 102.4 + .37)
        speed = 48 + 19 * math.sin(t / 5)
        throttle = max(0, min(1, math.sin(t / 3) * .7 + .4))
        brake = max(0, -math.sin(t / 3) * .85 - .1)
        car = dict(speed=speed, rpm=4800 + speed * 42, max_rpm=8500, shift_rpm=8000,
            gear=max(2, min(6, int(speed / 12))), throttle=throttle, brake=brake, clutch=0,
            steering=math.sin(t / 4) * .6, fuel=42.8 - (t % 600) * .025, lap=completed+1, lap_completed=completed,
            lap_pct=pct, current_lap=pct * 102.4, last_lap=102.842, best_lap=102.125,
            delta=math.sin(t / 10) * .34, delta_speed=math.cos(t / 10) * .034,
            speed_unit='km/h', water=87.3, oil=103.4, bias=54.2, abs=4, tc=3, map=1, incidents=2,
            position=5, left_right=2 if int(t / 8) % 4 == 0 else 1,
            pit=False, garage=False, on_track=True, in_car=True, replay=False, abs_active=brake > .6, pit_limiter=False,
            throttle_raw=throttle,brake_raw=brake,clutch_raw=0,engine_warnings=0,voltage=13.8,
            oil_pressure=4.2,fuel_pressure=5.1,fuel_rate=32,delta_best=.15,delta_optimal=.32,delta_session_optimal=.4,delta_last=-.12)
        names = ['Marco Rossi', 'Alex Morgan', 'Lukas Weber', 'Sofia Costa', 'Jan Kowalski',
                 'Emma Wilson', 'Mateusz Nowak', 'Noah Jensen', 'Oliver Martin', 'Leo Dubois', 'Tom Lee', 'Eva Fischer']
        drivers = []
        for i, name in enumerate(names):
            rel = (4 - i) * 2.47
            total = completed + pct + rel/102.4 + (1 if i==0 else -1 if i==7 else 0)
            in_pit = i==10 or i==9 and int(t/20)%3==1
            drivers.append(dict(id=i, name=name, number=str([12, 7, 88, 24, 27, 19, 63, 5, 31, 44, 9, 16][i]),
                position=i + 1, class_position=i + 1, class_name='GT3', car_brand=['Porsche','Ferrari','BMW','Mercedes-Benz'][i%4], rating=3210 - i * 87,
                license='A 3.42', safety_rating=3.42, user_id=10000+i,
                country=['PL','GB','DE','FR','US','IT','NL','CA'][i%8], player=i == 4, pct=total%1, laps=math.floor(total),
                relative=rel, distance=rel / 102.4 * 5793, speed=speed + (i % 3 - 1) * 3,
                pit=in_pit, surface=1 if in_pit else 3, last_lap=102.2 + i * .14, best_lap=101.9 + i * .1,
                class_id=1,class_color='#39b4e8',class_lap_time=102.4,team='Demo Racing '+str(i+1),team_id=100+i,
                car_id=i%4,compound='Dry',compound_index=0,flags=0x100000 if i==6 else 0x10000 if i==8 else 0,
                radio=i==2 and int(t)%8<3,grid_position=i+1,position_change=0,f2_time=i*2.47,p2p_active=None,p2p_count=None))
        classes = self.race.update('demo',1242+t,drivers,4,'Race',4)
        for d in drivers:
            d['class_color'] = '#39b4e8'
        data = empty('demo')
        data.update(connected=True, message='DEMO · simulated data', car=car, drivers=drivers,
            session=dict(track_id=239, track='Monza · Grand Prix', car='Porsche 911 GT3 R', type='Race', time=1242+t,
                remaining=max(0, 2340-t), laps_remaining=23, total_laps=35, track_length=5793,
                flags=4, air=23, track_temp=32, humidity=.54, wind=3.7, wind_dir=1.2, wetness=1,
                rain=0, state=4, pit_limit=22.2222,classes=classes,incident_limit=17,clock_seconds=46800+t,lap=car['lap']),
            history=[dict(lap=11-i, time=102.842+i*.18+math.sin(i)*.2, clean=True) for i in range(12)],
            fuel=dict(average=2.61, last=2.58, minimum=2.49, maximum=2.75,
                laps_left=car['fuel']/2.61, samples=[2.6,2.55,2.68,2.49,2.75,2.61,2.58]),
            trace=[dict(pct=j/150, throttle=max(0,min(1,math.sin(j/7)*.7+.4)), brake=max(0,-math.sin(j/7)*.8-.1),speed=50,gear=4) for j in range(int(pct*150))],
            reference=[dict(pct=j/150, throttle=max(0,min(1,math.sin(j/7+.2)*.7+.4)),brake=max(0,-math.sin(j/7+.2)*.8-.1),speed=52,gear=4) for j in range(151)],
            )
        data['input_trace'] = [dict(throttle=max(0,min(1,math.sin(j/14+t)*.7+.4)),brake=max(0,-math.sin(j/14+t)*.8-.1),clutch=0) for j in range(120)]
        data['pit'] = dict(available=True, can_control=True, flags=31, fuel=20, compound=0, compounds=[dict(index=0,name='Dry'),dict(index=1,name='Wet')], pressures=dict(lf=160,rf=160,lr=165,rr=165),status=0,fast_repairs=1,fuel_max=110)
        data['track_map']=dict(source='demo-generated',status='ready',progress=1,message='DEMO circuit · synthetic outline, not a real track',points=[[round(210*math.cos(i/600*math.tau)*(1+.18*math.cos(i/600*math.tau*3)),3),round(140*math.sin(i/600*math.tau),3)] for i in range(600)])
        sample=lambda row,duration:dict(row,time=row['pct']*duration+(.35*math.sin(row['pct']*math.tau*2) if duration==102.4 else 0))
        reference=dict(id='demo-reference',lap_time=102.125,samples=[sample(row,102.125) for row in data['reference']])
        data['coaching']=dict(status='ready',message='DEMO · synthetic lap comparison',current_time=car['current_lap']+.35*math.sin(pct*math.tau*2),
            trace=[sample(row,102.4) for row in data['trace']],
            references=dict(session='demo-reference',personal='demo-reference',last='demo-reference'),laps={'demo-reference':reference})
        data['sectors']=[dict(number=i+1,start=i/7,end=(i+1)/7) for i in range(7)]
        data['sector_source']='demo-generated'
        data['raw'] = {k: car.get(k) for k in car}
        return data


class Telemetry:
    def __init__(self, demo=False, hz=20, map_directory=None):
        self.map_directory=map_directory
        self.demo, self.hz = demo, hz
        self._lock = threading.Lock()
        self._data = empty('demo' if demo else 'live')
        self._stop = threading.Event()
        self._thread = None
        self._commands = queue.Queue(maxsize=4)
        self._raw_until = 0
        self.buttonbox = ButtonBox(demo=demo)

    def start(self):
        self._thread = threading.Thread(target=self._run, name='iracing-telemetry', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.buttonbox.stop()
        self._fail_commands('Telemetry stopped. The queued plan was not sent.')
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self, sections=None):
        with self._lock:
            if sections is None or 'raw' in sections:
                self._raw_until = time.monotonic() + 2
            filtered = dict(self._data)
            # Age is measured on the server, not against the tablet's wall clock.
            filtered['sample_age'] = max(0, time.time() - filtered['timestamp'])
            if sections is not None:
                for key in ('trace', 'reference', 'raw', 'track_map', 'coaching'):
                    if key not in sections:
                        filtered[key] = {} if key in ('raw', 'track_map', 'coaching') else []
                if 'trace' not in sections:
                    filtered['input_trace'] = []
            result = copy.deepcopy(filtered)
        states = result.setdefault('buttonbox', {})
        states.update(source='demo' if self.demo else 'sdk', available=bool(result['connected']) and result['sample_age'] < 2 and (self.demo or self.buttonbox.sink.supported))
        if self.demo:
            with self.buttonbox.lock:
                states.update(self.buttonbox.demo_states)
            states['message'] = 'DEMO: simulated controls; no keys sent.'
        elif not self.buttonbox.sink.supported:
            states['message'] = 'Live button-box controls require Windows.'
        else:
            states['message'] = 'Keep iRacing focused. Assign the same keys in iRacing Controls.'
        for field in ('ignition','pit_limiter','wipers','bias','tc','abs'):
            states.setdefault(field,None)
            if not self.demo and (not result['connected'] or result['sample_age'] >= 2):
                states[field] = None
        return result

    def submit_buttonbox(self, payload, owner='local'):
        snap = self.snapshot(sections=set())
        return self.buttonbox.submit(payload, ready=bool(snap['buttonbox']['available']), owner=owner)

    def submit_pit(self, plan):
        batch = commands(plan)  # Validate before enqueueing any side effects.
        snap = self.snapshot()
        if not snap['connected'] or not snap.get('pit', {}).get('can_control'):
            raise RuntimeError('Not connected or the driver is not in the car')
        validate_compound(batch,snap.get('pit') or {})
        if self.demo:
            return dict(status='demo', message='DEMO: plan validated; no commands were sent to the game')
        task = dict(batch=batch, ready=threading.Event(), cancelled=threading.Event(), error=None,
                    session=(snap['session'].get('track_id'), snap['session'].get('time', 0), snap['session'].get('key')))
        try:
            self._commands.put_nowait(task)
        except queue.Full:
            raise RuntimeError('Command queue is busy. Check the in-game settings before retrying.')
        if not task['ready'].wait(4):
            task['cancelled'].set()
            raise RuntimeError('Request timed out. Outcome unknown; check the pit plan in the game before retrying.')
        if task['error']:
            raise RuntimeError(task['error'])
        return dict(status='sent', message='Commands broadcast through the SDK. Check the service readback below; the game may reject unsupported settings.')

    def _drain_commands(self, source, data):
        while True:
            try:
                task = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if task['cancelled'].is_set():
                    continue
                track, session_time, session_key = task['session']
                if not data['connected'] or not data.get('pit', {}).get('can_control') or data['session'].get('track_id') != track or data['session'].get('key') != session_key or data['session'].get('time', 0) < session_time:
                    raise RuntimeError('The session changed or the driver left the car. The plan was not sent.')
                validate_compound(task['batch'],data.get('pit') or {})
                for mode, value in task['batch']:
                    if not source.sdk.pit_command(mode, value):
                        raise RuntimeError('Sending interrupted. Some settings may have changed; check the pit plan in the game.')
            except Exception as exc:
                task['error'] = str(exc)
            finally:
                task['ready'].set()

    def _fail_commands(self,message):
        while True:
            try:task=self._commands.get_nowait()
            except queue.Empty:return
            task['error']=message
            task['cancelled'].set()
            task['ready'].set()

    def _run(self):
        source = None
        if self.demo:
            source = DemoSource()
        elif platform.system() != 'Windows':
            with self._lock:
                self._data = empty(message='The iRacing SDK requires Windows. Preview with: python3 server.py --demo')
            return
        else:
            try:
                import irsdk
                source = LiveSource(irsdk.IRSDK(),self.map_directory)
            except ImportError:
                with self._lock:
                    self._data = empty(message='pyirsdk is missing. Run: python3 -m pip install -r requirements.txt')
                return
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                data = empty()
                try:
                    data = source.read() if self.demo else source.read(include_raw=time.monotonic()<self._raw_until)
                    if not self.demo:
                        self._drain_commands(source, data)
                        if not data.get('connected'):
                            self.buttonbox.release_all()
                    # Validate before publishing; malformed SDK floats must never break JSON.
                    json.dumps(data,allow_nan=False)
                    with self._lock:
                        self._data = data
                except Exception as exc:
                    with self._lock:
                        self._data = empty('demo' if self.demo else 'live', f'SDK error ({type(exc).__name__}). Reconnecting…')
                    if not self.demo:
                        self.buttonbox.release_all()
                        self._fail_commands('SDK connection interrupted. The queued plan was not sent.')
                        source.laps.reset()
                        source.race.reset()
                        source.inputs.clear()
                        source.previous={}
                        source.previous_time=None
                        source.last_session_time=None
                        source.recorder.reset_attempt()
                        source.sdk.shutdown()
                    self._stop.wait(1)
                self._stop.wait(max(0, 1/self.hz - (time.monotonic()-started)) if data.get('connected') else 1)
        finally:
            self.buttonbox.release_all()
            self._fail_commands('Telemetry stopped. The queued plan was not sent.')
            if not self.demo:
                source.sdk.shutdown()
