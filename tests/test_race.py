import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path

from irboard.race import RaceState, lap_relation, strength_of_field, rating_estimates
from irboard.records import LapRecords
from irboard.telemetry import LiveSource, LapState, Telemetry
from irboard.pit import validate_compound


def driver(index=0, **values):
    result=dict(id=index,user_id=100+index,car_id=1,class_id=1,class_name='GT3',class_color='#123456',
                class_lap_time=100,laps=10,pct=.5,pit=False,surface=3,position=index+1,class_position=index+1,
                best_lap=100,last_lap=101,rating=2000,flags=0)
    result.update(values)
    return result


class RaceTests(unittest.TestCase):
    def test_gap_trend_resets_for_missing_data_pits_leader_changes_and_sessions(self):
        state=RaceState()
        def step(now,gap=5,key='race',leader=0,**extra):
            rows=[driver(leader,position=1,class_position=1,f2_time=0,pct=.6),
                  driver(1,position=2,class_position=2,f2_time=gap,pct=.5,**extra)]
            state.update(key,now,rows,1,'Race',4)
            return rows[1]['gap_trend']
        self.assertIsNone(step(0))
        self.assertEqual(step(1,4),'closing')
        self.assertEqual(step(2,6),'opening')
        self.assertIsNone(step(5,6))
        self.assertIsNone(step(6,4,pit=True))
        self.assertIsNone(step(7,3))
        self.assertEqual(step(8,2),'closing')
        self.assertIsNone(step(9,1,key='new-session'))
        self.assertIsNone(step(10,1,pit=True))
        self.assertIsNone(step(11,2,laps=None))
        self.assertIsNone(step(12,2))
        self.assertEqual(step(13,1),'closing')
        self.assertIsNone(step(14,.5,leader=2))

    def test_lapping_uses_distance_and_wrap_not_just_completed_counter(self):
        own=driver(laps=10,pct=.99)
        self.assertEqual(lap_relation(driver(1,laps=11,pct=.01),own),0)
        self.assertEqual(lap_relation(driver(1,laps=10,pct=.01),own),-1)
        self.assertEqual(lap_relation(driver(1,laps=11,pct=.97),own),1)
        self.assertEqual(lap_relation(driver(1,laps=13,pct=.01),own),2)
        self.assertIsNone(lap_relation(driver(1,laps=None),own))

    def test_pit_elapsed_stationary_time_outlap_and_stint(self):
        state=RaceState()
        def step(now,**values):
            rows=[driver(**values)];state.update('race',now,rows,0,'Race',4);return rows[0]
        step(100)
        self.assertIsNone(step(110,pit=True,surface=2)['pit_duration'])
        self.assertEqual(step(115,pit=True,surface=1)['pit_elapsed'],5)
        step(120,pit=True,surface=1)
        step(125,pit=True,surface=1)
        out=step(130,laps=10,pct=.7)
        self.assertEqual(out['pit_duration'],20)
        self.assertEqual(out['pit_stop_duration'],10)
        self.assertTrue(out['out_lap'])
        self.assertEqual(out['stint_lap'],1)
        self.assertTrue(step(140,laps=11,pct=.2)['out_lap'])
        self.assertFalse(step(150,laps=11,pct=.8)['out_lap'])

    def test_joining_mid_pit_or_mid_stint_does_not_invent_history(self):
        state=RaceState();rows=[driver(pit=True,surface=1)]
        state.update('race',100,rows,0,'Race',4)
        self.assertIsNone(rows[0]['pit_elapsed'])
        self.assertIsNone(rows[0]['stint_lap'])
        rows=[driver(pct=.6)]
        state.update('race',110,rows,0,'Race',4)
        self.assertIsNone(rows[0]['pit_duration'])
        self.assertTrue(rows[0]['out_lap'])

    def test_session_rewind_and_driver_replacement_clear_observations(self):
        state=RaceState()
        state.update('a',100,[driver()],0,'Race',4)
        state.update('a',101,[driver(pit=True)],0,'Race',4)
        rows=[driver(user_id=999)]
        state.update('a',102,rows,0,'Race',4)
        self.assertIsNone(rows[0]['last_pit_lap'])
        rows=[driver()];state.update('b',103,rows,0,'Race',4)
        self.assertIsNone(rows[0]['pit_duration'])
        rows=[driver()];state.update('b',1,rows,0,'Race',4)
        self.assertIsNone(rows[0]['pit_duration'])

    def test_penalty_radio_and_unknown_track_location_are_not_dnf(self):
        state=RaceState();rows=[driver(flags=0x20000|0x10000|0x80000|0x100000,radio=True,surface=-1)]
        state.update('a',1,rows,0,'Race',4)
        self.assertTrue(all(rows[0][k] for k in ('disqualified','penalty','slowdown','repair','radio_recent')))
        rows=[driver(radio=False)];state.update('a',3,rows,0,'Race',4)
        self.assertTrue(rows[0]['radio_recent'])
        rows=[driver(radio=False)];state.update('a',5,rows,0,'Race',4)
        self.assertFalse(rows[0]['radio_recent'])
        self.assertFalse(rows[0]['disqualified'])

    def test_class_gap_interval_lap_deficit_and_practice_times(self):
        state=RaceState();rows=[driver(laps=12,pct=.2,f2_time=0),driver(1,laps=11,pct=.1,f2_time=2),
                                driver(2,class_id=2,class_position=1,f2_time=20),driver(3,class_id=2,class_position=2,f2_time=25)]
        classes=state.update('a',1,rows,0,'Race',4)
        self.assertEqual(len(classes),2)
        self.assertEqual(rows[1]['gap_laps'],1)
        self.assertEqual(rows[3]['gap'],5)
        self.assertEqual(rows[3]['interval'],5)
        self.assertFalse(rows[3]['gap_estimated'])
        self.assertEqual(RaceState.gap(driver(best_lap=100),driver(1,best_lap=102),'')[0],2)
        value,laps,estimated=RaceState.gap(driver(pct=.6,f2_time=0),driver(1,pct=.5,f2_time=0),True)
        self.assertAlmostEqual(value,10)
        self.assertTrue(estimated)

    def test_observed_lap_average_excludes_pit_laps_and_no_double_sampling(self):
        state=RaceState();state.update('a',1,[driver(laps=10)],0,'Race',4)
        rows=[driver(laps=11,last_lap=100)];state.update('a',2,rows,0,'Race',4)
        self.assertEqual(rows[0]['average_lap'],100)
        state.update('a',2,[driver(laps=11,last_lap=100)],0,'Race',4)
        state.update('a',3,[driver(laps=11,pit=True)],0,'Race',4)
        rows=[driver(laps=12,last_lap=150)];state.update('a',4,rows,0,'Race',4)
        self.assertEqual(rows[0]['average_lap'],100)
        self.assertEqual(len(rows[0]['lap_history']),2)

    def test_sof_and_provisional_rating_change(self):
        self.assertEqual(strength_of_field([2000,2000,None,0]),2000)
        self.assertIsNone(strength_of_field([None,0]))
        rows=[driver(started=True),driver(1,started=True)]
        changes=rating_estimates(rows)
        self.assertAlmostEqual(changes[0],50)
        self.assertAlmostEqual(changes[1],-49)
        self.assertEqual(rating_estimates([driver(ai=True,started=True)]),{})

    def test_local_record_persists_and_is_scoped_to_car_and_track(self):
        with tempfile.TemporaryDirectory() as directory:
            records=LapRecords(directory)
            key=(1,'Circuit',2,'car')
            self.assertEqual(records.observe(key,100),100)
            self.assertEqual(records.observe(key,110),100)
            self.assertEqual(LapRecords(directory).observe(key),100)
            self.assertIsNone(records.observe((2,'Other',2,'car')))
            self.assertEqual(records.observe(key,float('nan')),100)

    def test_compound_is_validated_before_any_command_is_sent(self):
        validate_compound([(0,0),(12,3)],{'compounds':[{'index':3}]})
        with self.assertRaises(ValueError):validate_compound([(0,0),(12,1)],{'compounds':[{'index':3}]})
        with self.assertRaises(ValueError):validate_compound([(0,0),(12,3)],{})


