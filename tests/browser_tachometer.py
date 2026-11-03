"""Fast polling, stable tachometer DOM, numeric speed and per-car shift lights."""
import os
import re
import time
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('IRBOARD_TEST_URL', 'http://127.0.0.1:8006')
with sync_playwright() as p:
    options = dict(headless=True, args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):
        options['executable_path'] = os.environ['IRBOARD_BROWSER']
    browser = p.chromium.launch(**options)
    page = browser.new_page(viewport={'width':1024,'height':700})
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['car'].update(speed=30,rpm=14000,max_rpm=15000,shift_rpm=14000,
                           shift_first_rpm=10000,shift_last_rpm=13500,blink_rpm=14000,gear=4)
    calls=[]
    def telemetry(route):
        # A tablet clock offset must not mark current telemetry as offline.
        snapshot['timestamp']=time.time()-3600
        snapshot['sample_age']=0
        calls.append(time.monotonic())
        assert route.request.headers.get('x-irboard-sections') == ''
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    # Isolate local layout fixtures; shared-server behavior has its own regression.
    page.route('**/api/layout', lambda route: route.abort())
    page.goto(BASE)
    page.wait_for_selector('.tachometer-panel')
    expect(page.locator('#dashboard .tachometer-panel [data-role=speed]')).to_have_text('108')
    expect(page.locator('#dashboard .tachometer-panel')).to_have_class(re.compile(r'.*\bshift-now\b.*'))
    page.evaluate("window.originalTach = document.querySelector('.tachometer-panel')")
    count=len(calls)
    page.wait_for_timeout(1500)
    received=len(calls)-count
    assert received >= 15, received
    assert page.evaluate("window.originalTach === document.querySelector('.tachometer-panel')")
    snapshot['car']['rpm']=13900
    expect(page.locator('#dashboard .tachometer-panel')).not_to_have_class(re.compile(r'.*\bshift-now\b.*'))
    snapshot['car'].update(rpm=14000,gear=0)
    page.wait_for_timeout(200)
    expect(page.locator('#dashboard .tachometer-panel')).not_to_have_class(re.compile(r'.*\bshift-now\b.*'))
    snapshot['car'].update(rpm=5700,max_rpm=6000,shift_rpm=5700,shift_first_rpm=4000,
                           shift_last_rpm=5600,blink_rpm=5700,gear=2)
    expect(page.locator('#dashboard .tachometer-panel')).to_have_class(re.compile(r'.*\bshift-now\b.*'))
    page.locator('.configure').click()
    page.locator('[name="blink-speed"]').select_option('10')
    page.locator('[name="led-style"]').select_option('dots')
    page.locator('[name="led-dots"]').fill('24')
    page.locator('#widget-form .form-actions .primary').click()
    expect(page.locator('#dashboard .leds i')).to_have_count(24)
    expect(page.locator('#dashboard .leds')).to_have_css('animation-name','shift-blink')
    expect(page.locator('#dashboard [data-role=rpm]')).to_have_css('animation-name','none')
    expect(page.locator('#dashboard [data-element=rpm] .unit')).to_have_css('animation-name','none')
    page.reload();page.wait_for_selector('.tachometer-panel')
    expect(page.locator('#dashboard .leds')).to_have_css('animation-duration','0.1s')
    expect(page.locator('#dashboard .leds i')).to_have_count(24)
    dot=page.locator('#dashboard .leds i').first.bounding_box()
    assert abs(dot['width']-dot['height'])<2, dot
    snapshot['car'].update(speed_unit='mph')
    expect(page.locator('#dashboard .speed-unit')).to_have_text('mph')
    expect(page.locator('#dashboard [data-role=speed]')).to_have_text('67')
    page.locator('.configure').click()
    page.locator('[name="led-style"]').select_option('segments')
    page.locator('[name="led-segments"]').fill('20')
    page.locator('#widget-form .primary').click()
    expect(page.locator('#dashboard .leds i')).to_have_count(20)
    page.locator('.configure').click()
    page.locator('[name="led-style"]').select_option('bar')
    page.locator('[name="blink-rpm"]').fill('7000')
    page.locator('#widget-form .primary').click()
    expect(page.locator('#dashboard .rpm-fill')).to_have_count(1)
    expect(page.locator('#dashboard .tachometer-panel')).not_to_have_class(re.compile(r'.*\bshift-now\b.*'))
    snapshot['car']['rpm']=3000
    expect(page.locator('#dashboard .rpm-fill')).to_have_css('width',re.compile(r'.+px'))
    page.wait_for_timeout(100)
    track=page.locator('#dashboard .leds').bounding_box()
    fill=page.locator('#dashboard .rpm-fill').bounding_box()
    assert .50 < fill['width']/track['width'] < .55
    snapshot['session']['pit_limit']=60/3.6
    snapshot['car'].update(speed_unit='km/h',pit=True,pit_limiter=True,speed=15)
    sign=page.locator('#dashboard .pit-limiter')
    expect(sign.locator('.pit-limit-number')).to_have_text('60')
    expect(sign.locator('.pit-limit-unit')).to_have_text('km/h')
    expect(sign).to_be_visible()
    expect(sign.locator('.pit-limiter-status')).to_have_text('LIMITER ON')
    assert sign.locator('.pit-limit-sign').evaluate("el=>getComputedStyle(el,'::after').borderTopColor") == 'rgb(32, 201, 112)'
    assert sign.locator('.pit-limit-sign').evaluate("el=>getComputedStyle(el,'::after').animationName") == 'pit-limiter-pulse'
    expect(sign.locator('.pit-limit-number')).to_have_css('animation-name','none')
    expect(sign).to_have_attribute('data-speeding','false')
    snapshot['car'].update(pit_limiter=False,speed=20)
    expect(sign.locator('.pit-limiter-status')).to_have_text('LIMITER OFF')
    assert sign.locator('.pit-limit-sign').evaluate("el=>getComputedStyle(el,'::after').borderTopColor") == 'rgb(223, 48, 57)'
    page.emulate_media(reduced_motion='reduce')
    assert sign.locator('.pit-limit-sign').evaluate("el=>getComputedStyle(el,'::after').animationName") == 'none'
    page.emulate_media(reduced_motion='no-preference')
    expect(sign).to_have_attribute('data-speeding','true')
    snapshot['car'].update(speed_unit='mph',pit=False,surface=2)
    expect(sign.locator('.pit-limit-number')).to_have_text('37')
    expect(sign.locator('.pit-limit-unit')).to_have_text('mph')
    expect(sign).to_have_attribute('data-speeding','false')
    snapshot['car'].update(surface=3,pit_limiter=True)
    expect(sign).to_be_hidden()
    snapshot['car']['surface']=2
    expect(sign).to_be_visible()
    snapshot['session']['pit_limit']=None
    snapshot['car']['pit_limiter']=None
    expect(sign.locator('.pit-limit-number')).to_have_text('—')
    expect(sign).to_be_hidden()
    snapshot['session']['pit_limit']=60/3.6
    expect(sign).to_be_hidden()
    snapshot['car']['pit_limiter']=True
    expect(sign).to_be_visible()
    assert not errors,errors
    browser.close()
    print(f'PASS: numeric speed, car-specific shift blinking, stable DOM, {received} updates in 1.5 seconds')
