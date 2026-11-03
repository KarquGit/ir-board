"""Live readback clears completed services without clobbering unsent edits."""
import json
import os
import time
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('IRBOARD_TEST_URL', 'http://127.0.0.1:8005')
with sync_playwright() as p:
    options = dict(headless=True, args=['--no-sandbox'])
    if os.environ.get('IRBOARD_BROWSER'):
        options['executable_path'] = os.environ['IRBOARD_BROWSER']
    browser = p.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1024, 'height': 800}, has_touch=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    snapshot = page.request.get(BASE + '/api/telemetry').json()
    snapshot.update(mode='live', connected=True, access={'can_control': True})
    snapshot['pit'].update(available=True, can_control=True, flags=0, fuel=0, status=0,
                           compounds=[{'index': 0, 'name': 'Dry'}, {'index': 1, 'name': 'Wet'}])
    def telemetry(route):
        snapshot['timestamp'] = time.time()
        route.fulfill(json=snapshot)
    page.route('**/api/telemetry', telemetry)
    plans = []
    def apply(route):
        plan = route.request.post_data_json
        plans.append(plan)
        snapshot['pit'].update(flags=1 | 16, fuel=plan['fuel'], status=0)
        route.fulfill(json={'status': 'sent', 'message': 'Commands broadcast through the SDK.'})
    page.route('**/api/pit', apply)
    # Isolate local layout fixtures; shared-server behavior has its own regression.
    page.route('**/api/layout', lambda route: route.abort())
    page.goto(BASE)
    page.wait_for_selector('.widget')
    page.evaluate("""() => localStorage.setItem('irboard', JSON.stringify({version:4, active:0,
      pages:[{name:'Pit test',preset:'full',widgets:[{type:'pit',title:'Pit stop',colors:{},hidden:[],layouts:{}}]}]}))""")
    page.reload()
    form = page.locator('.pit-form')
    lf = form.locator('input[name=lf]')
    rf = form.locator('input[name=rf]')
    expect(form.locator('select[name=compound] option')).to_have_text(['Keep current', 'Dry', 'Wet'])
    form.locator('select[name=compound]').select_option('1')
    lf.check()
    calculated = form.locator('[name=fuel]').input_value()
    assert form.locator('[name=fuel]').get_attribute('type') == 'hidden'
    # An unrelated telemetry update cannot erase the draft.
    page.wait_for_timeout(500)
    expect(lf).to_be_checked()
    expect(form.locator('input[name=fuel]')).to_have_value(calculated)
    form.locator('.pit-apply').click()
    expect(form.locator('[name=fuel]')).to_have_value(calculated)
    snapshot['pit']['status'] = 1
    expect(form.locator('.pit-result')).to_contain_text('in progress')
    snapshot['pit'].update(flags=0, fuel=0, status=2)
    expect(lf).not_to_be_checked()
    expect(form.locator('[name=fuel]')).to_have_value(calculated)
    expect(form.locator('.pit-result')).to_contain_text('completed')
    assert len(plans) == 1 and plans[0]['tires'] == {'lf': round(snapshot['pit']['pressures']['lf'])}
    assert plans[0]['compound'] == 1
    # New edits are protected, including stepper and All/None touch buttons.
    rf.check()
    assert form.locator('[data-step]').count() == 0
    page.wait_for_timeout(500)
    expect(rf).to_be_checked()
    expect(form.locator('[name=fuel]')).to_have_value(calculated)
    form.locator('[data-tires=all]').click()
    page.wait_for_timeout(400)
    expect(lf).to_be_checked()
    assert form.locator('.pit-read').count() == 0
    form.locator('.pit-apply').click()
    page.wait_for_timeout(100)
    snapshot['pit'].update(flags=0, fuel=0, status=2)
    expect(lf).not_to_be_checked()
    expect(rf).not_to_be_checked()
    snapshot['pit']['compounds'] = []
    expect(form.locator('select[name=compound]')).to_be_disabled()
    form.locator('.pit-apply').click()
    page.wait_for_timeout(400)
    assert plans[-1]['compound'] is None
    # Loading a fuel proposal changes only the draft until Apply.
    snapshot['car'].update(fuel=5,lap_pct=0)
    snapshot['fuel']['average']=2
    snapshot['session'].update(type='Race',laps_remaining=10,remaining=2000,state=4)
    form.locator('[data-fuel-target=stint]').click()
    form.locator('[name=stint_length]').fill('10')
    form.locator('[name=fuel_reserve]').fill('0')
    # Every numeric planner field has large +/- controls, and target tiles are accessible.
    expect(form.locator('[data-fuel-target=stint]')).to_have_attribute('aria-pressed','true')
    expect(form.locator('[data-fuel-target=finish]')).to_have_attribute('aria-pressed','false')
    form.locator('[data-number-field=stint_length][data-direction="1"]').click()
    expect(form.locator('[name=stint_length]')).to_have_value('11')
    form.locator('[data-number-field=stint_length][data-direction="-1"]').click()
    expect(form.locator('[name=stint_length]')).to_have_value('10')
    form.locator('[data-number-field=fuel_reserve][data-direction="-1"]').click()
    expect(form.locator('[name=fuel_reserve]')).to_have_value('0')
    assert form.locator('[name=fuel_consumption]').count() == 0
    form.locator('[data-stint-unit=minutes]').click()
    expect(form.locator('[data-stint-unit=minutes]')).to_have_attribute('aria-pressed','true')
    form.locator('[data-stint-unit=laps]').click()
    page.wait_for_timeout(200)
    before=len(plans)
    form.locator('.fuel-calculate').click()
    expect(form.locator('[name=fuel]')).to_have_value('15')
    assert len(plans)==before
    form.locator('.pit-apply').click()
    page.wait_for_timeout(300)
    assert plans[-1]['fuel']==15
    assert form.locator('.hint').count()==0
    snapshot['session']['type']='Practice'
    form.locator('[data-fuel-target=finish]').click()
    expect(form.locator('.fuel-estimate')).to_contain_text('Choose Next stint for Practice')
    expect(form.locator('.calculated-fuel')).to_have_text('Fuel estimate unavailable')
    form.locator('[data-fuel-target=stint]').click()
    expect(form.locator('[name=fuel]')).to_have_value('15')
    snapshot['fuel']={'average':None,'message':'Recording a full clean lap.'}
    expect(form.locator('.fuel-estimate')).to_have_text('Recording a full clean lap.')
    assert not errors, errors
    browser.close()
    print('PIT readback, completion, draft protection and touch controls passed')
