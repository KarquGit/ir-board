import json
import math
from pathlib import Path
import tempfile
import unittest

from irboard.coaching import CoachingRecorder, ReferenceStore, sector_layout
from irboard.track import SAMPLES


def sample(pct,incidents=0):
    return dict(lap_pct=pct,on_track=True,pit=False,replay=False,garage=False,surface=3,
                incidents=incidents,session_flags=0,speed=35,brake=max(0,-math.sin(pct*math.tau*4)),throttle=.5,
                lat=50+math.sin(pct*math.tau)*.0012,lon=20+math.cos(pct*math.tau)*.002)


def lap(recorder,duration,base=0,incident=False,key=('track','car')):
    for i in range(201):
        car=sample((i/200)%1,int(incident and i>=80))
        result=recorder.update('session',key,car,base+duration*i/200)
    return result


def sector_lap(times,radius=100):
    total=sum(times)
    points=[[radius*math.cos(i/SAMPLES*math.tau),radius*math.sin(i/SAMPLES*math.tau)] for i in range(SAMPLES)]
    rows=[]
    for i in range(SAMPLES+1):
        pct=i/SAMPLES;sector=min(len(times)-1,int(pct*len(times)))
        elapsed=sum(times[:sector])+(pct*len(times)-sector)*times[sector]
        rows.append(dict(pct=pct,time=elapsed))
    return dict(points=points,lap_time=total,source='sdk-gps',origin=[50,20]),dict(lap_time=total,samples=rows)


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ReferenceStore(Path(self.temp.name)/'coaching')
        self.recorder=CoachingRecorder(self.store)
    def test_sector_metadata_keeps_all_sdk_sections_and_never_invents_three(self):
        layout=sector_layout({'Sectors':[{'SectorNum':i,'SectorStartPct':i/7} for i in range(7)]})
        self.assertEqual(len(layout),7);self.assertEqual(layout[-1]['end'],1)
        self.assertEqual([row['number'] for row in layout],list(range(1,8)))
        for bad in [None,{}, {'Sectors':[]},{'Sectors':[{'SectorNum':0,'SectorStartPct':.1}]},
                    {'Sectors':[{'SectorNum':0,'SectorStartPct':0}]*2}]:
            self.assertEqual(sector_layout(bad),[])
    def test_clean_references_best_previous_and_restart_car_isolation(self):
        first=lap(self.recorder,100)
        self.assertEqual(len(first['laps']),1)
        self.assertAlmostEqual(self.recorder.personal['lap_time'],100)
        lap(self.recorder,120,100)
        self.assertAlmostEqual(self.recorder.personal['lap_time'],100)
        self.assertAlmostEqual(self.recorder.last['lap_time'],120)
        lap(self.recorder,90,220)
        self.assertAlmostEqual(self.recorder.personal['lap_time'],90)
        restored=CoachingRecorder(self.store)
        data=restored.update('new-session',('track','car'),sample(.5),0)
        self.assertTrue(data['references']['personal']);self.assertIsNone(data['references']['session'])
        self.assertEqual(data['trace'],[])
        other=restored.update('new-session',('track','other-car'),sample(.5),1)
        self.assertFalse(other['references']['personal']);self.assertIsNone(restored.best)
    def test_incident_partial_lap_replay_and_gap_keep_saved_reference(self):
        lap(self.recorder,100)
        lap(self.recorder,90,100,incident=True)
        self.assertAlmostEqual(self.recorder.personal['lap_time'],100)
        result=self.recorder.update('session',('track','car'),dict(sample(.1),replay=True),200)
        self.assertEqual(result['trace'],[])
        self.assertTrue(result['references']['personal'])
        self.recorder.update('session',('track','car'),sample(.3),205)
        self.recorder.update('session',('track','car'),sample(.31),210)
        self.assertIsNone(self.recorder.started)
    def test_corrupt_saved_trace_is_not_loaded(self):
        lap(self.recorder,100)
        path=self.store.path(('track','car'));value=json.loads(path.read_text())
        value['samples'][5]['time']=float('nan');path.write_text(json.dumps(value))
        self.assertIsNone(self.store.load(('track','car')))


if __name__=='__main__':unittest.main()
