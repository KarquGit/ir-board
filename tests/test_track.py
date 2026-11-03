import json
import math
from pathlib import Path
import tempfile
import unittest
from irboard.track import TrackRecorder, MapStore, SAMPLES


def car(pct,**extra):
    angle=pct*math.tau
    result=dict(on_track=True,pit=False,garage=False,replay=False,surface=3,speed=35,
                lap_pct=pct,lat=50+math.sin(angle)*.0012,lon=20+math.cos(angle)*.002)
    result.update(extra);return result


def drive(recorder,key=(123,'Personal SDK line',1000),start=.8,steps=1050):
    result=None
    for i in range(steps):result=recorder.update(key,car((start+i/600)%1),i*.1)
    return result


class LearnedTrackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=MapStore(self.temp.name);self.recorder=TrackRecorder(self.store)
    def test_complete_lap_learns_own_gps_and_persists(self):
        result=drive(self.recorder)
        self.assertEqual(result['status'],'ready');self.assertEqual(result['source'],'sdk-gps')
        self.assertEqual(len(result['points']),SAMPLES)
        self.assertTrue(all(all(math.isfinite(v) for v in point) for point in result['points']))
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))),1)
        fresh=TrackRecorder(self.store)
        self.assertEqual(fresh.update((123,'Personal SDK line',1000),car(.5),5)['points'],result['points'])
    def test_partial_lap_and_stationary_gps_never_fabricate_map(self):
        self.assertNotEqual(drive(self.recorder,steps=300)['status'],'ready')
        other=TrackRecorder(self.store)
        for i in range(1200):result=other.update((7,'Static sensor',1000),car((i/600)%1,lat=50,lon=20),i*.1)
        self.assertNotEqual(result['status'],'ready')
    def test_pits_missing_gps_and_teleports_restart_recording(self):
        for invalid in [dict(pit=True),dict(on_track=False),dict(replay=True),dict(lat=None),dict(surface=0),dict(lat=80,lon=100)]:
            recorder=TrackRecorder(self.store)
            drive(recorder,steps=500)
            recorder.update((123,'Personal SDK line',1000),car(.65,**invalid),50)
            self.assertFalse(recorder.recording)
            self.assertIsNone(recorder.learned)
    def test_first_full_lap_from_start_line_and_small_backwards_jitter(self):
        key=(9,'Start line',1000)
        for i in range(601):
            pct=(i/600)%1
            result=self.recorder.update(key,car(pct),i*.1)
            if i == 200:
                self.recorder.update(key,car(pct-.0001),i*.1+.01)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(len(result['points']),SAMPLES)

    def test_different_layout_does_not_reuse_other_tracks_geometry(self):
        drive(self.recorder)
        result=self.recorder.update((456,'Different',2000),car(.2),110)
        self.assertNotEqual(result['status'],'ready');self.assertEqual(result['points'],[])
    def test_live_motion_without_gps_learns_and_persists_approximate_line(self):
        key=(8,'Motion telemetry',1256)
        for i in range(1050):
            pct=(.8+i/600)%1
            sample=car(pct,lat=None,lon=None,yaw=pct*math.tau+math.pi/2,
                       velocity_x=math.tau*200/60,velocity_y=0)
            result=self.recorder.update(key,sample,i*.1)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['source'],'sdk-motion')
        self.assertEqual(len(result['points']),SAMPLES)
        xs=[p[0] for p in result['points']]
        self.assertAlmostEqual(max(xs)-min(xs),400,delta=2)
        restored=TrackRecorder(self.store).update(key,{},0)
        self.assertEqual(restored['source'],'sdk-motion')
        self.assertEqual(restored['points'],result['points'])

    def test_missing_motion_and_interrupted_samples_do_not_invent_a_map(self):
        key=(8,'Motion telemetry',1256)
        for i in range(500):
            pct=(.8+i/600)%1
            self.recorder.update(key,car(pct,lat=None,lon=None,yaw=pct*math.tau,
                                       velocity_x=20,velocity_y=0),i*.1)
        self.assertTrue(self.recorder.recording)
        self.recorder.update(key,car(.7,lat=None,lon=None),50)
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.learned)
    def test_untrusted_or_corrupted_saved_data_is_not_loaded(self):
        key=(1,'Local',1000);self.store.path(key).write_text(json.dumps(dict(format=1,source='third-party',track=list(key),points=[[0,0]]*600)))
        self.assertIsNone(self.store.load(key))
        self.store.path(key).write_text('not json');self.assertIsNone(self.store.load(key))

    def test_saved_map_stays_visible_and_is_replaced_after_each_clean_lap(self):
        key=(91,'Repeated clean laps',1000)
        for i in range(601):
            first=self.recorder.update(key,car((i/600)%1,incidents=0),i*.1)
        original=first['points']
        self.assertEqual(first['status'],'ready')
        for i in range(601,1201):
            pct=(i/600)%1
            result=self.recorder.update(key,car(pct,lat=50+math.sin(pct*math.tau)*.0018,incidents=0),i*.1)
            self.assertEqual(result['status'],'ready')
            if i<1200:self.assertEqual(result['points'],original)
        self.assertNotEqual(result['points'],original)
        self.assertEqual(self.store.load(key)['points'],result['points'])
        self.assertTrue(result['updating'])
        restored=TrackRecorder(self.store)
        for i in range(601):
            pct=(i/600)%1
            updated=restored.update(key,car(pct,lat=50+math.sin(pct*math.tau)*.0008,incidents=0),i*.1)
            self.assertEqual(updated['status'],'ready')
        self.assertNotEqual(updated['points'],result['points'])
        self.assertEqual(self.store.load(key)['points'],updated['points'])

    def test_incident_lap_keeps_previous_map_then_next_clean_lap_updates_it(self):
        key=(92,'Incident lap',1000)
        for i in range(601):
            first=self.recorder.update(key,car((i/600)%1,incidents=0),i*.1)
        for i in range(601,1801):
            pct=(i/600)%1
            result=self.recorder.update(key,car(pct,lat=50+math.sin(pct*math.tau)*.0018,incidents=int(i>=900)),i*.1)
            if i<1800:self.assertEqual(result['points'],first['points'])
        self.assertNotEqual(result['points'],first['points'])
        self.assertEqual(self.store.load(key)['points'],result['points'])

if __name__=='__main__':unittest.main()
