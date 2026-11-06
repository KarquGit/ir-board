import json
import ctypes
import platform
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from irboard.buttonbox import ButtonBox, WindowsKeys, KEYS, DEFAULT_KEYS, LEASE_SECONDS, TAP_SECONDS, RETIRED_SECONDS, MAX_RETIRED, read_states, validate
from irboard.layout import LayoutStore
from irboard.server import create_server
from irboard.telemetry import Telemetry


class FakeKeys:
    supported = True
    def __init__(self):
        self.focus = True
        self.events = []
    def focused(self):
        return self.focus
    def key(self, key, down):
        self.events.append((key, down))


def command(action='ignition', key='F13', phase='tap', press_id='unique-button-123456'):
    return dict(action=action,key=key,phase=phase,press_id=press_id)


class ButtonBoxTests(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.sink = FakeKeys()
        self.box = ButtonBox(sink=self.sink,clock=lambda:self.now[0])
        self.addCleanup(self.box.stop)

    def test_schema_allows_only_named_actions_keys_and_phases(self):
        self.assertEqual(list(DEFAULT_KEYS.values()),[f'F{i}' for i in range(13,25)])
        for key in KEYS:
            validate(command(key=key))
        for invalid in [None,{},command(action=[]),command(key=['F13']),command(key='CTRL+A'),command(key='ENTER'),
                        command(action='arbitrary-key'),command(phase='down'),command(action='starter',phase='tap'),
                        command(press_id='short'),dict(command(),unexpected=True)]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.box.submit(invalid)
        self.assertEqual(self.sink.events,[])

    def test_tap_gets_key_up_after_deadline_and_never_auto_repeats(self):
        self.box.submit(command())
        self.assertEqual(self.sink.events,[('F13',True)])
        self.now[0] = TAP_SECONDS + .01
        with self.box.lock:self.box._expire()
        self.assertEqual(self.sink.events,[('F13',True),('F13',False)])
        self.assertFalse(self.box.presses)

    def test_hold_heartbeat_extends_lease_and_lost_client_releases(self):
        payload=command(action='starter',key='F14',phase='down')
        self.box.submit(payload)
        self.now[0] = LEASE_SECONDS - .1
        self.box.submit(dict(payload,phase='keepalive'))
        self.now[0] = LEASE_SECONDS + .1
        with self.box.lock:self.box._expire()
        self.assertEqual(self.sink.events,[('F14',True)])
        self.now[0] += LEASE_SECONDS
        with self.box.lock:self.box._expire()
        self.assertEqual(self.sink.events,[('F14',True),('F14',False)])
        with self.assertRaises(RuntimeError):self.box.submit(dict(payload,phase='keepalive'))
        self.assertEqual(len(self.sink.events),2)

    def test_release_before_delayed_down_cannot_start_a_hold(self):
        payload=command(action='starter',key='F14',phase='up')
        self.box.submit(payload)
        with self.assertRaises(RuntimeError):self.box.submit(dict(payload,phase='down'))
        self.assertFalse(self.box.presses)
        self.assertEqual(self.sink.events,[])

    def test_expired_press_cannot_be_resurrected_and_completed_cache_is_bounded(self):
        payload=command(action='starter',key='F14',phase='down')
        self.box.submit(payload)
        self.now[0]=LEASE_SECONDS+.1
        with self.box.lock:self.box._expire()
        with self.assertRaises(RuntimeError):self.box.submit(payload)
        self.assertEqual(self.sink.events,[('F14',True),('F14',False)])
        for index in range(MAX_RETIRED+20):
            self.box.submit(dict(payload,phase='up',press_id=f'press-up-{index:08d}'))
        self.assertEqual(len(self.box.retired),MAX_RETIRED)
        self.now[0]+=RETIRED_SECONDS+.1
        with self.box.lock:self.box._expire()
        self.assertFalse(self.box.retired)

    def test_focus_loss_releases_existing_hold_and_refuses_new_press(self):
        payload=command(action='radio',key='F18',phase='down')
        self.box.submit(payload)
        self.sink.focus=False
        with self.box.lock:self.box._expire()
        self.assertEqual(self.sink.events,[('F18',True),('F18',False)])
        with self.assertRaises(RuntimeError):self.box.submit(command())
        self.assertEqual(len(self.sink.events),2)

    def test_release_allowed_when_telemetry_disconnected(self):
        payload=command(action='starter',key='F14',phase='down')
        self.box.submit(payload)
        self.box.submit(dict(payload,phase='up'),ready=False)
        self.box.submit(dict(payload,phase='up'),ready=False)
        self.assertEqual(self.sink.events,[('F14',True),('F14',False)])
        with self.assertRaises(RuntimeError):self.box.submit(command(),ready=False)

    def test_press_owner_binding_collision_and_expired_heartbeat_are_rejected(self):
        payload=command(action='radio',key='F18',phase='down')
        self.box.submit(payload,owner='tablet-a')
        for altered in [dict(payload,key='F19'),dict(payload,action='starter')]:
            with self.assertRaises(ValueError):self.box.submit(dict(altered,phase='up'),owner='tablet-a')
        with self.assertRaises(ValueError):self.box.submit(dict(payload,phase='up'),owner='tablet-b')
        with self.assertRaises(RuntimeError):self.box.submit(command(key='F18',press_id='another-unique-123456'))
        self.assertEqual(self.sink.events,[('F18',True)])
        self.box.stop()
        self.assertEqual(self.sink.events,[('F18',True),('F18',False)])
        with self.assertRaises(RuntimeError):self.box.submit(command())

    def test_real_watchdog_releases_without_browser(self):
        real = ButtonBox(sink=self.sink)
        try:
            real.submit(command(action='starter',key='F14',phase='down'))
            deadline=time.monotonic()+1.5
            while real.presses and time.monotonic()<deadline:time.sleep(.02)
            self.assertFalse(real.presses)
            self.assertEqual(self.sink.events,[('F14',True),('F14',False)])
        finally:real.stop()

    def test_demo_updates_simulated_states_without_any_os_events(self):
        demo=ButtonBox(demo=True,sink=self.sink)
        try:
            result=demo.submit(command())
            self.assertEqual(result['status'],'demo')
            self.assertFalse(demo.demo_states['ignition'])
            demo.submit(command(action='abs_up',key='F24',press_id='abs-unique-123456'))
            self.assertEqual(demo.demo_states['abs'],5)
            self.assertEqual(self.sink.events,[])
        finally:demo.stop()

    def test_sdk_state_never_guesses_missing_switches_or_out_of_car_values(self):
        source=dict(EngineWarnings=0x10,dcBrakeBias=54.2,dcABS=4,dcTractionControl=3,dcWiper=0)
        state=read_states(source.get,dict(in_car=True,pit_limiter=True))
        self.assertIsNone(state['ignition'])
        self.assertTrue(state['pit_limiter'])
        self.assertFalse(state['wipers'])
        self.assertEqual(state['bias'],54.2)
        source.update(dcIgnition=True,dcWiper=2,dcABS=float('nan'))
        state=read_states(source.get,dict(in_car=True,pit_limiter=False))
        self.assertTrue(state['ignition'])
        self.assertTrue(state['wipers'])
        self.assertIsNone(state['abs'])
        state=read_states(source.get,dict(in_car=False,pit_limiter=True))
        for key in ('ignition','pit_limiter','wipers','bias','abs','tc'):self.assertIsNone(state[key])

    @unittest.skipUnless(platform.system()=='Windows','Native Windows ABI check')
    def test_native_sendinput_abi_and_scan_code_flags_without_sending_real_keys(self):
        sink=WindowsKeys()
        expected=40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28
        self.assertEqual(ctypes.sizeof(sink.Input),expected)
        events=[]
        def send(count,pointer,size):
            event=ctypes.cast(pointer,ctypes.POINTER(sink.Input)).contents
            events.append((count,size,event.type,event.ki.wVk,event.ki.wScan,event.ki.dwFlags))
            return 1
        with patch.object(sink,'focused',return_value=True), \
             patch.object(sink.user32,'GetForegroundWindow',return_value=16), \
             patch.object(sink.user32,'GetWindowThreadProcessId',return_value=42), \
             patch.object(sink.user32,'GetKeyboardLayout',return_value=None), \
             patch.object(sink.user32,'MapVirtualKeyExW',return_value=0x64), \
             patch.object(sink.user32,'SendInput',side_effect=send):
            sink.key('F13',True)
            sink.key('F13',False)
        self.assertEqual(events,[(1,expected,1,0,0x64,0x8),(1,expected,1,0,0x64,0xa)])

    def test_snapshot_only_advertises_ready_supported_controls_and_copies_demo(self):
        telemetry=Telemetry(demo=True)
        try:
            self.assertFalse(telemetry.snapshot()['buttonbox']['available'])
            telemetry._data.update(connected=True)
            self.assertTrue(telemetry.snapshot()['buttonbox']['available'])
            telemetry.submit_buttonbox(command())
            state=telemetry.snapshot()['buttonbox']
            self.assertFalse(state['ignition']);self.assertEqual(state['source'],'demo')
            telemetry._data['timestamp']=time.time()-5
            self.assertFalse(telemetry.snapshot()['buttonbox']['available'])
        finally:telemetry.stop()


class ButtonBoxHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.telemetry=Telemetry(demo=True)
        self.telemetry._data.update(connected=True)
        self.server=create_server('127.0.0.1',0,self.telemetry,layout_store=LayoutStore(Path(self.temp.name)/'layout.json'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.telemetry.stop();self.temp.cleanup()
    def request(self,payload,origin=None,cookie=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        if cookie:headers['Cookie']=cookie
        return urlopen(Request(self.base+'/api/buttonbox',data=json.dumps(payload).encode(),headers=headers),timeout=3)
    def test_authenticated_same_origin_demo_and_bad_payload(self):
        with self.request(command(),origin=self.base) as response:
            self.assertEqual(json.load(response)['status'],'demo')
        with self.assertRaises(HTTPError) as error:self.request(command(key='CTRL+ALT+DELETE'))
        self.assertEqual(error.exception.code,400)
        with self.assertRaises(HTTPError) as error:self.request(command(),origin='http://evil.example')
        self.assertEqual(error.exception.code,403)
    def test_remote_control_requires_pairing_cookie(self):
        with patch('irboard.server.local_client',return_value=False):
            with self.assertRaises(HTTPError) as error:self.request(command())
            self.assertEqual(error.exception.code,401)
            code=self.server.pairing.issue()
            session=self.server.pairing.exchange(code,'test-tablet')
            cookie=self.server.pairing.cookie(session)
            with self.request(command(),cookie=cookie) as response:
                self.assertEqual(json.load(response)['status'],'demo')
