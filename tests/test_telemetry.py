import json
import unittest
from irboard.telemetry import DemoSource, LapState, LiveSource, Telemetry, rpm_limits, driver_profile, car_brand, speed_quantity, relative_seconds, driver_compound
import time

class SDK:
    is_initialized=True
    is_connected=True
    def __init__(self):
        self.frozen=False
    def __getitem__(self,k):
        return {'Speed':42,'SessionNum':0,'SessionTime':2,'Lap':1,'FuelLevel':30,'IsOnTrack':True}.get(k)
    def freeze_var_buffer_latest(self):self.frozen=True
    def unfreeze_var_buffer_latest(self):self.frozen=False
    def shutdown(self):pass

class TelemetryTests(unittest.TestCase):
    def test_country_and_safety_rating_use_explicit_profile_values(self):
        self.assertEqual(driver_profile({'UserID':123, 'CountryCode':'pl','LicString':'A 3.42','LicSubLevel':100}),
                         {'user_id':123,'country':'PL','safety_rating':3.42,'license_color':None})
        self.assertEqual(driver_profile({'Country':'Germany','LicSubLevel':285})['country'],'DE')
        self.assertEqual(driver_profile({'LicSubLevel':285})['safety_rating'],2.85)
        self.assertIsNone(driver_profile({'ClubName':'Poland'})['country'])
        self.assertIsNone(driver_profile({'ClubName':'Iberia'})['country'])
        self.assertIsNone(driver_profile({'LicString':'unknown','LicSubLevel':-1})['safety_rating'])
        self.assertEqual(driver_profile({'LicColor':0x0153db})['license_color'],'#0153db')

    def test_selected_sdk_flair_prevents_club_and_country_confusion(self):
        self.assertEqual(driver_profile({'FlairID':223,'ClubName':'Georgia','Country':'Georgia'})['country'],'US')
        self.assertEqual(driver_profile({'FlairID':167})['country'],'PL')
        self.assertEqual(driver_profile({'FlairID':77})['country'],'DE')
        for flair in [None, 1, 2, 99999]:
            self.assertIsNone(driver_profile({'FlairID':flair,'ClubName':'Georgia'})['country'])
        self.assertEqual(driver_profile({'FlairName':'Poland'})['country'],'PL')

    def test_pit_speed_units_are_independent_of_display_units(self):
        self.assertAlmostEqual(speed_quantity('40 mph'),17.8816)
        self.assertAlmostEqual(speed_quantity('60 kph'),60/3.6)
        self.assertEqual(speed_quantity('10 m/s'),10)
        for value in [None,'40 knots','unknown',40]:
            self.assertIsNone(speed_quantity(value))

    def test_live_rpm_thresholds_override_session_values_and_reject_zero(self):
        info={'DriverCarSLShiftRPM':7000,'DriverCarSLBlinkRPM':7200}
        live={'PlayerCarSLShiftRPM':6500,'PlayerCarSLBlinkRPM':0}
        limits=rpm_limits(info,live)
        self.assertEqual(limits['shift_rpm'],6500)
        self.assertEqual(limits['blink_rpm'],7200)

    def test_relative_timing_wraps_in_both_directions_and_handles_missing_times(self):
        self.assertEqual(relative_seconds(.02,1,98,100),3)
        self.assertEqual(relative_seconds(-.02,98,1,100),-3)
        self.assertEqual(relative_seconds(.1,22,20,100),2)
        self.assertEqual(relative_seconds(.1,None,20,100),10)
        self.assertIsNone(relative_seconds(None,22,20,100))

    def test_clutch_and_standings_survive_missing_track_position(self):
        class ProfileSDK(SDK):
            def __getitem__(self,key):
                return {'Clutch':self.clutch,'DriverInfo':{'Drivers':[{'CarIdx':0,'UserName':'Driver','FlairID':167}]},
                    'CarIdxLapDistPct':[-1],'CarIdxPosition':[0], 'SessionInfo':{'Sessions':[{'SessionNum':0,
                    'ResultsPositions':[{'CarIdx':0,'Position':7}]}]}}.get(key,super().__getitem__(key))
        sdk=ProfileSDK();sdk.clutch=1
        snapshot=LiveSource(sdk).read()
        self.assertEqual(snapshot['car']['clutch'],0)
        self.assertEqual(snapshot['drivers'][0]['position'],7)
        self.assertEqual(snapshot['drivers'][0]['country'],'PL')
        self.assertIsNone(snapshot['drivers'][0]['pct'])
        self.assertIsNone(snapshot['drivers'][0]['relative'])
        sdk.clutch=0
        self.assertEqual(LiveSource(sdk).read()['car']['clutch'],1)

    def test_live_same_class_estimates_and_empty_results(self):
        class TimingSDK(SDK):
            def __getitem__(self,key):
                values={'PlayerCarIdx':0,'LapDistPct':.99,'CarIdxLapDistPct':[.99,.01],
                    'CarIdxEstTime':[98,1], 'DriverInfo':{'Drivers':[
                        {'CarIdx':0,'CarClassID':1,'CarClassEstLapTime':100},
                        {'CarIdx':1,'CarClassID':1}]},
                    'SessionInfo':{'Sessions':[{'SessionNum':0,'ResultsPositions':None}]}}
                return values.get(key,super().__getitem__(key))
        data=LiveSource(TimingSDK()).read()
        self.assertEqual(data['drivers'][0]['relative'],0)
        self.assertEqual(data['drivers'][1]['relative'],3)

    def test_pit_limiter_uses_engine_status_and_distinguishes_unavailable(self):
        class WarningSDK(SDK):
            def __getitem__(self,key):
                return self.warnings if key == 'EngineWarnings' else super().__getitem__(key)
        sdk=WarningSDK()
        for warnings,expected in [(0,False),(0x10,True),(0x30,True),(0x20,False),(None,None)]:
            sdk.warnings=warnings
            self.assertIs(LiveSource(sdk).read()['car']['pit_limiter'],expected)
    def test_snapshot_reports_age_without_mutating_published_data(self):
        telemetry = Telemetry(demo=True)
        telemetry._data['timestamp'] = time.time() - 2
        snapshot = telemetry.snapshot(sections=set())
        self.assertGreaterEqual(snapshot['sample_age'],2)
        self.assertLess(snapshot['sample_age'],3)
        self.assertNotIn('sample_age',telemetry._data)
    def test_car_specific_rpm_limits_and_missing_values(self):
        limits = rpm_limits(dict(DriverCarRedLine=15000, DriverCarSLFirstRPM=10000,
                                 DriverCarSLLastRPM=13500, DriverCarSLBlinkRPM=14000))
        self.assertEqual(limits['max_rpm'],15000)
        self.assertEqual(limits['shift_rpm'],14000)
        self.assertEqual(limits['shift_first_rpm'],10000)
        self.assertEqual(rpm_limits({'DriverCarRedLine':6000})['shift_rpm'],5700)
        self.assertIsNone(rpm_limits({})['blink_rpm'])
        self.assertIsNone(rpm_limits({'DriverCarRedLine':float('nan')})['max_rpm'])
    def test_demo_json(self):
        d=DemoSource().read()
        json.dumps(d,allow_nan=False)
        self.assertEqual(d['mode'],'demo')
        self.assertTrue(any(x['player'] for x in d['drivers']))
    def test_live_missing_values(self):
        sdk=SDK();d=LiveSource(sdk).read()
        self.assertEqual(d['car']['speed'],42)
        self.assertIsNone(d['car']['bias'])
        self.assertFalse(sdk.frozen)
        json.dumps(d,allow_nan=False)
    def test_fuel_ignores_partial_lap_and_refuel(self):
        l=LapState()
        c=dict(lap=1,fuel=30,on_track=True,pit=False,incidents=0,lap_pct=0)
        l.update('session',c)
        c.update(lap=2,fuel=28,last_lap=100)
        self.assertEqual(l.update('session',c)['average'],2)
        c.update(fuel=40);l.update('session',c)
        c.update(lap=3,fuel=38)
        self.assertEqual(l.update('session',c)['samples'],[2])
    def test_completed_counter_and_first_full_lap(self):
        state = LapState()
        c = dict(lap=2, lap_completed=0, fuel=30, on_track=True, pit=False,
                 incidents=0, lap_pct=.6)
        state.update('race', c)
        c.update(lap=3, lap_completed=1, lap_pct=.001, fuel=29)
        self.assertIsNone(state.update('race', c)['average'])
        c.update(lap_pct=.5, fuel=28)
        state.update('race', c)
        c.update(lap=4, lap_completed=2, lap_pct=.001, fuel=27, last_lap=100)
        self.assertEqual(state.update('race', c)['average'], 2)

    def test_practice_consumption_and_refuel_below_start_level(self):
        state = LapState()
        car = dict(lap=1, lap_completed=0, lap_pct=.5, fuel=40,
                   on_track=True, pit=False, surface=3, incidents=0)
        self.assertEqual(state.update('Practice', car)['status'], 'waiting')
        car.update(lap=2, lap_completed=1, lap_pct=0, fuel=39)
        self.assertEqual(state.update('Practice', car)['status'], 'recording')
        car.update(lap_pct=.8, fuel=37)
        state.update('Practice', car)
        car.update(lap=3, lap_completed=2, lap_pct=0, fuel=36, last_lap=100)
        self.assertEqual(state.update('Practice', car)['samples'], [3])
        car.update(lap_pct=.4, fuel=34)
        state.update('Practice', car)
        car.update(fuel=35)  # Refuel stays below the lap's initial 36 L.
        state.update('Practice', car)
        car.update(lap=4, lap_completed=3, fuel=33)
        self.assertEqual(state.update('Practice', car)['samples'], [3])

    def test_compound_metadata_is_car_specific(self):
        player = dict(CarID=1, CarClassID=5, CarClassShortName='GT3')
        rival = dict(CarID=2, CarClassID=5, CarClassShortName='GT3')
        info = dict(DriverTires=[dict(TireIndex=0, TireCompoundType='Hard'),
                                 dict(TireIndex=1, TireCompoundType='Wet')])
        self.assertEqual(driver_compound(rival, player, info, 0), 'Hard')
        self.assertEqual(driver_compound(rival, player, info, 1), 'Wet')
        self.assertIsNone(driver_compound(rival, player, info, 2))
        self.assertIsNone(driver_compound(dict(rival, CarClassShortName='GTP'), player, info, 0))
        self.assertIsNone(driver_compound(rival, player, {}, 0))
        self.assertEqual(driver_compound(dict(rival, DriverTires=[dict(TireIndex=0, TireCompoundType='Soft')]), player, info, 0), 'Soft')

    def test_brand_from_sdk_car_name(self):
        self.assertEqual(car_brand('Mercedes-AMG GT3 2020'), 'Mercedes-Benz')
        self.assertEqual(car_brand('Porsche 911 GT3 R (992)'), 'Porsche')
        self.assertIsNone(car_brand('Unknown Prototype'))

    def test_sdk_display_units(self):
        class UnitsSDK(SDK):
            def __getitem__(self, key):
                if key == 'DisplayUnits': return self.units
                return super().__getitem__(key)
        sdk=UnitsSDK()
        sdk.units=0
        self.assertEqual(LiveSource(sdk).read()['car']['speed_unit'],'mph')
        sdk.units=1
        self.assertEqual(LiveSource(sdk).read()['car']['speed_unit'],'km/h')

    def test_session_reset(self):
        l=LapState();l.consumption.append(2)
        self.assertIsNone(l.update('new',{})['average'])

if __name__=='__main__':unittest.main()
