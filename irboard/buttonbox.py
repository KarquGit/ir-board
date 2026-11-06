"""Allowlisted button-box keys, limited to the foreground iRacing simulator.

An expiring lease releases held keys when a tablet disconnects. A successful key
send is not an acknowledgement that the simulator accepted the assigned control.
"""
import ctypes
import math
import ntpath
import platform
import re
import threading
import time

ACTIONS = ('ignition', 'starter', 'pit_limiter', 'flash', 'wipers', 'radio',
           'bias_down', 'bias_up', 'tc_down', 'tc_up', 'abs_down', 'abs_up')
DEFAULT_KEYS = dict(zip(ACTIONS, (f'F{i}' for i in range(13, 25))))
HOLD_ACTIONS = frozenset(('starter', 'radio'))
KEYS = frozenset([*(f'F{i}' for i in range(1, 25)), *'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'])
LEASE_SECONDS = .9
TAP_SECONDS = .065
RETIRED_SECONDS = 10
MAX_RETIRED = 256


def validate(payload):
    if not isinstance(payload, dict) or set(payload) - {'action', 'key', 'phase', 'press_id'}:
        raise ValueError('Invalid button-box command')
    action, key, phase, press_id = (payload.get(k) for k in ('action', 'key', 'phase', 'press_id'))
    if not isinstance(action, str) or action not in ACTIONS:
        raise ValueError('Unknown button-box action')
    if not isinstance(key, str) or key not in KEYS:
        raise ValueError('Choose one key: F1–F24, A–Z or 0–9')
    if phase not in ('tap', 'down', 'keepalive', 'up'):
        raise ValueError('Unknown button-box phase')
    if action in HOLD_ACTIONS and phase == 'tap' or action not in HOLD_ACTIONS and phase != 'tap':
        raise ValueError('Starter and radio require hold/release; other controls require a tap')
    if not isinstance(press_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', press_id):
        raise ValueError('Invalid button press identifier')
    return action, key, phase, press_id


def read_states(get, car):
    """Read only observed simulator fields; missing controls remain unknown."""
    def finite(value):
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    def switch(name):
        value = get(name)
        if type(value) is bool:
            return value
        value = finite(value)
        return value > 0 if value is not None and value >= 0 else None
    active = car.get('in_car') is True and not car.get('garage') and not car.get('replay')
    return dict(ignition=switch('dcIgnition') if active else None,
                pit_limiter=car.get('pit_limiter') if active else None,
                wipers=switch('dcWiper') if active else None,
                bias=finite(get('dcBrakeBias')) if active else None,
                tc=finite(get('dcTractionControl')) if active else None,
                abs=finite(get('dcABS')) if active else None,
                source='sdk', available=bool(active),
                message='Keep iRacing focused. Assign the same keys in iRacing Controls.' if active else 'Enter the car to use the button box.')


class WindowsKeys:
    """Native scan-code injection; never activate or switch application windows."""
    def __init__(self):
        self.supported = platform.system() == 'Windows'
        if not self.supported:
            return
        from ctypes import wintypes
        self.wintypes = wintypes
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
        self.user32.GetKeyboardLayout.restype = wintypes.HANDLE
        self.user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HANDLE)
        self.user32.MapVirtualKeyExW.restype = wintypes.UINT

        class KeyboardInput(ctypes.Structure):
            _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                        ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
        class MouseInput(ctypes.Structure):
            _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                        ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
        class HardwareInput(ctypes.Structure):
            _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]
        class InputUnion(ctypes.Union):
            _fields_ = [('ki', KeyboardInput), ('mi', MouseInput), ('hi', HardwareInput)]
        class Input(ctypes.Structure):
            _anonymous_ = ('data',)
            _fields_ = [('type', wintypes.DWORD), ('data', InputUnion)]
        self.Input, self.KeyboardInput = Input, KeyboardInput
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT
        self._scans = {}

    def focused(self):
        if not self.supported:
            return False
        window = self.user32.GetForegroundWindow()
        if not window:
            return False
        pid = self.wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        handle = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            length = self.wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(length.value)
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                return False
            return ntpath.basename(image.value).lower() in {
                'iracingsim64dx11.exe', 'iracingsim64dx11_test.exe', 'iracingsim64.exe'}
        finally:
            self.kernel32.CloseHandle(handle)

    def key(self, key, down):
        if not self.supported:
            raise RuntimeError('Live button-box controls require Windows.')
        if down:
            if not self.focused():
                raise RuntimeError('Focus the iRacing simulator before pressing a button.')
            thread = self.user32.GetWindowThreadProcessId(self.user32.GetForegroundWindow(), None)
            layout = self.user32.GetKeyboardLayout(thread)
            virtual = 0x70 + int(key[1:]) - 1 if key.startswith('F') and len(key) > 1 else ord(key)
            scan = self.user32.MapVirtualKeyExW(virtual, 4, layout)
            if not scan:
                raise RuntimeError('This key has no scan code on the current keyboard layout. Choose another binding.')
            self._scans[key] = scan
        else:
            scan = self._scans.get(key)
            if scan is None:
                return
        flags = 0x0008 | (0x0002 if not down else 0) | (0x0001 if scan & 0xff00 else 0)
        event = self.Input(type=1)
        event.ki = self.KeyboardInput(0, scan & 0xff, flags, 0, 0)
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
            raise RuntimeError('Windows did not accept the key. Run iRacing and iR-Board at the same permission level.')
        if not down:
            self._scans.pop(key, None)


