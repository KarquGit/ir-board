"""Multiclass colors and shapes, readable numbers and independent state rings."""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8022')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('IRBOARD_BROWSER','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':800},has_touch=True)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=page.request.get(BASE+'/api/telemetry').json()
    snapshot['session']['flags']=0
    snapshot['track_map']={'status':'ready','source':'sdk-gps','points':[[0,0],[100,0],[140,80],[80,150],[0,110]],'message':'Local telemetry line'}
    classes=[('GT3','circle','#111111'),('GTP','diamond','#ee3366'),('LMP2','square','#3388ff'),('LMP3','triangle','#ffaa33'),('GT4','pentagon','#aa77ff'),('TCR','hexagon','#33cccc')]
    snapshot['drivers']=[dict(id=i,pct=(i+.2)/6,number=i+1,class_id=i,class_name=name,class_color=color,player=i==0,pit=i in (0,2)) for i,(name,shape,color) in enumerate(classes)]
    def telemetry(route):
        snapshot['timestamp']=time.time();snapshot['sample_age']=0
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry',telemetry)
    page.route('**/api/layout',lambda route:route.abort())
    page.goto(BASE);page.wait_for_selector('.widget')
    page.evaluate("""()=>localStorage.setItem('irboard',JSON.stringify({pages:[{name:'Map',preset:'single',widgets:[{type:'learnedmap'}]}]}))""")
    page.reload();page.wait_for_selector('.map-marker-body')
    for i,(name,shape,color) in enumerate(classes):
        marker=page.locator(f'.learned-map g[data-car-idx="{i}"]')
        expect(marker.locator('[data-map-marker]')).to_have_attribute('data-map-marker',shape)
        assert marker.locator('[data-map-marker]').get_attribute('style')=='fill:'+color
    expect(page.locator('.map-class-legend > span')).to_have_count(6)
    own=page.locator('.learned-map g[data-car-idx="0"]')
    expect(own.locator('.map-state-ring')).to_have_count(2)
    expect(own.locator('text')).to_have_css('fill','rgb(255, 255, 255)')
    for role in ['player','pitCar','rival','classLegend','carNumber']:
        page.locator('.configure').click()
        page.locator('[data-visible='+role+']').uncheck()
        page.locator('#widget-form .primary').click()
        page.wait_for_function("role=>[...document.querySelectorAll('#dashboard [data-element='+role+']')].every(n=>getComputedStyle(n).display==='none')",arg=role)
        page.locator('.configure').click();page.locator('[data-visible='+role+']').check();page.locator('#widget-form .primary').click()
    for size in [{'width':800,'height':1280},{'width':1280,'height':800}]:
        page.set_viewport_size(size);page.wait_for_timeout(150)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/map-multiclass.png')
    assert not errors,errors
    browser.close()
    print('PASS: six class colors/shapes, player plus PIT rings, number contrast, independent visibility, tablet layouts')
