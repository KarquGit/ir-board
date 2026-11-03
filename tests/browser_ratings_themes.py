"""SDK flags, rating visibility and thirty theme persistence without manual country settings."""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8011')
with sync_playwright() as p:
    options=dict(headless=True,args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):options['executable_path']=os.environ['IRBOARD_BROWSER']
    browser=p.chromium.launch(**options)
    page=browser.new_page(viewport={'width':1024,'height':800},has_touch=True)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['drivers'][0]['country']=None
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    # Isolate local layout fixtures; shared-server behavior has its own regression.
    page.route('**/api/layout', lambda route: route.abort())
    page.goto(BASE);page.wait_for_selector('.widget')
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({theme:'original',active:0,pages:[{name:'Ratings',preset:'top-bottom',widgets:[{type:'standings',colors:{driver:'#ff00aa'},hidden:[]},{type:'relative',colors:{},hidden:[]}]}]}))""")
    page.reload();page.wait_for_selector('.driver-flag',state='attached')
    standings=page.locator('#dashboard [data-type=standings]')
    relative=page.locator('#dashboard [data-type=relative]')
    expect(standings.locator('tbody tr').first.locator('img')).to_have_attribute('src','/flags/iracing.svg')
    assert standings.locator('[data-element=safetyRating]').first.inner_text()=='SR A 3.42'
    assert page.locator('.driver-flag').evaluate_all('(images)=>images.every(i=>i.complete && i.naturalWidth>0)')
    for role in ['flag','irating','safetyRating']:
        standings.locator('.configure').click()
        page.locator('[data-visible='+role+']').uncheck()
        page.locator('#widget-form .form-actions .primary').click()
        expect(standings.locator('[data-element='+role+']').first).to_be_hidden()
        assert relative.locator('[data-element='+role+']').first.is_visible()
    page.reload();page.wait_for_selector('.driver-flag',state='attached')
    expect(standings.locator('[data-element=safetyRating]').first).to_be_hidden()
    page.locator('#settings').click()
    assert page.locator('[data-theme-choice]').count()==31
    expect(page.locator('[data-theme-choice=original]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-theme-choice=blue]').click()
    expect(page.locator('html')).to_have_attribute('data-theme','blue')
    expect(standings.locator('[data-role=driver]').first).to_have_css('color','rgb(255, 0, 170)')
    expect(page.locator('#country-driver')).to_have_count(0)
    expect(page.locator('#country-value')).to_have_count(0)
    expect(page.locator('#install-app')).to_have_count(0)
    page.locator('[data-theme-choice=light]').click()
    expect(page.locator('#modal')).to_have_css('background-color','rgb(255, 255, 255)')
    page.locator('#modal-close').click()
    page.reload();page.wait_for_selector('.driver-flag',state='attached')
    expect(page.locator('html')).to_have_attribute('data-theme','light')
    expect(relative.locator('tbody tr').first.locator('img')).to_have_attribute('src','/flags/iracing.svg')
    expect(standings.locator('[data-role=driver]').first).to_have_css('color','rgb(255, 0, 170)')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/ratings-daylight.png')
    expect(relative.locator('[data-role=irating]').first).to_have_css('color','rgb(28, 95, 171)')
    expect(relative.locator('[data-role=safetyRating]').first).to_have_css('background-color','rgb(40, 123, 224)')
    relative.locator('.configure').click()
    for role,color in [('irating','#3366ff'),('safetyRating','#8a2be2')]:
        page.locator('[data-color='+role+']').evaluate('(input,color)=>{input.value=color;input.dispatchEvent(new Event("input",{bubbles:true}))}',color)
    page.locator('#widget-form .form-actions .primary').click()
    expect(relative.locator('[data-role=irating]').first).to_have_css('color','rgb(51, 102, 255)')
    expect(relative.locator('[data-role=safetyRating]').first).to_have_css('background-color','rgb(138, 43, 226)')
    page.reload();page.wait_for_selector('.driver-flag',state='attached')
    expect(relative.locator('[data-role=safetyRating]').first).to_have_css('background-color','rgb(138, 43, 226)')
    assert not errors,errors
    browser.close()
    print('PASS: local flags/fallback, independent rating visibility, thirty themes, custom colors and no manual country or PWA settings')
