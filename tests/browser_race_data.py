"""Race semantics, independent visibility and tablet layouts against the actual UI."""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8017')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('IRBOARD_BROWSER','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':900},has_touch=True)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['session']['flags']=0
    snapshot['drivers'][10].update(pit=True,pit_elapsed=25.6,surface=1)
    snapshot['drivers'][0]['lap_difference']=1
    snapshot['drivers'][7]['lap_difference']=-1
    snapshot['drivers'][1]['gap_trend']='closing'
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.route('**/api/layout',lambda route:route.abort())
    page.goto(BASE);page.wait_for_selector('.widget')
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({pages:[{name:'Race',preset:'left-right',widgets:[{type:'standings'},{type:'relative'}]}]}))""")
    page.reload();page.wait_for_selector('.race-table')
    for kind in ['standings','relative']:
        widget=page.locator('#dashboard [data-type='+kind+']')
        expect(widget.locator('[data-car-idx="0"] [data-element=lapping]')).to_contain_text('LAPPING YOU +1L')
        expect(widget.locator('[data-car-idx="7"] [data-element=lapped]')).to_contain_text('LAPPED −1L')
        expect(widget.locator('[data-car-idx="10"] [data-status=pit]')).to_contain_text('PIT 25.6 s')
        expect(widget.locator('[data-car-idx="0"] [data-role=driver]')).to_have_css('color','rgb(255, 116, 123)')
        expect(widget.locator('[data-car-idx="7"] [data-role=driver]')).to_have_css('color','rgb(123, 181, 255)')
        assert widget.locator('td[data-element=bestTime]').count()==(12 if kind=='standings' else 0)
        expect(widget.locator('tr.me')).to_be_in_viewport()
        body=widget.locator('.widget-body')
        page.wait_for_timeout(150)
        body.evaluate("el=>{el.savedTable=el.querySelector('table');el.savedRow=el.querySelector('tr.me');}")
        body.evaluate("el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=0;}")
        assert body.evaluate('el=>Number(el.dataset.followPausedUntil)-performance.now()')>14000
        page.wait_for_timeout(250)
        assert body.evaluate('el=>el.scrollTop')==0
        body.evaluate("el=>delete el.dataset.followPausedUntil")
        expect(widget.locator('tr.me')).to_be_in_viewport()
        assert body.evaluate("el=>el.savedTable===el.querySelector('table')&&el.savedRow===el.querySelector('tr.me')")
        body.evaluate("el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=150;el.seenScrolls=[];el.addEventListener('scroll',()=>el.seenScrolls.push(el.scrollTop));}")
        page.wait_for_timeout(250)
        assert body.evaluate('el=>el.scrollTop')==150
        body.evaluate("el=>delete el.dataset.followPausedUntil")
        page.wait_for_timeout(250)
        assert body.evaluate('el=>el.seenScrolls.every(top=>top>0)'),body.evaluate('el=>el.seenScrolls')
    standings=page.locator('#dashboard [data-type=standings]')
    relative=page.locator('#dashboard [data-type=relative]')
    expect(standings.locator('th[data-element=gap]')).to_be_visible()
    expect(standings.locator('th[data-element=bestTime]')).to_be_hidden()
    expect(standings.locator('[data-car-idx="1"] td[data-element=gap]')).to_have_css('color','rgb(114, 223, 155)')
    snapshot['drivers'][1]['gap_trend']='opening'
    expect(standings.locator('[data-car-idx="1"] td[data-element=gap]')).to_have_css('color','rgb(255, 116, 123)')
    assert standings.locator('.race-timing [data-element=gap]').count()==0
    standings.locator('.configure').click()
    page.locator('[data-visible=pitStatus]').uncheck()
    page.locator('#widget-form .primary').click()
    expect(standings.locator('[data-car-idx="10"] [data-status=pit]')).to_be_hidden()
    expect(relative.locator('[data-car-idx="10"] [data-status=pit]')).to_be_visible()
    page.set_viewport_size({'width':800,'height':1100});page.wait_for_timeout(250)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('.widget-body').evaluate_all('(els)=>els.every(el=>el.scrollWidth<=el.clientWidth+2)'),page.locator('.widget-body').evaluate_all('(els)=>els.map(el=>[el.clientWidth,el.scrollWidth])')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/race-data-portrait.png')
    assert not errors,errors
    browser.close()
    print('PASS: lap relation, PIT timer, semantic colors, class timing, independent visibility, portrait and no browser errors')
