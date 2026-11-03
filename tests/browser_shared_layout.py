"""Two real browser contexts share appearance. Run against a disposable data directory."""
import os
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('IRBOARD_TEST_URL', 'http://127.0.0.1:8002')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.environ.get('IRBOARD_BROWSER', '/usr/bin/chromium'), args=['--no-sandbox'])
    desktop = browser.new_context(viewport={'width': 1200, 'height': 850})
    tablet = browser.new_context(viewport={'width': 800, 'height': 1000}, has_touch=True)
    a, b = desktop.new_page(), tablet.new_page()
    errors = []
    for page in (a, b): page.on('pageerror', lambda error: errors.append(str(error)))
    revision = a.request.get(BASE+'/api/layout').json()['revision']
    seeded = a.request.post(BASE+'/api/layout', data={'revision':revision, 'layout':{'pages':[{'name':'RPM','widgets':[{'type':'tachometer','colors':{},'hidden':[],'layouts':{}}]}]}})
    assert seeded.ok
    a.goto(BASE)
    expect(a.locator('.leds')).to_be_visible()
    expect(a.locator('#save-state')).to_contain_text('synchronized')
    b.goto(BASE)
    expect(b.locator('.leds')).to_be_visible()
    # Hide the complete temperature row, change the title and color on desktop.
    before = a.locator('#dashboard .widget').bounding_box()['height']
    a.locator('.configure').click()
    a.locator('[data-visible=water]').uncheck()
    a.locator('[data-visible=oil]').uncheck()
    a.locator('#widget-form [name=title]').fill('Shared RPM')
    a.locator('[data-color=rpm]').fill('#12ab34')
    a.locator('#widget-form .primary').click()
    expect(b.locator('.widget-title')).to_have_text('Shared RPM')
    expect(b.locator('[data-element=water]').first).to_be_hidden()
    expect(b.locator('[data-element=oil]').first).to_be_hidden()
    expect(b.locator('[data-role=rpm]')).to_have_css('color', 'rgb(18, 171, 52)')
    assert a.locator('#dashboard .widget').bounding_box()['height'] < before * .85
    # Tablet edits propagate back and survive a new independent browser context.
    b.locator('.configure').click()
    b.locator('#widget-form [name=title]').fill('Tablet RPM')
    b.locator('#widget-form .primary').click()
    expect(a.locator('.widget-title')).to_have_text('Tablet RPM')
    third = browser.new_page()
    third.goto(BASE)
    expect(third.locator('.widget-title')).to_have_text('Tablet RPM')
    # Restoring temperatures restores the original frame size.
    a.locator('.configure').click()
    a.locator('[data-visible=water]').check()
    a.locator('[data-visible=oil]').check()
    a.locator('#widget-form .primary').click()
    assert abs(a.locator('#dashboard .widget').bounding_box()['height'] - before) < 3
    b.locator('#settings').click()
    b.locator('.custom-theme-editor summary').click()
    b.locator('[data-custom-color=accent]').fill('#ee8833')
    b.locator('#modal-close').click()
    expect(a.locator('html')).to_have_attribute('data-theme','custom')
    third.reload()
    expect(third.locator('html')).to_have_attribute('data-theme','custom')
    assert third.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")=='#ee8833'
    # Driving alerts are shared appearance and survive a fresh browser as well.
    b.locator('#settings').click()
    b.locator('#alert-flag-mode').select_option('center')
    b.locator('#alert-flag-duration').fill('6')
    b.locator('#alert-flag-animation').select_option('blink')
    b.locator('#alert-flag-visibility').select_option('active')
    b.locator('[data-race-flag=green]').uncheck()
    b.locator('#alert-spotter-mode').select_option('bars')
    b.locator('#modal-close').click()
    a.wait_for_function("() => JSON.parse(localStorage.getItem('irboard')).alerts?.spotter.mode==='bars'")
    third.reload()
    third.locator('#settings').click()
    expect(third.locator('#alert-flag-mode')).to_have_value('center')
    expect(third.locator('#alert-flag-duration')).to_have_value('6')
    expect(third.locator('#alert-flag-animation')).to_have_value('blink')
    expect(third.locator('#alert-flag-visibility')).to_have_value('active')
    expect(third.locator('[data-race-flag=green]')).not_to_be_checked()
    expect(third.locator('#alert-spotter-mode')).to_have_value('bars')
    third.locator('#modal-close').click()
    a.locator('.configure').click()
    a.locator('#widget-form [name=title]').fill('Saved before closing')
    a.locator('#widget-form .primary').click()
    a.close()
    expect(b.locator('.widget-title')).to_have_text('Saved before closing')
    assert not errors, errors
    browser.close()
    print('PASS: PC → tablet → PC appearance, hidden elements, colors, compact frame, fresh browser restoration')
