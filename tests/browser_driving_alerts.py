"""Flag overlays, per-flag controls, side spotter and persistent settings."""
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8026')
with sync_playwright() as p:
    options=dict(headless=True,args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):options['executable_path']=os.environ['IRBOARD_BROWSER']
    browser=p.chromium.launch(**options)
    page=browser.new_page(viewport={'width':1100,'height':900})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['session'].update(flags=0,key='alerts-test')
    snapshot['car'].update(left_right=1,in_car=True,replay=False,garage=False)
    def telemetry(route):
        snapshot['timestamp']=time.time()
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.route('**/api/layout',lambda route:route.abort())
    page.goto(BASE);page.wait_for_selector('.tachometer-panel')
    flag=page.locator('#race-flag-overlay')
    spotter=page.locator('#screen-spotter')
    left=spotter.locator('[data-side=left]');right=spotter.locator('[data-side=right]')
    expect(flag).to_be_hidden();expect(spotter).to_be_hidden()
    page.locator('#settings').click()
    expect(page.locator('#alert-flag-mode')).to_have_value('center')
    expect(page.locator('#alert-spotter-mode')).to_have_value('off')
    page.locator('#alert-flag-mode').select_option('center')
    page.locator('#alert-flag-duration').fill('1')
    page.locator('#alert-flag-opacity').evaluate("el=>{el.value=65;el.dispatchEvent(new Event('input',{bubbles:true}))}")
    page.locator('#modal-close').click()
    snapshot['session']['flags']=8
    expect(flag).to_be_visible();expect(flag).to_have_attribute('data-mode','center')
    expect(flag).to_have_attribute('data-flag','yellow')
    expect(flag.locator('.race-flag-cloth')).to_have_css('opacity','0.65')
    expect(flag.locator('.race-flag-cloth')).to_have_css('animation-name','none')
    assert flag.locator('.race-flag-sign').bounding_box()['width']<=140
    assert flag.locator('.race-flag-label').bounding_box()['width']<=1
    expect(flag).to_have_css('pointer-events','none')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/centered-race-flag.png')
    expect(flag).to_be_hidden(timeout=2500)
    page.wait_for_timeout(300);expect(flag).to_be_hidden()
    # A small flag can blink or stay steady, and can stay until the game clears it.
    page.locator('#settings').click()
    page.locator('#alert-flag-visibility').select_option('active')
    expect(page.locator('#alert-flag-duration')).to_be_disabled()
    page.locator('#alert-flag-animation').select_option('blink')
    page.locator('#modal-close').click()
    expect(flag).to_be_visible()
    expect(flag.locator('.race-flag-cloth')).to_have_css('animation-name','race-flag-pulse')
    page.wait_for_timeout(1200);expect(flag).to_be_visible()
    page.locator('#settings').click()
    page.locator('#alert-flag-animation').select_option('steady')
    page.locator('#modal-close').click()
    expect(flag.locator('.race-flag-cloth')).to_have_css('animation-name','none')
    # A clear then a new flag is another event; disabled flags disappear immediately.
    snapshot['session']['flags']=0;page.wait_for_timeout(150)
    snapshot['session']['flags']=16;expect(flag).to_have_attribute('data-flag','red')
    page.locator('#settings').click()
    page.locator('[data-race-flag=red]').uncheck();expect(flag).to_be_hidden()
    page.locator('#alert-flag-mode').select_option('flash')
    page.locator('#alert-flag-visibility').select_option('timed')
    page.locator('#alert-flag-duration').fill('3')
    page.locator('#modal-close').click()
    snapshot['session']['flags']=0x20
    expect(flag).to_be_visible();expect(flag).to_have_attribute('data-mode','flash')
    cloth=flag.locator('.race-flag-cloth')
    expect(cloth).to_have_css('animation-name','race-flag-pulse')
    start=cloth.evaluate('el=>el.getAnimations()[0].startTime')
    page.wait_for_timeout(250)
    assert cloth.evaluate('el=>el.getAnimations()[0].startTime')==start
    page.emulate_media(reduced_motion='reduce')
    expect(cloth).to_have_css('animation-name','none')
    page.emulate_media(reduced_motion='no-preference')
    # The orange spotter is independent of both flags and the radar widget.
    snapshot['session']['flags']=0
    page.locator('#settings').click()
    page.locator('#alert-spotter-mode').select_option('halves')
    page.locator('#modal-close').click()
    for value,expected in [(2,(True,False)),(3,(False,True)),(4,(True,True)),(5,(True,False)),(6,(False,True))]:
        snapshot['car']['left_right']=value
        expect(spotter).to_be_visible()
        expect(left).to_be_visible() if expected[0] else expect(left).to_be_hidden()
        expect(right).to_be_visible() if expected[1] else expect(right).to_be_hidden()
    assert abs(right.bounding_box()['width']-550)<1
    expect(right).to_have_css('background-color','rgb(255, 148, 31)')
    expect(spotter).to_have_css('pointer-events','none')
    snapshot['car']['left_right']=1;expect(spotter).to_be_hidden()
    snapshot['car'].update(left_right=2,replay=True);expect(spotter).to_be_hidden()
    snapshot['car'].update(replay=False,in_car=False);expect(spotter).to_be_hidden()
    snapshot['car']['in_car']=True;expect(spotter).to_be_visible()
    snapshot['connected']=False;expect(spotter).to_be_hidden();expect(flag).to_be_hidden()
    snapshot.update(connected=True,sample_age=10);expect(spotter).to_be_hidden()
    snapshot['sample_age']=0;expect(spotter).to_be_visible()
    page.locator('#settings').click()
    page.locator('#alert-spotter-mode').select_option('bars')
    page.locator('#modal-close').click()
    snapshot['car']['left_right']=4
    expect(left).to_be_visible();expect(right).to_be_visible()
    expect(spotter).to_have_attribute('data-mode','bars')
    assert 10<=left.bounding_box()['width']<=30
    page.screenshot(path='test-results/spotter-side-bars.png')
    page.reload();expect(spotter).to_have_attribute('data-mode','bars')
    expect(left).to_be_visible();expect(right).to_be_visible()
    page.locator('#settings').click()
    expect(page.locator('#alert-spotter-mode')).to_have_value('bars')
    expect(page.locator('[data-race-flag=red]')).not_to_be_checked()
    expect(page.locator('#alert-flag-opacity')).to_have_value('65')
    page.locator('#alert-flag-mode').select_option('off')
    page.locator('#alert-spotter-mode').select_option('off')
    page.locator('#modal-close').click()
    snapshot['session']['flags']=0x8
    expect(flag).to_be_hidden();expect(spotter).to_be_hidden()
    assert not errors,errors
    browser.close()
    print('PASS: centered/timed flags, stable full-screen flashing, individual flags, reduced motion, every spotter side, bars/halves, stale/replay clearing and saved settings')
