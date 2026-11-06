"""LAN dashboard HTTP server with explicit pit-service commands. No build step."""
import argparse
import json
import mimetypes
import os
import base64
import hashlib
import threading
import socket
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from .layout import LayoutStore
from .telemetry import Telemetry
from .network import connection_info, qr_svg
from .security import Pairing, loopback, valid_host, local_client

STATIC = Path(__file__).parent / 'static'

class LANServer(ThreadingHTTPServer):
    """Bound concurrent handlers so idle LAN sockets cannot spawn unlimited threads."""
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(32)
        super().__init__(*args,**kwargs)
    def server_close(self):
        telemetry = getattr(self, 'telemetry', None)
        if telemetry is not None:
            telemetry.buttonbox.stop()
        super().server_close()

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:
            self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


def create_server(host, port, telemetry, lan_host=None, layout_store=None):
    scheme = 'http'
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def host_ok(self):
            if valid_host(self.headers.get('Host'),server.server_port,server.allowed_names,scheme):return True
            self.reply(403,b'{"error":"Unrecognized server address"}','application/json');return False

        def local(self):
            return local_client(self.client_address[0], self.connection.getsockname()[0])

        def access(self):
            paired=server.pairing.authorized(self.headers.get('Cookie',''))
            allowed = self.local() or paired
            return dict(can_control=allowed, paired=paired, api_allowed=allowed)

        def do_GET(self):
            if not self.host_ok():return
            path = urlsplit(self.path).path
            # Only a minimal pairing screen is public. The dashboard and its data
            # cannot be fetched by a remote device before QR/PIN redemption.
            if path in ('/auth', '/auth.js', '/auth.css'):
                if path == '/auth' and self.access()['api_allowed']:
                    self.redirect('/')
                    return
                file = STATIC / {'/auth':'auth.html','/auth.js':'auth.js','/auth.css':'auth.css'}[path]
                self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                return
            if not self.access()['api_allowed']:
                if path.startswith('/api/'):
                    self.reply(401,b'{"error":"Pair this device using the QR or six-digit code shown on the server computer"}','application/json')
                elif path in ('/', '/connect'):
                    self.redirect('/auth')
                else:
                    self.reply(401,b'Pair this device first.', 'text/plain')
                return
            if path == '/api/connection':
                result = dict(server.connection_info, pairing_available=self.local(), qr_available=True)
                if self.local():
                    result['manual_pairing'] = server.pairing.manual_code()
                self.reply(200, json.dumps(result).encode(), 'application/json')
                return
            if path == '/qr.svg':
                requested = parse_qs(urlsplit(self.path).query).get('url', [''])[0]
                if requested not in server.connection_info['urls']:
                    self.reply(400, b'Choose one of the detected LAN URLs', 'text/plain')
                    return
                try:
                    self.reply(200, qr_svg(requested), 'image/svg+xml')
                except ImportError:
                    self.reply(503, b'QR support is missing. Install requirements.txt.', 'text/plain')
                return
            if re.fullmatch(r'/flags/(?:[a-z]{2}|gb-(?:eng|sct|wls|nir)|iracing)\.svg', path):
                flag = STATIC / path.lstrip('/')
                if flag.is_file():
                    self.reply(200, flag.read_bytes(), 'image/svg+xml', cache_control='public, max-age=86400')
                else:
                    self.reply(404, b'Not found', 'text/plain')
                return
            if path.startswith('/api/'):
                access=self.access()
                if not access['api_allowed']:
                    self.reply(401,b'{"error":"Pair this device using the QR or six-digit code"}','application/json');return
                if path == '/api/layout':
                    self.reply(200, json.dumps(server.layout_store.read()).encode(), 'application/json')
                    return
                requested = self.headers.get('X-IRBOARD-Sections') if path == '/api/telemetry' else None
                snapshot = telemetry.snapshot(sections=set(requested.split(','))) if requested is not None else telemetry.snapshot()
                snapshot['access']=dict(can_control=access['can_control'])
                if path == '/api/health':
                    result = {k: snapshot[k] for k in ('mode', 'connected', 'message', 'timestamp')}
                elif path == '/api/telemetry':
                    result = snapshot
                else:
                    self.reply(404, b'{"error":"Not found"}', 'application/json')
                    return
                self.reply(200, json.dumps(result, allow_nan=False, separators=(',', ':')).encode(), 'application/json')
                return
            files = {'/sw.js':'sw.js','/icon-192.png':'icon-192.png','/icon-512.png':'icon-512.png','/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/icon.svg': 'icon.svg', '/model.mjs': 'model.mjs', '/alerts.mjs':'alerts.mjs', '/experimental.mjs':'experimental.mjs', '/buttonbox.mjs':'buttonbox.mjs', '/default-layout.mjs': 'default-layout.mjs', '/widgets.mjs': 'widgets.mjs', '/fuel.mjs': 'fuel.mjs', '/format.mjs': 'format.mjs', '/race-view.mjs': 'race-view.mjs', '/driving-view.mjs': 'driving-view.mjs', '/countries.mjs': 'countries.mjs', '/themes.mjs': 'themes.mjs', '/connect': 'connect.html', '/connect.js': 'connect.js'}
            if path not in files:
                self.reply(404, b'Not found', 'text/plain')
                return
            file = STATIC / files[path]
            self.reply(200, file.read_bytes(), 'application/manifest+json' if file.suffix=='.webmanifest' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream')

        def do_POST(self):
            if not self.host_ok():return
            path=urlsplit(self.path).path
            if path not in ('/api/pit','/api/pair','/api/pairing','/api/layout','/api/buttonbox'):
                self.reply(404,b'{"error":"Not found"}','application/json');return
            origin=self.headers.get('Origin')
            if self.headers.get('Sec-Fetch-Site')=='cross-site' or (origin and
                    (urlsplit(origin).netloc.lower()!=self.headers.get('Host','').lower() or urlsplit(origin).scheme != scheme)):
                self.reply(403,b'{"error":"Cross-origin commands forbidden"}','application/json');return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.reply(415,b'{"error":"JSON required"}','application/json');return
            if path=='/api/pairing' and not self.local():
                self.reply(403,b'{"error":"Generate pairing codes on the server computer"}','application/json');return
            if path in ('/api/pit', '/api/layout', '/api/buttonbox') and not self.access()['can_control']:
                self.reply(401,b'{"error":"Pair this device using the QR or six-digit code from the server computer"}','application/json');return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if self.headers.get('Transfer-Encoding') or not 0<size<=(1048576 if path=='/api/layout' else 4096):raise ValueError('Invalid request size')
                self.connection.settimeout(5)
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
                if path=='/api/layout':
                    result=server.layout_store.update(payload.get('layout'), payload.get('revision'))
                    if result is None:
                        self.reply(409, json.dumps(server.layout_store.read()).encode(), 'application/json');return
                elif path=='/api/pairing':
                    url=payload.get('url')
                    if url not in server.connection_info['urls']:raise ValueError('Choose a detected LAN URL')
                    code=server.pairing.issue();join=url+'auth#pair='+code
                    svg=qr_svg(join)
                    result=dict(join_url=join,qr_image='data:image/svg+xml;base64,'+base64.b64encode(svg).decode(),expires_in=300)
                elif path=='/api/pair':
                    session=server.pairing.exchange(payload.get('code'),self.client_address[0])
                    if not session:
                        self.reply(401,b'{"error":"Code is incorrect, expired or already used. Check the current code on the computer. After too many attempts, wait one minute."}','application/json');return
                    self.reply(200,b'{"status":"paired"}','application/json',cookie=Pairing.cookie(session));return
                elif path=='/api/buttonbox':
                    owner = hashlib.sha256((self.headers.get('Cookie','') or self.client_address[0]).encode()).hexdigest()
                    result=telemetry.submit_buttonbox(payload, owner=owner)
                else:result=telemetry.submit_pit(payload)
                self.reply(200,json.dumps(result).encode(),'application/json')
            except (ValueError,UnicodeDecodeError) as exc:
                self.reply(400,json.dumps(dict(error=str(exc))).encode(),'application/json')
            except ImportError:
                self.reply(503,b'{"error":"Install requirements.txt for QR support"}','application/json')
            except (RuntimeError,TimeoutError) as exc:
                self.reply(409,json.dumps(dict(error=str(exc))).encode(),'application/json')
            except OSError:
                self.reply(503,b'{"error":"Unable to save shared layout"}','application/json')

        def redirect(self, location):
            self.reply(303, b'', 'text/plain', location=location)

        def reply(self, status, body, content_type, cookie=None, cache_control='no-store', location=None, attachment=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', cache_control)
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
            self.send_header('X-Frame-Options','SAMEORIGIN')
            if cookie:self.send_header('Set-Cookie',cookie)
            if location:self.send_header('Location',location)
            if attachment:self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, fmt, *args):
            # Do not write request targets, pairing codes or headers to logs.
            if len(args)>1 and str(args[1]) not in ('200','304'):
                import logging
                logging.getLogger('irboard.http').warning('HTTP response %s',args[1])

    server = LANServer((host, port), Handler)
    server.telemetry = telemetry
    server.connection_info = connection_info(host, server.server_port, lan_host, scheme=scheme)
    server.allowed_names={'127.0.0.1','localhost'}|{urlsplit(url).hostname.lower().rstrip('.') for url in server.connection_info['urls']}
    server.layout_store=layout_store or LayoutStore()
    server.pairing=Pairing()
    server.pairing.manual_code()
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='iR-Board — tablet dashboard for iRacing')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address (default: all LAN interfaces)')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--demo', action='store_true', help='Explicitly use simulated telemetry')
    parser.add_argument('--hz', default=20, type=int, choices=range(1, 61), metavar='1..60')
    parser.add_argument('--lan-host', help='Override the LAN address used in the QR code (IPv4 or DNS name)')
    parser.add_argument('--open-browser', action='store_true', help='Open the connection page after startup')
    args = parser.parse_args()
    telemetry = Telemetry(demo=args.demo, hz=args.hz)
    try:
        server = create_server(args.host, args.port, telemetry, lan_host=args.lan_host)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Cannot listen on {args.host}:{args.port}: {exc}\n')
    telemetry.start()
    print(f'iR-Board | {"DEMO — simulated data" if args.demo else "LIVE — waiting for iRacing SDK"}', flush=True)
    scheme = 'http'
    print(f'Listening on {args.host}:{args.port}. Open {scheme}://<PC-LAN-IP>:{args.port} on your tablet.', flush=True)
    # Pairing codes are deliberately never written to console/server logs.
    print(f'Open {server.connection_info["local_url"]}connect on this computer to see the pairing code.', flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(server.connection_info['local_url']+'connect')
    print('Use a trusted private LAN. Do not forward this HTTP port to the Internet.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        telemetry.stop()
