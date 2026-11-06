"""Button box interaction regression. Run against a disposable DEMO data directory.

IRBOARD_TEST_URL defaults to http://127.0.0.1:8040. Uses the existing Chromium
binary unless IRBOARD_BROWSER selects another executable.
"""
import os
import re
from pathlib import Path
import time
import uuid

from playwright.sync_api import expect, sync_playwright


BASE = os.environ.get('IRBOARD_TEST_URL', 'http://127.0.0.1:8040')
OUT = Path('test-results')
OUT.mkdir(exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=os.environ.get('IRBOARD_BROWSER', '/usr/bin/chromium'),
        args=['--no-sandbox'],
    )
    context = browser.new_context(viewport={'width': 1280, 'height': 950})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    snapshot = page.request.get(BASE + '/api/telemetry').json()
    assert snapshot['mode'] == 'demo'

    # Real endpoint exercises DEMO without requiring an OS keyboard backend.
    demo = page.request.post(BASE + '/api/buttonbox', data={
        'action': 'flash', 'key': 'F16', 'phase': 'tap',
        'press_id': str(uuid.uuid4()),
    })
    assert demo.ok, demo.text()
    assert demo.json()['status'] == 'demo'

    snapshot['buttonbox'] = dict(
        ignition=True, pit_limiter=False, wipers=None,
        bias=54.2, tc=3, abs=4, source='sdk', available=True,
        message='Shortcuts ready',
    )

    def telemetry(route):
        snapshot['timestamp'] = time.time()
        snapshot['sample_age'] = 0
        route.fulfill(json=snapshot)

    commands = []
    command_error = {'message': None}

    def command(route):
        commands.append(route.request.post_data_json)
        if command_error['message']:
            route.fulfill(status=409, json={'error': command_error['message']})
        else:
            route.fulfill(json={'status': 'demo', 'message': 'DEMO: no keys sent'})

    page.route('**/api/telemetry', telemetry)
    page.route('**/api/layout', lambda route: route.abort())
    page.route('**/api/buttonbox', command)
    page.goto(BASE)
    page.wait_for_selector('.widget')
    original = page.evaluate("JSON.parse(localStorage.getItem('irboard'))")
    assert len(original['pages']) == 7

    # Add an optional widget without changing any of the supplied seven pages.
    page.locator('#new-page').click()
    page.locator('#add-widget').click()
    expect(page.locator('[data-kind=buttonbox] strong')).to_have_text('Button box')
    page.locator('[data-kind=buttonbox]').click()
    box = page.locator('#dashboard [data-type=buttonbox]')
    expect(box).to_be_visible()
    saved = page.evaluate("JSON.parse(localStorage.getItem('irboard'))")
    assert saved['pages'][:7] == original['pages']

    def action(name):
        return box.locator(f'[data-action={name}]')

    def received(name, phase):
        return [c for c in commands if c['action'] == name and c['phase'] == phase]

    def wait_command(name, phase, count=1):
        deadline = time.monotonic() + 5
        while len(received(name, phase)) < count:
            assert time.monotonic() < deadline, (name, phase, commands)
            page.wait_for_timeout(25)
        return received(name, phase)[-1]

    def press(name):
        button = action(name)
        bounds = button.bounding_box()
        page.mouse.move(bounds['x'] + bounds['width'] / 2,
                        bounds['y'] + bounds['height'] / 2)
        page.mouse.down()

    # Null telemetry must stay distinct from a confirmed OFF state.
    expect(action('ignition')).to_have_attribute('data-state', 'on')
    expect(action('pit_limiter')).to_have_attribute('data-state', 'off')
    expect(action('wipers')).to_have_attribute('data-state', 'unknown')
    expect(box.locator('[data-box-value=bias]')).to_have_text('54.2%')
    expect(box.locator('[data-box-value=tc]')).to_have_text('3')
    expect(box.locator('[data-box-value=abs]')).to_have_text('4')

    # A command animates briefly; no local optimistic toggle fabricates readback.
    action('flash').dispatch_event('click')
    expect(action('flash')).to_have_class(re.compile(r'\bbox-pressed\b'))
    wait_command('flash', 'tap')
    page.wait_for_timeout(220)
    expect(action('flash')).not_to_have_class(re.compile(r'\bbox-pressed\b'))
    assert received('flash', 'tap')[-1]['key'] == 'F16'
    assert not received('flash', 'down')
    action('ignition').click()
    wait_command('ignition', 'tap')
    expect(action('ignition')).to_have_attribute('data-state', 'on')
    snapshot['buttonbox']['ignition'] = False
    expect(action('ignition')).to_have_attribute('data-state', 'off')

    # Held commands are leased and released when the finger lifts.
    press('starter')
    start = wait_command('starter', 'down')
    wait_command('starter', 'keepalive')
    page.mouse.up()
    stop = wait_command('starter', 'up')
    assert start['press_id'] == stop['press_id']
    assert all(c['press_id'] == start['press_id']
               for c in received('starter', 'keepalive'))

    # A fast finger lift must also release a key when its down response is late.
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = (...args) => {
        const request = original(...args);
        if (String(args[0]).includes('/api/buttonbox') &&
            JSON.parse(args[1].body).phase === 'down') {
          return request.then(response => new Promise(resolve => setTimeout(() => resolve(response), 500)));
        }
        return request;
      };
      window.restoreButtonboxFetch = () => { window.fetch = original; };
    }""")
    starter_count = len(received('starter', 'down'))
    press('starter')
    late = wait_command('starter', 'down', starter_count + 1)
    page.mouse.up()
    assert wait_command('starter', 'up', starter_count + 1)['press_id'] == late['press_id']
    assert not [c for c in received('starter', 'keepalive') if c['press_id'] == late['press_id']]
    page.evaluate('window.restoreButtonboxFetch()')

    # Browser focus loss, cancelled touches and page navigation release keys.
    press('radio')
    radio = wait_command('radio', 'down')
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    assert wait_command('radio', 'up')['press_id'] == radio['press_id']
    page.mouse.up()

    starter_count = len(received('starter', 'down'))
    press('starter')
    wait_command('starter', 'down', starter_count + 1)
    action('starter').dispatch_event('pointercancel', {'pointerId': 1})
    wait_command('starter', 'up', starter_count + 1)
    page.mouse.up()

    radio_count = len(received('radio', 'down'))
    press('radio')
    wait_command('radio', 'down', radio_count + 1)
    page.locator('[data-page="0"]').first.dispatch_event('click')
    wait_command('radio', 'up', radio_count + 1)
    page.mouse.up()
    page.locator('[data-page="7"]').first.click()
    expect(box).to_be_visible()

    # Controls never issue commands while editing or in the appearance preview.
    page.locator('#edit').click()
    before = len(commands)
    action('flash').dispatch_event('click')
    page.wait_for_timeout(300)
    assert len(commands) == before
    page.locator('#edit').click()
    box.locator('.configure').click()
    page.locator('.preview [data-action=flash]').dispatch_event('click')
    page.wait_for_timeout(300)
    assert len(commands) == before

    # Custom shortcuts survive save, reload and sharing with a fresh browser.
    page.locator('.buttonbox-bindings summary').click()
    page.locator('[data-button-binding=flash]').select_option('L')
    page.locator('[data-button-binding=radio]').select_option('R')
    page.locator('#widget-form .primary').click()
    page.reload()
    expect(box).to_be_visible()
    action('flash').click()
    assert wait_command('flash', 'tap', 2)['key'] == 'L'
    saved = page.evaluate("JSON.parse(localStorage.getItem('irboard'))")
    bindings = saved['pages'][7]['widgets'][0]['buttonBindings']
    assert bindings['flash'] == 'L' and bindings['radio'] == 'R'

    # Keyboard activation has the same press/release behavior as a touch hold.
    starter_count = len(received('starter', 'down'))
    action('starter').focus()
    page.keyboard.down('Space')
    keyboard_start = wait_command('starter', 'down', starter_count + 1)
    page.keyboard.up('Space')
    assert wait_command('starter', 'up', starter_count + 1)['press_id'] == keyboard_start['press_id']
    action('starter').evaluate('button => button.blur()')

    # Responsive layouts keep every action accessible and within the widget.
    page.add_style_tag(content='#race-flag-overlay,#screen-spotter {display:none !important;}')
    snapshot['buttonbox'].update(ignition=True, pit_limiter=True, wipers=False)
    expect(action('ignition')).to_have_attribute('data-state', 'on')
    for size, filename in [({'width': 1280, 'height': 950}, 'buttonbox-landscape.png'),
                           ({'width': 1024, 'height': 768}, None),
                           ({'width': 800, 'height': 1100}, 'buttonbox-portrait.png')]:
        page.set_viewport_size(size)
        page.wait_for_timeout(200)
        box.locator('.widget-body').evaluate('body => { body.scrollTop=0; }')
        bounds = box.bounding_box()
        command_error['message'] = 'iRacing must be the active window on the PC. Focus the simulator and try again.'
        action('flash').click()
        expect(box.locator('.box-result')).to_have_text(command_error['message'])
        for name in ['ignition', 'starter', 'pit_limiter', 'bias_down', 'bias_up',
                     'tc_down', 'tc_up', 'abs_down', 'abs_up', 'flash', 'wipers', 'radio']:
            button = action(name)
            expect(button).to_be_visible()
            rect = button.bounding_box()
            assert rect['width'] >= 35 and rect['height'] >= 35, (name, rect)
            assert rect['x'] >= bounds['x'] - 1 and rect['x'] + rect['width'] <= bounds['x'] + bounds['width'] + 1, (name, rect, bounds)
        for selector in ['.box-legend', '.box-result']:
            rect = box.locator(selector).bounding_box()
            assert rect['y'] >= bounds['y'] and rect['y'] + rect['height'] <= bounds['y'] + bounds['height'] + 1, (selector, rect, bounds, size)
        command_error['message'] = None
        action('flash').click()
        expect(box.locator('.box-result')).to_have_text('DEMO: no keys sent')
        page.wait_for_timeout(220)
        action('flash').evaluate('button => button.blur()')
        if filename:
            box.screenshot(path=str(OUT / filename))

    # Use the actual LayoutStore API to prove new settings reach another device.
    revision = page.request.get(BASE + '/api/layout').json()['revision']
    shared = page.request.post(BASE + '/api/layout', data={'revision': revision, 'layout': saved})
    assert shared.ok, shared.text()
    other = browser.new_page(viewport={'width': 1200, 'height': 850})
    other.on('pageerror', lambda error: errors.append(str(error)))
    other.goto(BASE)
    other.wait_for_function("() => JSON.parse(localStorage.getItem('irboard'))?.pages.length===8")
    other.locator('[data-page="7"]').first.click()
    expect(other.locator('#dashboard [data-type=buttonbox]')).to_be_visible()
    other.locator('#dashboard .configure').click()
    other.locator('.buttonbox-bindings summary').click()
    expect(other.locator('[data-button-binding=flash]')).to_have_value('L')
    expect(other.locator('[data-button-binding=radio]')).to_have_value('R')
    assert not errors, errors
    browser.close()
    print('PASS: optional Button box, telemetry states and values, momentary commands, held-key release, preview/edit isolation, shortcuts, keyboard, responsive layout and shared settings')
