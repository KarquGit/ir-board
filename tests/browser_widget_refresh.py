"""Compact widgets, fuel cylinder, custom palette and short dashboard flag alerts."""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8004')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('IRBOARD_BROWSER','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1200,'height':850})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/api/layout',lambda route:route.abort())
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['session']['flags']=0
    snapshot['car']['fuel']=55
    snapshot['pit']['fuel_max']=110
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.goto(BASE);page.wait_for_selector('.leds')
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({alerts:{flags:{mode:'flash'}},pages:[{name:'Compact',preset:'grid-2x2',widgets:['tachometer','laps','fuel','systems'].map(type=>({type,colors:{},hidden:[],layouts:{}}))}]}))""")
    page.reload()
    expect(page.locator('.fuel-cylinder-fill')).to_have_attribute('style','height:50%')
    snapshot['car']['fuel']=22
    expect(page.locator('.fuel-cylinder-fill')).to_have_attribute('style','height:20%')
    page.locator('#add-widget').click()
    for removed in ['weather','flag','flatmap','trace']:
        assert page.locator('[data-kind='+removed+']').count()==0
    page.locator('#modal-close').click()
    page.locator('#settings').click()
    assert page.locator('[data-theme-choice]').count()==31
    page.locator('.custom-theme-editor summary').click()
    page.locator('[data-custom-color=bg]').fill('#102030')
    page.locator('[data-custom-color=background]').fill('#213141')
    page.locator('[data-custom-color=accent]').fill('#ff9933')
    expect(page.locator('html')).to_have_attribute('data-theme','custom')
    page.locator('#modal-close').click()
    page.reload();page.wait_for_selector('.fuel-cylinder')
    expect(page.locator('html')).to_have_attribute('data-theme','custom')
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")=='#102030'
    expect(page.locator('[data-type=systems]')).to_have_css('background-color','rgb(33, 49, 65)')
    snapshot['session']['flags']=8
    expect(page.locator('#race-flag-overlay')).to_have_attribute('data-flag','yellow')
    expect(page.locator('.race-flag-cloth')).to_have_css('animation-name','race-flag-pulse')
    page.wait_for_timeout(3300)
    expect(page.locator('#race-flag-overlay')).to_be_hidden()
    snapshot['session']['flags']=16|8
    expect(page.locator('#race-flag-overlay')).to_have_attribute('data-flag','red')
    snapshot['session']['flags']=0
    expect(page.locator('#race-flag-overlay')).to_be_hidden()
    page.set_viewport_size({'width':800,'height':1000})
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/refreshed-widgets.png')
    page.evaluate("() => localStorage.setItem('irboard', JSON.stringify({alerts:{flags:{mode:'flash'}},pages:[{name:'Compact systems',preset:'auto',widgets:[{type:'systems'}]}]}))")
    page.reload();page.wait_for_selector('[data-type=systems]')
    box=page.locator('#dashboard').bounding_box();widget=page.locator('#dashboard .widget').bounding_box()
    assert widget['height']/box['height'] <= .281
    assert not errors,errors
    browser.close()
    print('PASS: compact widgets, falling cylinder, removed catalog, 30 palettes + custom persistence, finite flag alert, portrait')
