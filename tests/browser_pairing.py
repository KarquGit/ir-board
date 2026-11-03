"""HTTP pairing flow with separate PC/tablet browser contexts.

Uses a real HTTP server. An alternate loopback address is explicitly classified
as another computer so the regression runs without external networking.
"""
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect

# Run directly as `python tests/browser_pairing.py` from the repository root.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from irboard.layout import LayoutStore
from irboard.security import loopback
from irboard.server import create_server
from irboard.telemetry import Telemetry


with tempfile.TemporaryDirectory() as directory:
    telemetry=Telemetry(demo=True)
    server=create_server('0.0.0.0',0,telemetry,lan_host='127.0.0.2',
                         layout_store=LayoutStore(Path(directory)/'layout.json'))
    if not server.connection_info['urls']:
        server.server_close()
        raise RuntimeError('This regression needs a non-loopback LAN interface.')
    local=server.connection_info['local_url'].rstrip('/')
    remote=server.connection_info['urls'][0].rstrip('/')
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    telemetry.start();thread.start()
    try:
        with patch('irboard.server.local_client',side_effect=lambda peer,bound:bound=='127.0.0.1'), sync_playwright() as p:
            options=dict(headless=True,args=['--no-sandbox'])
            if os.environ.get('IRBOARD_BROWSER'):options['executable_path']=os.environ['IRBOARD_BROWSER']
            browser=p.chromium.launch(**options)
            pc_context=browser.new_context()
            pc=pc_context.new_page();errors=[]
            pc.on('pageerror',lambda error:errors.append(str(error)))
            pc.goto(local+'/')
            expect(pc.locator('#source-status')).to_have_text('DEMO')
            pc.goto(local+'/connect')
            expect(pc.locator('#manual-code')).to_have_text(__import__('re').compile(r'^[0-9]{6}$'))
            expect(pc.locator('#manual-pairing')).to_be_visible()
            expect(pc.locator('#connection-link')).to_have_attribute('href',remote+'/')
            expect(pc.locator('#copy-address')).to_have_count(0)
            # Loopback-only startup explains why no tablet URL/QR is shown.
            info=pc.request.get(local+'/api/connection').json()
            info.update(urls=[],lan_enabled=False,message='Local computer only.')
            pc.route('**/api/connection',lambda route:route.fulfill(json=info))
            pc.reload()
            expect(pc.locator('#connection-instructions')).to_contain_text('--host 0.0.0.0')
            expect(pc.locator('.qr-frame')).to_be_hidden()
            expect(pc.locator('#refresh-qr')).to_be_hidden()
            expect(pc.locator('#copy-address')).to_have_count(0)
            pc.unroute('**/api/connection');pc.reload()
            expect(pc.locator('#connection-link')).to_have_attribute('href',remote+'/')
            code=pc.locator('#manual-code').inner_text()
            tablet_context=browser.new_context(viewport={'width':800,'height':1100})
            tablet=tablet_context.new_page()
            tablet.on('pageerror',lambda error:errors.append(str(error)))
            tablet.goto(remote+'/')
            expect(tablet).to_have_url(remote+'/auth')
            assert tablet.request.get(remote+'/api/telemetry').status==401
            assert tablet.request.get(remote+'/app.js').status==401
            tablet.locator('#pair-code').fill('bad')
            tablet.locator('#pair-submit').click()
            expect(tablet).to_have_url(remote+'/auth')
            tablet.locator('#pair-code').fill(code)
            tablet.locator('#pair-submit').click()
            expect(tablet).to_have_url(remote+'/')
            expect(tablet.locator('#source-status')).to_have_text('DEMO')
            session=next(cookie for cookie in tablet_context.cookies() if cookie['name']=='irboard_session')
            assert not session['secure'] and session['httpOnly'] and session['sameSite']=='Strict'
            assert 'manual_pairing' not in tablet.request.get(remote+'/api/connection').json()
            tablet.goto(remote+'/connect')
            expect(tablet.locator('#manual-pairing')).to_be_hidden()
            expect(pc.locator('#manual-code')).not_to_have_text(code)

            # A fresh, separate tablet can scan the PC's single-use QR link.
            pair=pc.request.post(local+'/api/pairing',data=json.dumps({'url':remote+'/'}),
                                 headers={'Content-Type':'application/json'}).json()
            assert pair['join_url'].startswith(remote+'/auth#pair=')
            second_context=browser.new_context()
            second=second_context.new_page();second.on('pageerror',lambda error:errors.append(str(error)))
            second.goto(pair['join_url'])
            expect(second).to_have_url(remote+'/')
            expect(second.locator('#source-status')).to_have_text('DEMO')
            assert '#pair=' not in second.url
            retry_context=browser.new_context()
            retry=retry_context.new_page();retry.goto(pair['join_url'])
            expect(retry.locator('#pair-status')).to_contain_text('already used')
            expect(retry).to_have_url(remote+'/auth')

            # Expired/revoked sessions return to the pairing screen, not a stale portal.
            second.goto(remote+'/')
            with server.pairing.lock:
                server.pairing.sessions.clear()
            expect(second).to_have_url(remote+'/auth',timeout=10000)
            expect(second.locator('#pair-form')).to_be_visible()
            assert not errors,errors
            browser.close()
            print('PASS: HTTP, local-PC exemption and displayed PIN, private portal, manual and QR pairing, HttpOnly cookies, single use and session revocation')
    finally:
        server.shutdown();server.server_close();thread.join();telemetry.stop()