class SDK:
    is_initialized=True
    is_connected=True
    def __init__(self):
        self.frame={'SessionTime':10,'SessionNum':0,'IsOnTrack':True,'IsOnTrackCar':True,'PlayerCarIdx':0,
                    'DriverInfo':{'Drivers':[{'CarIdx':0,'CarID':1,'CarClassID':1,'UserID':100,'UserName':'Me'},
                                             {'CarIdx':1,'CarID':2,'CarClassID':1,'UserID':101,'UserName':'Other'}],
                                  'DriverTires':[{'TireIndex':3,'TireCompoundType':'Wet'}]},
                    'SessionInfo':{'Sessions':[{'SessionNum':0,'SessionType':'Race','ResultsPositions':[]}]},
                    'CarIdxLapCompleted':[10,10],'CarIdxLapDistPct':[.99,.01],'CarIdxPosition':[1,2],
                    'CarIdxClassPosition':[1,2],'CarIdxSessionFlags':[0,0x100000],
                    'CarIdxOnPitRoad':[False,True],'CarIdxTrackSurface':[3,2],
                    'CarIdxTireCompound':[3,3],'CarIdxP2P_Status':[False,True],'CarIdxP2P_Count':[-1,5],
                    'RadioTransmitCarIdx':1,'PitSvFlags':0,'dcABS':-3,'dcTractionControl2':0,
                    'Throttle':.5,'Brake':0,'Clutch':1,'LapCompleted':10,'LapDistPct':.99,
                    'LapBestLapTime':100,'LapDeltaToSessionBestLap':.2,'LapDeltaToSessionBestLap_OK':True,
                    'CustomChannel':float('nan')}
        self.frozen=False
    @property
    def var_headers_names(self):return list(self.frame)
    def __getitem__(self,key):return copy.deepcopy(self.frame.get(key))
    def freeze_var_buffer_latest(self):self.frozen=True
    def unfreeze_var_buffer_latest(self):self.frozen=False
    def shutdown(self):pass


