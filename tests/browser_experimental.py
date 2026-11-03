"""iR-logic colors, automatic carousel, retired-widget migration and references."""
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8030')
OUT=Path('test-results');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('IRBOARD_BROWSER','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1250,'height':950})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    assert snapshot['mode']=='demo' and 'navigator_map' not in snapshot
    requests=[]
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        requests.append(route.request.headers.get('x-irboard-sections',''))
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.route('**/api/layout',lambda route:route.abort())
    page.goto(BASE);page.wait_for_selector('.widget')
    assert page.evaluate("JSON.parse(localStorage.getItem('irboard')).pages.length")==7
    saved=page.evaluate("JSON.parse(localStorage.getItem('irboard'))")
    import json
    supplied=json.loads(Path('docs/default-layout.json').read_text())
    def without_ids(value):
        if isinstance(value,dict):return {k:without_ids(v) for k,v in value.items() if k!='id'}
        if isinstance(value,list):return [without_ids(v) for v in value]
        return value
    assert without_ids(saved)==without_ids(supplied)
    for index,expected in enumerate(supplied['pages']):
        page.evaluate("index=>{const s=JSON.parse(localStorage.getItem('irboard'));s.active=index;localStorage.setItem('irboard',JSON.stringify(s));}",index)
        page.reload()
        expect(page.locator('#dashboard .widget')).to_have_count(len(expected['widgets']))
        assert page.locator('#dashboard .widget').evaluate_all("items=>items.map(el=>el.dataset.type)")==[w['type'] for w in expected['widgets']]
    page.locator('#add-widget').click()
    expect(page.locator('[data-kind=irlogic] strong')).to_have_text('iR-logic')
    assert page.locator('[data-kind=navigator],[data-kind=brakecoach]').count()==0
    page.locator('#modal-close').click()
    page.evaluate("localStorage.setItem('irboard',JSON.stringify({pages:[{name:'Custom',widgets:[{type:'navigator'},{type:'irlogic',layouts:{landscape:{x:0,y:0,w:1,h:1}}},{type:'brakecoach'}]}]}))")
    page.reload()
    logic=page.locator('[data-type=irlogic]')
    expect(logic.locator('.experimental-badge')).to_have_count(0)
    assert page.locator('.widget').count()==1
    assert page.evaluate("JSON.parse(localStorage.getItem('irboard')).pages[0].name")=='Custom'
    def center(number):
        cell=logic.locator(f'.sector-cell.active[data-sector-index="{number-1}"]')
        window=logic.locator('.sector-window').bounding_box()
        for _ in range(30):
            if any(abs((e.bounding_box()['x']+e.bounding_box()['width']/2)-(window['x']+window['width']/2))<3 for e in cell.all()):return
            page.wait_for_timeout(50)
        raise AssertionError('Current sector was not centered')
    for pct,number in [(.5,4),(.93,7),(.01,1)]:
        snapshot['car']['lap_pct']=pct;page.wait_for_timeout(400);center(number)
    page.evaluate("window.originalStrip=document.querySelector('.sector-strip')")
    page.wait_for_timeout(250)
    assert page.evaluate("originalStrip===document.querySelector('.sector-strip')")
    samples=[dict(pct=i/100,time=i) for i in range(101)]
    snapshot['car'].update(lap_pct=.65,in_car=True,pit=False,garage=False,replay=False)
    snapshot['sectors']=[dict(number=i+1,start=i/4,end=(i+1)/4) for i in range(4)]
    snapshot['coaching'].update(current_time=65,trace=[dict(pct=0,time=0),dict(pct=.25,time=24),dict(pct=.5,time=51),dict(pct=.65,time=65)],references=dict(session='ref',personal='ref',last='ref'),laps=dict(ref=dict(lap_time=100,samples=samples)))
    gain=logic.locator('.sector-cell[data-sector-index="0"]').first
    loss=logic.locator('.sector-cell[data-sector-index="1"]').first
    current=logic.locator('.sector-cell.active')
    expect(gain).to_have_attribute('data-state','gain')
    expect(gain.locator('strong')).to_have_css('color','rgb(114, 223, 155)')
    expect(loss).to_have_attribute('data-state','loss')
    expect(loss.locator('strong')).to_have_css('color','rgb(255, 116, 123)')
    expect(current).to_have_attribute('data-state','current')
    expect(current.locator('strong')).to_have_css('color','rgb(255, 159, 28)')
    logic.locator('.configure').click()
    page.locator('[name=coach-reference]').select_option('personal')
    page.locator('#widget-form .primary').click()
    page.reload();expect(logic.locator('.experimental-badge')).to_have_count(0)
    assert page.evaluate("JSON.parse(localStorage.getItem('irboard')).pages[0].widgets[0].coachReference")=='personal'
    page.add_style_tag(content='#race-flag-overlay,#screen-spotter {display:none !important;}')
    logic.screenshot(path=str(OUT/'irlogic-sector-colors.png'))
    page.set_viewport_size({'width':800,'height':1100})
    expect(logic.locator('.logic-delta')).to_be_visible()
    snapshot['coaching']={};snapshot['sectors']=[]
    expect(logic.locator('.experiment-note')).to_contain_text('Record a complete clean lap')
    assert any('coaching' in value for value in requests)
    assert not errors,errors
    browser.close()
    print('PASS: retired widgets migrate safely; seven-sector carousel; green gains, red losses and orange current sector; reference persistence and portrait')
