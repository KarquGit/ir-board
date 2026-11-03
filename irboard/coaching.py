"""Experimental lap references from continuous clean telemetry, not track assets."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .track import finite


def sector_layout(info):
    rows = info.get('Sectors') if isinstance(info, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict): return []
        start, index = row.get('SectorStartPct'), row.get('SectorNum')
        if not finite(start) or not 0 <= start < 1 or type(index) is not int or index < 0:
            return []
        result.append(dict(number=index+1, start=start))
    result.sort(key=lambda row: row['start'])
    if result[0]['start'] != 0 or len({row['start'] for row in result}) != len(result) or len({row['number'] for row in result}) != len(result):
        return []
    return [dict(row, end=result[i+1]['start'] if i+1 < len(result) else 1) for i, row in enumerate(result)]


class ReferenceStore:
    def __init__(self, directory): self.directory = Path(directory)
    def path(self, key):
        return self.directory/(hashlib.sha256(json.dumps(key).encode()).hexdigest()+'.json')
    def load(self, key):
        try:
            path = self.path(key)
            if path.stat().st_size > 400000: return None
            value = json.loads(path.read_text(encoding='utf-8'))
            samples, duration = value.get('samples'), value.get('lap_time')
            if value.get('key') != list(key) or value.get('format') != 1 or not finite(duration) or not 1 < duration < 86400:
                return None
            if not isinstance(samples, list) or not 40 <= len(samples) <= 1500: return None
            for row in samples:
                if not isinstance(row, dict) or not finite(row.get('pct')) or not 0 <= row['pct'] <= 1 or not finite(row.get('time')) or not 0 <= row['time'] <= duration:
                    return None
                for field, high in [('brake',1),('throttle',1),('speed',200)]:
                    if row.get(field) is not None and (not finite(row[field]) or not 0 <= row[field] <= high): return None
            if samples[0]['pct'] != 0 or samples[-1]['pct'] != 1 or samples[0]['time'] != 0 or samples[-1]['time'] != duration: return None
            if any(not 0 < b['pct']-a['pct'] <= .035 or b['time'] < a['time'] for a,b in zip(samples,samples[1:])): return None
            return value
        except (OSError, ValueError, TypeError, KeyError, AttributeError): return None
    def save(self, key, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(value, key=list(key), format=1), stream, allow_nan=False, separators=(',',':'))
            os.replace(temporary, self.path(key))
        finally:
            if temporary: temporary.unlink(missing_ok=True)


class CoachingRecorder:
    def __init__(self, store):
        self.store = store
        self.session_key = self.record_key = None
        self.personal = self.best = self.last = None
        self.reset_attempt()
    def reset_attempt(self):
        self.previous = None
        self.started = None
        self.trace = []
    @staticmethod
    def sample(car):
        return {name: car.get(name) if finite(car.get(name)) and 0 <= car[name] <= high else None
                for name,high in [('brake',1),('throttle',1),('speed',200)]}
    def snapshot(self, now, message=None):
        ready = self.best is not None or self.personal is not None
        references, laps = {}, {}
        for name,value in [('session',self.best),('personal',self.personal),('last',self.last)]:
            identifier = hashlib.sha256(json.dumps([self.record_key,value['lap_time']]).encode()).hexdigest() if value else None
            references[name] = identifier
            if value: laps[identifier] = dict(id=identifier, lap_time=value['lap_time'], samples=value['samples'])
        return dict(status='ready' if ready else 'recording' if self.started is not None else 'waiting',
                    message=message or ('Best clean references are available.' if ready else 'Cross start/finish and complete a continuous clean lap to record a reference.'),
                    current_time=now-self.started if self.started is not None else None,
                    trace=self.trace[:], references=references, laps=laps)
    def update(self, session_key, record_key, car, now):
        if record_key != self.record_key:
            self.record_key = record_key
            self.personal = self.store.load(record_key)
            self.session_key = None
        if session_key != self.session_key:
            self.session_key = session_key
            self.best = self.last = None
            self.reset_attempt()
        pct, incidents = car.get('lap_pct'), car.get('incidents')
        eligible = car.get('on_track') and not any(car.get(field) for field in ('pit','garage','replay')) and car.get('surface',3) in (None,3)
        eligible = eligible and not (car.get('session_flags',0) or 0) & 0xC118 and finite(incidents)
        if not eligible or not finite(pct) or not 0 <= pct < 1 or not finite(now):
            self.reset_attempt()
            return self.snapshot(now, 'A continuous clean on-track lap and incident data are required; saved references are retained.')
        sample = self.sample(car)
        previous = self.previous
        current = dict(sample, pct=pct, at=now, incidents=incidents)
        self.previous = current
        if previous is None:
            if pct <= .000001:
                self.started = now
                self.trace = [dict(sample, pct=0, time=0)]
            return self.snapshot(now)
        dt = now-previous['at']
        if dt == 0 or -.002 < pct-previous['pct'] < 0:
            self.previous = previous
            return self.snapshot(now)
        delta = (pct-previous['pct']) % 1
        if dt < 0 or dt > 2 or delta > .035 or incidents != previous['incidents']:
            self.reset_attempt()
            return self.snapshot(now, 'Lap recording interrupted; the previous clean reference is retained.')
        if previous['pct'] > .9 and pct < .1:
            mix = (1-previous['pct'])/(delta or 1)
            crossing_time = previous['at']+mix*dt
            crossing = {name: previous[name]+mix*(sample[name]-previous[name]) if sample[name] is not None and previous[name] is not None else None for name in sample}
            if self.started is not None and len(self.trace) >= 40 and self.trace[-1]['pct'] > .965:
                duration = crossing_time-self.started
                if 1 < duration < 86400:
                    value = dict(lap_time=duration, samples=self.trace+[dict(crossing,pct=1,time=duration)])
                    self.last = value
                    if self.best is None or duration < self.best['lap_time']-.001: self.best = value
                    if self.personal is None or duration < self.personal['lap_time']-.001:
                        self.personal = value
                        try: self.store.save(record_key, value)
                        except OSError:
                            self.started = crossing_time
                            self.trace = [dict(crossing,pct=0,time=0)]
                            return self.snapshot(now, 'Clean reference is available in memory, but could not be saved to disk.')
            self.started = crossing_time
            self.trace = [dict(crossing,pct=0,time=0)]
        if self.started is not None and pct > self.trace[-1]['pct']+.0008:
            self.trace.append(dict(sample,pct=pct,time=now-self.started))
        return self.snapshot(now)