class SDKCoverageTests(unittest.TestCase):
    def test_classification_compounds_signed_controls_and_full_inspector(self):
        sdk=SDK();data=LiveSource(sdk).read(include_raw=True)
        self.assertEqual(data['drivers'][1]['lap_difference'],-1)
        self.assertTrue(data['drivers'][1]['pit'])
        self.assertTrue(data['drivers'][1]['repair'])
        self.assertTrue(data['drivers'][1]['radio_recent'])
        self.assertEqual(data['drivers'][0]['compound'],'Wet')
        self.assertIsNone(data['drivers'][1]['compound'])
        self.assertEqual(data['drivers'][1]['compound_index'],3)
        self.assertEqual(data['drivers'][1]['p2p_count'],5)
        self.assertEqual(next(v['value'] for v in data['car']['systems'] if v['key']=='dcABS'),-3)
        self.assertIsNone(data['raw']['CustomChannel'])
        self.assertIn('Session.DriverInfo',data['raw'])
        json.dumps(data,allow_nan=False)
        self.assertFalse(sdk.frozen)

    def test_gt3_rival_compounds_and_practice_fuel_from_sdk(self):
        sdk = SDK()
        sdk.frame['SessionInfo']['Sessions'][0]['SessionType'] = 'Practice'
        for driver in sdk.frame['DriverInfo']['Drivers']:
            driver.update(CarClassShortName='GT3')
        sdk.frame['DriverInfo']['Drivers'][0]['CarScreenName'] = 'Aston Martin Vantage GT3'
        sdk.frame['DriverInfo']['DriverTires'] = [
            dict(TireIndex=0, TireCompoundType='Hard'), dict(TireIndex=1, TireCompoundType='Wet')]
        sdk.frame.update(CarIdxTireCompound=[0,1], Lap=1, LapCompleted=0,
                         LapDistPct=.5, FuelLevel=30, OnPitRoad=False, PlayerTrackSurface=3)
        import tempfile
        from pathlib import Path
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = LiveSource(sdk, map_directory=Path(temporary.name)/'tracks')
        data = source.read()
        self.assertEqual([d['compound'] for d in data['drivers']], ['Hard','Wet'])
        sdk.frame.update(SessionTime=11, Lap=2, LapCompleted=1, LapDistPct=0, FuelLevel=29)
        self.assertIsNone(source.read()['fuel']['average'])
        sdk.frame.update(SessionTime=61, LapDistPct=.5, FuelLevel=28)
        source.read()
        sdk.frame.update(SessionTime=111, Lap=3, LapCompleted=2, LapDistPct=0,
                         FuelLevel=27, LapLastLapTime=100)
        data = source.read()
        self.assertEqual(data['session']['type'], 'Practice')
        self.assertEqual(data['fuel']['samples'], [2])
        self.assertEqual(data['fuel']['status'], 'measured')
        self.assertTrue(data['history'][0]['clean'])

    def test_spectating_cannot_send_pit_even_when_the_car_physics_runs(self):
        sdk=SDK();sdk.frame['IsOnTrack']=False
        data=LiveSource(sdk).read()
        self.assertFalse(data['pit']['can_control'])
        self.assertFalse(data['car']['in_car'])

    def test_relative_follows_valid_camera_without_giving_it_pit_control(self):
        sdk=SDK();sdk.frame.update(IsOnTrack=False,CamCarIdx=1)
        source=LiveSource(sdk);data=source.read()
        self.assertEqual(data['session']['focus_idx'],1)
        self.assertEqual(data['drivers'][1]['relative'],0)
        self.assertTrue(data['drivers'][1]['focus'])
        self.assertFalse(data['pit']['can_control'])
        sdk.frame['CarIdxLapDistPct'][1]=-1
        self.assertEqual(source.read()['session']['focus_idx'],0)

    def test_delta_validity_input_history_and_out_of_car_controls(self):
        sdk=SDK();source=LiveSource(sdk)
        self.assertAlmostEqual(source.read()['car']['predicted_lap'],100.2)
        sdk.frame.update(SessionTime=11,LapDeltaToSessionBestLap_OK=False)
        data=source.read()
        self.assertIsNone(data['car']['delta'])
        self.assertIsNone(data['car']['predicted_lap'])
        self.assertEqual(len(data['input_trace']),2)
        sdk.frame.update(SessionTime=12,IsOnTrack=False)
        data=source.read()
        self.assertTrue(all(v['value'] is None for v in data['car']['systems']))
        sdk.frame['SessionTime']=1
        self.assertEqual(len(source.read()['input_trace']),0)

    def test_first_completed_lap_is_numbered_one(self):
        state=LapState();car=dict(lap=1,lap_completed=0,lap_pct=0,fuel=30,on_track=True,pit=False,incidents=0)
        state.update('a',car);car.update(lap=2,lap_completed=1,fuel=28,last_lap=100)
        state.update('a',car)
        self.assertEqual(state.history[0]['lap'],1)

    def test_offtrack_and_caution_laps_do_not_lower_the_fuel_average(self):
        for extra in [dict(surface=0),dict(session_flags=0x4000)]:
            state=LapState();car=dict(lap=1,lap_completed=0,lap_pct=0,fuel=30,on_track=True,pit=False,incidents=0)
            state.update('a',car);state.update('a',dict(car,**extra))
            car.update(lap=2,lap_completed=1,fuel=29,last_lap=100)
            self.assertIsNone(state.update('a',car)['average'])

    def test_queued_commands_are_cancelled_on_connection_failure(self):
        telemetry=Telemetry()
        task=dict(ready=threading.Event(),cancelled=threading.Event(),error=None)
        telemetry._commands.put(task)
        telemetry._fail_commands('Disconnected; plan not sent')
        self.assertTrue(task['ready'].is_set())
        self.assertTrue(task['cancelled'].is_set())
        self.assertIn('not sent',task['error'])

    def test_partial_session_metadata_is_a_valid_snapshot(self):
        sdk=SDK();sdk.frame['SessionInfo']={'Sessions':None};sdk.frame['DriverInfo']={'Drivers':None}
        data=LiveSource(sdk).read()
        self.assertEqual(data['drivers'],[])
        json.dumps(data,allow_nan=False)

if __name__=='__main__':unittest.main()
