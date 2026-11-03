"""Per-car race observations. Missing telemetry is never an assumed result."""
import math
from collections import deque


def finite(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def progress(driver):
    laps, pct = finite(driver.get('laps')), finite(driver.get('pct'))
    return laps + pct if laps is not None and laps >= 0 and pct is not None and 0 <= pct <= 1 else None


def lap_relation(driver, player):
    """Separate actual race distance from the nearest car's wrapped track offset."""
    other, own = progress(driver), progress(player)
    if other is None or own is None:
        return None
    nearest = (driver['pct'] - player['pct'] + .5) % 1 - .5
    return int(round(other - own - nearest))


def strength_of_field(ratings):
    values = [v for v in ratings if finite(v) is not None and v > 0]
    if not values:
        return None
    scale = 1600 / math.log(2)
    base = min(values)
    return round(base - scale * math.log(sum(math.exp(-(v-base)/scale) for v in values) / len(values)))


def rating_estimates(drivers):
    """Provisional race-result estimates, not official post-race account ratings."""
    field = [d for d in drivers if not d.get('ai') and finite(d.get('rating')) is not None and d['rating'] > 0]
    starters = [d for d in field if d.get('started')]
    if len(field) < 2 or not starters:
        return {}
    scale = 1600 / math.log(2)
    strength = {d['id']: math.expm1(min(d['rating'] / scale, 50)) for d in field}
    expected = {d['id']: sum(strength[d['id']] / (strength[d['id']] + strength[o['id']])
                            for o in field if o['id'] != d['id']) for d in field}
    ordered = sorted(field, key=lambda d: (d.get('class_position') or d.get('position') or 10000, -(progress(d) or 0)))
    nonstarters = len(field) - len(starters)
    changes = {}
    for rank, d in enumerate(ordered, 1):
        if d.get('started'):
            correction = ((len(field) - nonstarters / 2) / 2 - rank) / 100
            changes[d['id']] = (len(field) - rank - expected[d['id']] - correction) * 200 / len(starters)
    absent = [d for d in field if not d.get('started')]
    weight = sum(expected[d['id']] for d in absent)
    total = sum(changes.values())
    for d in absent:
        changes[d['id']] = -total * expected[d['id']] / weight if weight else 0
    return changes


class RaceState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.key = None
        self.time = None
        self.cars = {}

    def update(self, key, now, drivers, player_idx, session_type, session_state=None):
        if key != self.key or self.time is not None and now < self.time:
            self.reset()
            self.key = key
        dt = max(0, now - self.time) if self.time is not None else 0
        self.time = now
        race = session_type.lower() == 'race'
        player = next((d for d in drivers if d['id'] == player_idx), None)
        for d in drivers:
            identity = (d.get('team_id') or d.get('user_id'), d.get('car_id'))
            state = self.cars.get(d['id'])
            if state is None or state['identity'] != identity:
                state = dict(identity=identity, previous=None, history=deque(maxlen=20), entry=None,
                             stop=0, last_pit_lap=None, last_pit_progress=None, last_pit_time=None,
                             last_stop_time=None, first_lap=d.get('laps'), radio=None, lap_pit=False)
                self.cars[d['id']] = state
            prev = state['previous']
            pct_progress = progress(d)
            if d.get('pit') is True:
                state['lap_pit'] = True
                if prev is not None and prev.get('pit') is False:
                    state['entry'], state['stop'] = now, 0
                if prev is not None and prev.get('pit') and prev.get('surface') == 1 and d.get('surface') == 1:
                    state['stop'] += dt
            elif d.get('pit') is None:
                state['entry'] = None
                state['lap_pit'] = True
            elif d.get('pit') is False and prev is not None and prev.get('pit') is True and pct_progress is not None and d.get('surface') != -1:
                state['last_pit_lap'] = d.get('lap') if finite(d.get('lap')) is not None and d['lap']>0 else d['laps']+1
                state['last_pit_progress'] = pct_progress
                state['last_pit_time'] = now - state['entry'] if state['entry'] is not None else None
                state['last_stop_time'] = state['stop'] if state['entry'] is not None else None
                state['entry'] = None
            if prev is not None and finite(prev.get('laps')) is not None and finite(d.get('laps')) is not None:
                if d['laps'] == prev['laps'] + 1:
                    lap_time = finite(d.get('last_lap'))
                    if lap_time is not None and lap_time > 0:
                        state['history'].append(dict(lap=d['laps'], time=lap_time, clean=not state['lap_pit']))
                    state['lap_pit'] = bool(d.get('pit'))
                elif d['laps'] < prev['laps'] or d['laps'] > prev['laps'] + 1:
                    state['history'].clear()
                    state['last_pit_progress'] = None
            if d.get('radio'):
                state['radio'] = now
            history = list(state['history'])
            clean = [h['time'] for h in history if h['clean']][-5:]
            stint = None
            if pct_progress is not None and state['last_pit_progress'] is not None:
                stint = max(1, math.floor(pct_progress - state['last_pit_progress']) + 1)
            elif finite(state['first_lap']) is not None and state['first_lap'] <= 0 and finite(d.get('laps')) is not None:
                stint = d['laps'] + 1
            out = (d.get('pit') is False and pct_progress is not None and state['last_pit_progress'] is not None
                   and 0 <= pct_progress - state['last_pit_progress'] < 1)
            flags = d.get('flags')
            flags = flags if type(flags) is int else 0
            d.update(lap_difference=lap_relation(d, player) if race and player is not None else None,
                     pit_elapsed=now-state['entry'] if d.get('pit') and state['entry'] is not None else None,
                     pit_duration=state['last_pit_time'], pit_stop_duration=state['last_stop_time'],
                     last_pit_lap=state['last_pit_lap'], stint_lap=stint, out_lap=out,
                     average_lap=sum(clean)/len(clean) if clean else None, lap_history=history,
                     lap_deltas=[history[i]['time']-history[i-1]['time'] for i in range(1,len(history))][-3:],
                     radio_recent=state['radio'] is not None and now-state['radio'] < 3,
                     disqualified=bool(flags & 0x20000), penalty=bool(flags & 0x10000),
                     slowdown=bool(flags & 0x80000), repair=bool(flags & 0x100000), finished=bool(flags & 1),
                     started=bool(finite(d.get('laps')) is not None and d['laps'] > 0 or d.get('surface') == 3 and pct_progress is not None))
            state['previous'] = {k:d.get(k) for k in ('pit','surface','laps','pct')}
        groups = {}
        for d in drivers:
            groups.setdefault(d.get('class_id'), []).append(d)
        classes = []
        for class_id, group in groups.items():
            ordered = sorted(group, key=lambda d: (d.get('class_position') or d.get('position') or 10000, -(progress(d) or 0)))
            best = min((d['best_lap'] for d in group if finite(d.get('best_lap')) is not None and d['best_lap'] > 0), default=None)
            sof = strength_of_field([d.get('rating') for d in group if not d.get('ai')])
            estimates = rating_estimates(group) if race and (session_state is None or session_state >= 4) else {}
            leader = ordered[0]
            for index, d in enumerate(ordered):
                d['gap'], d['gap_laps'], d['gap_estimated'] = self.gap(leader, d, race)
                state=self.cars[d['id']]
                reference=(leader['id'],leader.get('user_id'),class_id,d['gap_laps'],d['gap_estimated'])
                previous=state.get('gap_observation')
                comparable=(finite(d['gap']) is not None and not d['gap_laps'] and not d.get('pit') and not leader.get('pit'))
                if not comparable or previous is None or previous['reference']!=reference:
                    state['gap_trend']=None
                    state['gap_until']=now
                    state['gap_observation']=dict(reference=reference,value=d['gap'],time=now) if comparable else None
                elif now-previous['time']>=.75:
                    difference=d['gap']-previous['value']
                    if abs(difference)>=.05:
                        state['gap_trend']='closing' if difference<0 else 'opening'
                        state['gap_until']=now+2
                    state['gap_observation']=dict(reference=reference,value=d['gap'],time=now)
                d['gap_trend']=state.get('gap_trend') if now<state.get('gap_until',now) else None
                d['interval'], d['interval_laps'], d['interval_estimated'] = self.gap(ordered[max(0,index-1)], d, race)
                d['class_sof'], d['class_size'] = sof, len(group)
                d['class_best'] = best
                d['class_fastest'] = best is not None and d.get('best_lap') == best
                d['irating_change'] = estimates.get(d['id'])
            classes.append(dict(id=class_id, name=leader.get('class_name'), color=leader.get('class_color'),
                                drivers=len(group), sof=sof, best_lap=best))
        return classes

    @staticmethod
    def gap(a, b, race):
        if a['id'] == b['id']:
            return 0, 0, False
        if not race:
            best_a, best_b = finite(a.get('best_lap')), finite(b.get('best_lap'))
            return (max(0,best_b-best_a),0,False) if best_a and best_b and min(best_a,best_b)>0 else (None,None,False)
        pa, pb = progress(a), progress(b)
        if pa is None or pb is None:
            return None, None, False
        distance = max(0,pa-pb)
        laps = math.floor(distance + 1e-6)
        if laps:
            return None, laps, False
        ta, tb = finite(a.get('f2_time')), finite(b.get('f2_time'))
        if ta is not None and tb is not None and 0 <= ta <= tb and (tb>ta or distance<1e-6):
            return tb-ta, 0, False
        duration = finite(b.get('class_lap_time'))
        return (distance*duration,0,True) if duration and duration>0 else (None,0,True)
