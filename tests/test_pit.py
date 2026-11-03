import threading
import unittest
from irboard.pit import commands, read_pit, read_compounds, fuel_capacity
from irboard.telemetry import Telemetry, empty

class PitTests(unittest.TestCase):
    def test_sdk_tire_compound_field_and_restricted_tank(self):
        self.assertEqual(read_compounds({'DriverTires':[
            {'TireIndex':0,'TireCompoundType':'Hard'},
            {'TireIndex':1,'TireCompoundType':'Wet'}]}),
            [{'index':0,'name':'Hard'},{'index':1,'name':'Wet'}])
        self.assertEqual(fuel_capacity({'DriverCarFuelMaxLtr':100,'DriverCarMaxFuelPct':.6}),60)
        self.assertIsNone(fuel_capacity({}))
    def test_compound_names_and_indices_come_from_session(self):
        self.assertEqual(read_compounds({'DriverTires': [
            {'TireIndex': 3, 'CompoundType': 'Wet'},
            {'TireIndex': 1, 'CompoundType': 'Dry'},
            {'TireIndex': True, 'CompoundType': 'Invalid'},
            {'TireIndex': 2}, None]}),
            [{'index': 1, 'name': 'Dry'}, {'index': 3, 'name': 'Wet'}])
        self.assertEqual(read_compounds({}), [])
        self.assertEqual(read_compounds({'DriverTires': None}), [])
    def test_all_sdk_services(self):
        self.assertEqual(commands(dict(tires=dict(lf=160,rf=161,lr=0,rr=165),fuel=42,windshield=True,fast_repair=True,compound=1)),
                         [(0,0),(3,160),(4,161),(5,0),(6,165),(2,42),(1,0),(8,0),(12,1)])
    def test_clear_plan(self):
        self.assertEqual(commands({}),[(0,0)])
    def test_sdk_service_status_readback(self):
        values = {'PitSvFlags': 17, 'PitSvStatus': 2, 'PlayerCarPitSvStatus': 100}
        pit = read_pit(values.get, {}, True)
        self.assertEqual(pit['status'], 2)
        self.assertTrue(pit['can_control'])
        values.pop('PitSvStatus')
        self.assertEqual(read_pit(values.get, {}, True)['status'], 100)
    def test_invalid_never_sends(self):
        for plan in [{'fuel':-1},{'fuel':True},{'fuel':5.5},{'fuel':1000},{'tires':{'lf':20}},{'tires':{'xx':0}},{'compound':-1},{'windshield':'yes'},[],{'x':1}]:
            with self.subTest(plan=plan),self.assertRaises(ValueError):commands(plan)
    def test_offline_and_missing_capability(self):
        t=Telemetry()
        with self.assertRaises(RuntimeError):t.submit_pit({})
        p=read_pit(lambda key,default=None:default,{},True)
        self.assertFalse(p['can_control'])
    def test_demo_never_queues(self):
        t=Telemetry(demo=True);t._data.update(connected=True,pit={'can_control':True})
        self.assertEqual(t.submit_pit({'fuel':5})['status'],'demo')
        self.assertTrue(t._commands.empty())
    def test_queue_owner_sends_and_rejects_changed_session(self):
        t=Telemetry();sent=[]
        class SDK:
            def pit_command(self,mode,value):sent.append((mode,value));return 1
        class Source:sdk=SDK()
        task=dict(batch=commands({'fuel':5}),ready=threading.Event(),cancelled=threading.Event(),error=None,session=(239,20,None))
        t._commands.put(task)
        data=empty();data.update(connected=True,pit={'can_control':True},session={'track_id':239,'time':21})
        t._drain_commands(Source(),data);self.assertEqual(sent,[(0,0),(2,5)]);self.assertTrue(task['ready'].is_set())
        task['session']=(1,0,None);t._commands.put(task);sent.clear();t._drain_commands(Source(),data)
        self.assertEqual(sent,[]);self.assertIsNotNone(task['error'])
    def test_cancelled_request_never_sends(self):
        t=Telemetry()
        class Source:sdk=None
        task=dict(batch=[(0,0)],ready=threading.Event(),cancelled=threading.Event(),error=None,session=(239,0,None));task['cancelled'].set();t._commands.put(task)
        t._drain_commands(Source(),empty());self.assertTrue(task['ready'].is_set())

if __name__=='__main__':unittest.main()
