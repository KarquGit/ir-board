"""Fullscreen flag patterns and revised tachometer layout in the browser."""
import os
import time
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8020')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('IRBOARD_BROWSER','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':800})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['session']['flags']=0
    snapshot['car'].update(pit=True,pit_limiter=True,water=87.3,oil=103.4)
    snapshot['session']['pit_limit']=60/3.6
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.route('**/api/layout',lambda route:route.abort())
    page.goto(BASE);page.wait_for_selector('.widget')
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({alerts:{flags:{mode:'flash'}},pages:[{name:'Speed',preset:'single',widgets:[{type:'tachometer'}]}]}))""")
    page.reload();page.wait_for_selector('.tachometer-panel')
    panel=page.locator('#dashboard .tachometer-panel')
    pit=panel.locator('.pit-limiter').bounding_box()
    water=panel.locator('.metric[data-element=water]').bounding_box()
    oil=panel.locator('.metric[data-element=oil]').bounding_box()
    assert pit['y']+pit['height']<=water['y']
    assert abs(water['y']-oil['y'])<2
    box=panel.bounding_box()
    center=(water['x']+oil['x']+oil['width'])/2
    assert abs(center-(box['x']+box['width']/2))<3
    assert oil['x']-(water['x']+water['width'])<100
    for value,name,pattern in [(0x40,'debris','repeating-linear-gradient'),(1,'checkered','conic-gradient'),(0x20,'blue','linear-gradient'),(0x10,'red','none')]:
        snapshot['session']['flags']=value
        expect(page.locator('#race-flag-overlay')).to_have_attribute('data-flag',name)
        image=page.locator('.race-flag-cloth').evaluate("el=>getComputedStyle(el).backgroundImage")
        assert pattern in image,(name,image)
        if value==0x40:
            assert '255, 207, 36' in image and '216, 32, 50' in image,image
        expect(page.locator('.race-flag-cloth')).to_have_css('animation-name','race-flag-pulse')
    snapshot['car']['pit_limiter']=None
    expect(panel.locator('.pit-limiter')).to_be_hidden()
    expect(panel.locator('.metric[data-element=water]')).to_be_visible()
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({alerts:{flags:{mode:'flash'}},pages:[{name:'Inputs',preset:'single',widgets:[{type:'inputs'}]}]}))""")
    snapshot['session']['flags']=0
    snapshot['car'].update(abs_active=True,brake=.7)
    page.reload();page.wait_for_selector('.inputs-panel')
    inputs=page.locator('#dashboard .inputs-panel')
    expect(inputs.locator('.input-info')).to_have_count(0)
    brake=inputs.locator('.pedal[data-element=brake] i')
    expect(brake).to_have_css('background-color','rgb(255, 159, 28)')
    expect(brake).to_have_css('animation-name','abs-brake-flash')
    brake.evaluate('el=>window.originalBrake=el')
    page.wait_for_timeout(350)
    assert brake.evaluate('el=>el===window.originalBrake')
    assert brake.evaluate('el=>el.getAnimations()[0].currentTime')>200
    snapshot['car']['abs_active']=False
    expect(brake).to_have_css('animation-name','none')
    assert brake.evaluate("el=>getComputedStyle(el).backgroundColor")!='rgb(255, 159, 28)'
    assert not errors,errors
    browser.close()
    print('PASS: PIT above centered temperatures, hidden unsupported limiter, simultaneous flag patterns, no browser errors')
