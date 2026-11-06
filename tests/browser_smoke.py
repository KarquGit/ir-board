"""Optional browser regression. pip install playwright; playwright install chromium.
IRBOARD_BROWSER may select an existing Chrome executable. Start server --demo first.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8001')
OUT=Path('test-results');OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    options=dict(headless=True,args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):options['executable_path']=os.environ['IRBOARD_BROWSER']
    browser=p.chromium.launch(**options)
    context=browser.new_context(viewport={'width':1024,'height':600},has_touch=True)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # Isolate local layout fixtures; shared-server behavior has its own regression.
    page.route('**/api/layout', lambda route: route.abort())
    page.goto(BASE);page.wait_for_selector('.leds')
    assert page.locator('.widget').count()==1
    # All eight handles actually change the rectangle and persist after a reload.
    for edge,dx,dy in [('n',0,20),('ne',20,20),('e',20,0),('se',20,20),('s',0,20),('sw',20,20),('w',20,0),('nw',20,20)]:
        page.evaluate('''() => {const s=JSON.parse(localStorage.getItem('irboard'));s.active=0;s.pages[0].widgets[0].layouts={landscape:{x:.2,y:.2,w:.6,h:.6},portrait:{x:.2,y:.2,w:.6,h:.6}};localStorage.setItem('irboard',JSON.stringify(s));}''')
        page.reload();page.wait_for_selector('.leds');page.locator('#edit').click()
        before=page.locator('.widget').bounding_box();handle=page.locator('[data-edge='+edge+']').bounding_box()
        x,y=handle['x']+handle['width']/2,handle['y']+handle['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=5);page.mouse.up()
        after=page.locator('.widget').bounding_box()
        canvas_after=page.locator('#dashboard').bounding_box()
        assert any(abs(after[k]-before[k])>3 for k in ('x','y','width','height')),(edge,before,after)
        page.reload();page.wait_for_selector('.leds');persisted=page.locator('.widget').bounding_box()
        canvas_reload=page.locator('#dashboard').bounding_box()
        assert abs(persisted['width']/canvas_reload['width']-after['width']/canvas_after['width'])<.005,(edge,persisted,after)
        assert abs(persisted['height']/canvas_reload['height']-after['height']/canvas_after['height'])<.005,(edge,persisted,after)
        assert abs((persisted['y']-canvas_reload['y'])/canvas_reload['height']-(after['y']-canvas_after['y'])/canvas_after['height'])<.005
    # Restore automatic fitting, then style one specific element and the whole panel.
    page.locator('#page-options').click();page.locator('#reset-layout').click()
    page.locator('.configure').click()
    for role,color in [('rpm','#ff00aa'),('background','#102030'),('water','#00aaff')]:
        page.locator('[data-color='+role+']').evaluate('(el,color)=>{el.value=color;el.dispatchEvent(new Event("input",{bubbles:true}))}',color)
    expect(page.locator('.preview [data-role=rpm]')).to_have_css('color','rgb(255, 0, 170)')
    page.locator('#widget-form button[type=submit], #widget-form button:not([type])').last.click()
    page.reload();page.wait_for_selector('.leds')
    assert page.locator('#dashboard .widget [data-role=rpm]').evaluate('(el)=>getComputedStyle(el).color')=='rgb(255, 0, 170)'
    # Cancel does not save preview changes.
    page.locator('.configure').click();page.locator('[data-color=rpm]').evaluate('(el)=>{el.value="#abcdef";el.dispatchEvent(new Event("input",{bubbles:true}))}')
    page.locator('#cancel-colors').click()
    expect(page.locator('#dashboard [data-role=rpm]')).to_have_css('color','rgb(255, 0, 170)')
    assert page.locator('#dashboard .widget [data-role=rpm]').evaluate('(el)=>getComputedStyle(el).color')=='rgb(255, 0, 170)'
    # Fullscreen is frame-free. Double touch on changing telemetry still exits.
    page.locator('#fullscreen').click();page.wait_for_timeout(200)
    assert page.locator('body').evaluate('el=>el.classList.contains("focus")')
    assert not page.locator('.rail').is_visible()
    assert not page.locator('.configure').is_visible()
    assert page.locator('.widget').evaluate('el=>getComputedStyle(el).borderTopWidth')=='0px'
    cdp=context.new_cdp_session(page)
    def touch(x,y):
        cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    touch(200,190);page.wait_for_timeout(90);touch(200,190);page.wait_for_timeout(200)
    assert not page.locator('body').evaluate('el=>el.classList.contains("focus")')
    # Real touch swipe works despite changing DOM telemetry nodes.
    page.locator('#fullscreen').click();page.wait_for_timeout(100)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':700,'y':240}]})
    for x in [660,600,540,480]:cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':240}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(200)
    assert page.locator('.widget').count()==2
    page.locator('.widget-body').first.dblclick(position={'x':30,'y':30});page.wait_for_timeout(200)
    # A third widget stays on the current page; templates never impose limits.
    page.locator('#layouts').click();page.locator('[data-preset=left-right]').click()
    page.locator('#add-widget').click();page.locator('[data-kind=radar]').click();assert page.locator('.widget').count()==3
    assert page.locator('#layout-title').inner_text()=='Page 2'
    # Learned map uses only telemetry and displays all demo drivers.
    page.locator('[data-page="4"]').first.click();page.wait_for_selector('.map-marker-body')
    assert page.locator('.map-marker-body').count()==12
    page.screenshot(path=str(OUT/'flat-map.png'))
    # Pit editing survives polling and never submits until explicitly applied.
    page.locator('[data-page="5"]').first.click();page.wait_for_selector('.pit-form')
    form=page.locator('.pit-form');form.locator('[data-tires=all]').click();calculated=form.locator('[name=fuel]').input_value()
    page.wait_for_timeout(500);assert form.locator('[name=fuel]').input_value()==calculated
    seen=[];page.on('request',lambda r:seen.append(r.post_data_json) if r.url.endswith('/api/pit') else None)
    assert not seen;form.locator('.pit-apply').click();expect(form.locator('.pit-result')).to_contain_text('DEMO')
    assert seen[0]['fuel']==int(calculated) and len(seen[0]['tires'])==4
    page.screenshot(path=str(OUT/'pit-tablet.png'))
    # Small portrait tablet keeps the pit panel visible without horizontal overflow.
    page.set_viewport_size({'width':600,'height':800});page.wait_for_timeout(200)
    assert page.locator('.widget').count()==1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#fullscreen').click();page.wait_for_timeout(100);page.screenshot(path=str(OUT/'portrait-fullscreen.png'))
    # Screenshot-sized display; one tachometer panel fills the whole surface.
    page.locator('.widget-body').first.dblclick(position={'x':20,'y':20});page.wait_for_timeout(100)
    page.locator('[data-page="0"]').first.click();page.set_viewport_size({'width':814,'height':250});page.locator('#fullscreen').click();page.wait_for_timeout(200)
    page.screenshot(path=str(OUT/'small-fullscreen.png'))
    assert not errors,errors
    # Migration of existing installations is verified in the actual browser too.
    page.evaluate('''()=>localStorage.setItem('irboard',JSON.stringify({active:0,pages:[{name:'Old layout',widgets:['inputs','tachometer','laps','fuel','systems'].map(type=>({type,w:4,h:4}))}]}))''')
    page.reload();page.wait_for_selector('.widget')
    saved=page.evaluate('JSON.parse(localStorage.getItem("irboard"))')
    assert [len(p['widgets']) for p in saved['pages']]==[5]
    assert sum(len(p['widgets']) for p in saved['pages'])==5
    browser.close()
    print('PASS: 8 resize handles, persistence, color preview/save/cancel, fullscreen, double touch, touch swipe, unlimited widgets, learned map, pit form, portrait, migration; no browser errors')