class ButtonBox:
    def __init__(self, demo=False, sink=None, clock=time.monotonic):
        self.demo, self.sink, self.clock = demo, sink or WindowsKeys(), clock
        self.lock = threading.RLock()
        self.presses = {}
        self.retired = {}
        self.stop_event = threading.Event()
        self.thread = None
        self.demo_states = dict(ignition=True,pit_limiter=False,wipers=False,bias=54.2,tc=3,abs=4)

    def _watch(self):
        while not self.stop_event.wait(.04):
            with self.lock:
                self._expire()

    def _retire(self, press_id):
        # Remember completed IDs so an HTTP down arriving after its matching up
        # cannot start a new hold. Bound both retention time and memory usage.
        self.retired.pop(press_id, None)
        self.retired[press_id] = self.clock() + RETIRED_SECONDS
        while len(self.retired) > MAX_RETIRED:
            self.retired.pop(next(iter(self.retired)))

    def _expire(self):
        now = self.clock()
        for press_id, deadline in list(self.retired.items()):
            if now >= deadline:
                self.retired.pop(press_id, None)
        if not self.presses:
            return
        now = self.clock()
        focused = self.demo or self.sink.focused()
        for press_id, press in list(self.presses.items()):
            if now >= press['deadline'] or not focused:
                self._release(press_id)

    def _release(self, press_id):
        press = self.presses.get(press_id)
        if press is None:
            self._retire(press_id)
            return
        # Retry a rejected key-up on the next watchdog tick; do not lose track.
        if not self.demo:
            try:
                self.sink.key(press['key'], False)
            except (OSError, RuntimeError):
                press['deadline'] = 0
                return
        self.presses.pop(press_id, None)
        self._retire(press_id)

    def submit(self, payload, ready=True, owner='local'):
        action, key, phase, press_id = validate(payload)
        with self.lock:
            self._expire()
            if self.stop_event.is_set():
                raise RuntimeError('Button box stopped.')
            previous = self.presses.get(press_id)
            if previous and (previous['action'], previous['key'], previous['owner']) != (action, key, owner):
                raise ValueError('Button press belongs to another control or device.')
            if phase == 'up':
                self._release(press_id)
            elif phase == 'keepalive':
                if not previous:
                    raise RuntimeError('Button hold expired. Release and press again.')
                if not ready:
                    self._release(press_id)
                    raise RuntimeError('Connect to the iRacing simulator before using the button box.')
                previous['deadline'] = self.clock() + LEASE_SECONDS
            else:
                if not ready:
                    raise RuntimeError('Connect to the iRacing simulator before using the button box.')
                if press_id in self.retired:
                    raise RuntimeError('This button press has already been released. Press again.')
                if previous:
                    raise RuntimeError('This button press has already been sent.')
                if len(self.presses) >= 12 or any(p['key'] == key for p in self.presses.values()):
                    raise RuntimeError('This key is already pressed. Release it before pressing again.')
                if not self.demo:
                    if not self.sink.supported:
                        raise RuntimeError('Live button-box controls require Windows.')
                    if not self.sink.focused():
                        raise RuntimeError('Focus the iRacing simulator before pressing a button.')
                    self.sink.key(key, True)
                if self.demo and phase == 'tap':
                    if action in ('ignition','pit_limiter','wipers'):
                        self.demo_states[action] = not self.demo_states[action]
                    elif '_' in action:
                        group,direction = action.rsplit('_',1)
                        amount = (.1 if group == 'bias' else 1) * (1 if direction == 'up' else -1)
                        self.demo_states[group] = round(max(0,min(100 if group=='bias' else 15,self.demo_states[group]+amount)),1)
                self.presses[press_id] = dict(action=action, key=key, owner=owner,
                    deadline=self.clock() + (TAP_SECONDS if phase == 'tap' else LEASE_SECONDS))
                if self.thread is None:
                    self.thread = threading.Thread(target=self._watch, name='buttonbox-key-release', daemon=True)
                    self.thread.start()
        return dict(status='demo' if self.demo else 'sent',
                    message='DEMO: simulated button press; no keys sent.' if self.demo else 'Key sent. The simulator decides whether this control is available.')

    def release_all(self):
        with self.lock:
            for press_id in list(self.presses):
                self._release(press_id)

    def stop(self):
        self.stop_event.set()
        self.release_all()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
