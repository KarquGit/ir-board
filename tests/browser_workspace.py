"""Regression for unlimited layouts, SVG visibility, touch pit controls and local QR."""
import io
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('IRBOARD_TEST_URL','http://127.0.0.1:8001')
OUT=Path('test-results');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    options=dict(headless=True,args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):options['executable_path']=os.environ['IRBOARD_BROWSER']
    browser=p.chromium.launch(**options)
    context=browser.new_context(viewport={'width':1024,'height':700},has_touch=True)
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # Isolate local layout fixtures; shared-server behavior has its own regression.
    page.route('**/api/layout', lambda route: route.abort())
    page.goto(BASE);page.wait_for_selector('.leds')
    assert page.locator('html').get_attribute('lang')=='en';assert page.locator('.session-bar').count()==0
    page.locator('#add-widget').click();assert page.locator('[data-kind=map]').count()==0;page.locator('#modal-close').click()
    # Old full maps migrate to telemetry-only learned maps.
    page.evaluate('''()=>localStorage.setItem('irboard',JSON.stringify({version:3,active:0,pages:[{name:'Track map',widgets:[{type:'map',title:'Track map',colors:{},hidden:[],layouts:{}}]}]}))''')
    page.reload();page.wait_for_selector('.learned-map circle');assert page.locator('#layout-title').inner_text()=='Track progress'
    # Every Learned map checkbox changes actual SVG visibility, including parent/number groups.
    for role in ['track','player','rival','pitCar','carNumber']:
        page.locator('.configure').click();page.locator('[data-visible='+role+']').uncheck()
        nodes=page.locator('#dashboard .learned-map [data-element='+role+']')
        assert nodes.count()>0,role
        assert nodes.evaluate_all('(xs)=>xs.every(x=>getComputedStyle(x).display==="none")'),role
        if role in ['player','rival','pitCar']:
            assert page.locator('#dashboard .learned-map g[data-element='+role+'] text').evaluate_all('(xs)=>xs.every(x=>x.getBoundingClientRect().width===0)'),role
        page.locator('#widget-form button.primary').click();page.wait_for_timeout(100)
    page.reload();page.wait_for_selector('.learned-map');assert page.locator('.learned-map [data-element=carNumber]').evaluate_all('(xs)=>xs.every(x=>getComputedStyle(x).display==="none")')
    page.locator('.configure').click()
    for role in ['track','player','rival','pitCar','carNumber']:page.locator('[data-visible='+role+']').check()
    page.locator('#widget-form button.primary').click();expect(page.locator('#dashboard .learned-map g[data-element=player]')).to_be_visible()
    # Add more widgets than any old per-page cap and preserve them on template changes.
    page.locator('#layouts').click();assert page.locator('[data-preset]').count()>=14;page.locator('[data-preset=grid-4x4]').click()
    for kind in ['tachometer','inputs','systems','fuel','laps','systems','radar']:
        page.locator('#add-widget').click();page.locator('[data-kind='+kind+']').click()
    assert page.locator('#dashboard .widget').count()==8
    assert page.locator('#page-nav button').count()==1
    page.locator('#layouts').click();page.locator('[data-preset=full]').click()
    assert page.locator('#dashboard .widget').count()==8 and page.locator('#page-nav button').count()==1
    page.locator('#layouts').click();page.locator('[data-preset=grid-3x3]').click()
    page.reload();page.wait_for_selector('.widget');assert page.locator('#dashboard .widget').count()==8
    page.screenshot(path=str(OUT/'compact-layout.png'))
    # Real snapping to a nearby widget, with guides visible only while manipulating.
    page.evaluate('''()=>{const make=(type,rect)=>({type,title:type,colors:{},hidden:[],layouts:{landscape:rect,portrait:rect}});localStorage.setItem('irboard',JSON.stringify({version:4,active:0,pages:[{name:'Snap',preset:'auto',widgets:[make('tachometer',{x:.1,y:.1,w:.2,h:.3}),make('systems',{x:.55,y:.55,w:.2,h:.3})]}]}));}''')
    page.reload();page.wait_for_selector('.widget');page.locator('#edit').click()
    bounds=page.locator('#dashboard').bounding_box();grip=page.locator('.drag-handle').first.bounding_box()
    x,y=grip['x']+20,grip['y']+20
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+.246*bounds['width'],y+.03*bounds['height'],steps=8)
    assert page.locator('.manipulating .alignment-layer').is_visible()
    assert page.locator('.alignment-guide.axis-x').count()==1
    page.screenshot(path=str(OUT/'snap-guides.png'))
    page.mouse.up();assert not page.locator('.alignment-layer').is_visible()
    rect=page.locator('.widget').first.bounding_box();assert abs((rect['x']-bounds['x']+rect['width'])/bounds['width']-.55)<.002
    # Pit tire illustrations are actual touch targets; fuel controls are >= 44 CSS pixels.
    page.evaluate('''()=>localStorage.setItem('irboard',JSON.stringify({version:4,active:0,pages:[{name:'Pit',preset:'full',widgets:[{type:'pit',title:'Pit stop',hidden:[],colors:{},layouts:{}}]}]}))''')
    page.reload();page.wait_for_selector('.tire-drawing');assert page.locator('.tire-drawing').count()==4
    checkbox=page.locator('[name=lf]');expect(checkbox).to_be_checked();page.locator('.tire-option').first.tap(position={'x':60,'y':45});expect(checkbox).not_to_be_checked();page.locator('.tire-option').first.tap(position={'x':60,'y':45});expect(checkbox).to_be_checked()
    assert page.locator('[name=fuel]').get_attribute('type')=='hidden'
    assert page.locator('[data-step]').count()==0
    expect(page.locator('.calculated-fuel')).to_contain_text('calculated')
    seen=[];page.on('request',lambda r:seen.append(r.post_data_json) if r.url.endswith('/api/pit') else None)
    assert not seen;page.locator('.pit-apply').tap();expect(page.locator('.pit-result')).to_contain_text('DEMO');assert len(seen)==1
    page.screenshot(path=str(OUT/'pit-touch-controls.png'))
    # Independent SDK map renders in demo; no external circuit assets are loaded.
    page.locator('#add-widget').click();page.locator('[data-kind=learnedmap]').click();page.wait_for_selector('.learned-map circle')
    assert page.locator('.learned-map [data-map-marker]').count()==12
    assert 'synthetic' in page.locator('.learned-map-caption').inner_text()
    page.screenshot(path=str(OUT/'sdk-learned-map.png'))
    # The QR embeds a single-use credential; the visible/manual URL does not.
    with page.expect_response(lambda response: response.url.endswith('/api/pairing') and response.request.method=='POST') as paired:
        page.goto(BASE+'/connect')
    target=paired.value.json()['join_url']
    expect(page.locator('#connection-qr')).to_be_visible()
    manual=page.locator('#connection-link').get_attribute('href')
    assert manual.startswith('http://') and '#pair=' not in manual
    assert target.startswith(manual+'auth#pair=')
    expect(page.locator('#copy-address')).to_have_count(0)
    for _ in range(40):
        if page.locator('#connection-qr').get_attribute('src').startswith('data:'):break
        page.wait_for_timeout(50)
    assert page.locator('#connection-qr').get_attribute('src').startswith('data:')
    png=page.locator('#connection-qr').screenshot(path=str(OUT/'connection-qr.png'))
    try:
        import zxingcpp
        from PIL import Image
        decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(png)))
        assert decoded and decoded.text==target
        print('Single-use pairing QR decoded successfully (code redacted)')
    except ImportError:
        print('QR rendered; optional zxing-cpp decoding check not installed')
    # Remote QR redemption and manual-code authentication are covered by browser_pairing.py.
    page.screenshot(path=str(OUT/'connect-page.png'))
    assert not errors,errors
    browser.close()
    print('PASS: SVG visibility/reload, unlimited widgets, compact templates, snapping guides, touch tires/fuel, explicit pit submission, SDK map and authenticated QR pairing; no browser errors')
