"""Restart restores references, without reviving a previous live session."""
import tempfile
from pathlib import Path
import unittest

from irboard.records import FuelRecords
from irboard.telemetry import LapState
from irboard.coaching import ReferenceStore, CoachingRecorder
from test_coaching import sample, lap


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_fuel_restart_is_historical_and_live_state_is_empty(self):
        store = FuelRecords(self.root/'fuel')
        state = LapState(store)
        car = dict(sample(0),lap_completed=0,fuel=20,last_lap=100)
        state.update('old', car, ('track-layout','car'))
        state.update('old', dict(car,lap_completed=1,fuel=17), ('track-layout','car'))
        restored = LapState(FuelRecords(store.directory))
        result = restored.update('new',dict(car,lap_pct=.5,fuel=10),('track-layout','car'))
        self.assertEqual(result['average'],3)
        self.assertTrue(result['historical'])
        self.assertIsNone(result['last'])
        self.assertFalse(restored.clean)
        self.assertEqual(list(restored.history),[])
        self.assertEqual(list(restored.consumption),[])
        for key in [('other-layout','car'),('track-layout','other-car')]:
            self.assertIsNone(restored.update(str(key),car,key)['average'])
        store.path(('track-layout','car')).write_text('{broken')
        self.assertEqual(store.load(('track-layout','car')),[])
        store.path(('track-layout','car')).write_text('[]')
        self.assertEqual(store.load(('track-layout','car')),[])

    def test_coaching_corrupt_top_level_and_layout_isolation(self):
        store = ReferenceStore(self.root/'coach')
        recorder = CoachingRecorder(store)
        lap(recorder,100,key=('layout','car'))
        restarted = CoachingRecorder(store)
        data = restarted.update('new',('layout','car'),dict(sample(.5),replay=True),0)
        self.assertIsNotNone(data['references']['personal'])
        self.assertIsNone(data['references']['session'])
        self.assertEqual(data['trace'],[])
        self.assertIsNone(restarted.update('new',('other-layout','car'),sample(.5),1)['references']['personal'])
        store.path(('layout','car')).write_text('[]')
        self.assertIsNone(store.load(('layout','car')))


