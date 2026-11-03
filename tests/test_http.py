import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from irboard.server import create_server
from irboard.telemetry import Telemetry, DemoSource

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.telemetry=Telemetry(demo=True);cls.telemetry._data.update(connected=True,pit={'can_control':True})
        cls.server=create_server('127.0.0.1',0,cls.telemetry)
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,body=None,token='test-token',origin=None,ctype='application/json'):
        headers={'Authorization':'Bearer '+token,'Content-Type':ctype}
        if origin:headers['Origin']=origin
        request=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        return urlopen(request,timeout=5)
    def test_modules_and_api(self):
        for path in ['/','/app.js','/model.mjs','/alerts.mjs','/widgets.mjs','/style.css','/api/health','/connect','/connect.js','/api/connection']:
            with self.request(path) as response:self.assertEqual(response.status,200)
        with self.assertRaises(HTTPError) as error:self.request('/api/tracks/239')
        self.assertEqual(error.exception.code,404)
    def test_local_country_assets_and_fallback(self):
        for path in ['/countries.mjs','/themes.mjs','/flags/pl.svg','/flags/iracing.svg']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)
                if path.startswith('/flags/'): self.assertIn('max-age',response.headers['Cache-Control'])
        for path in ['/flags/../../LICENSE','/flags/zz.svg']:
            with self.assertRaises(HTTPError) as error:self.request(path)
            self.assertEqual(error.exception.code,404)
    def test_optional_sections_reduce_payload_without_changing_default_api(self):
        with self.telemetry._lock:
            self.telemetry._data = DemoSource().read()
        full = self.request('/api/telemetry').read()
        request = Request(self.base+'/api/telemetry', headers={'Authorization':'Bearer test-token', 'X-IRBOARD-Sections':''})
        with urlopen(request,timeout=5) as response: lean=response.read()
        data=json.loads(lean)
        self.assertEqual(data['trace'],[])
        self.assertEqual(data['track_map'],{})
        self.assertEqual(data['car'],json.loads(full)['car'])
        self.assertLess(len(lean),len(full)*.6)
        self.assertTrue(self.telemetry.snapshot()['track_map']['points'])
    def test_local_computer_does_not_require_credentials(self):
        with self.request('/api/pit',{},token='wrong') as response:
            self.assertEqual(response.status,200)
    def test_cross_origin_and_form_posts_rejected(self):
        for origin,ctype,code in [('http://evil.example','application/json',403),(self.base,'text/plain',415)]:
            with self.assertRaises(HTTPError) as error:self.request('/api/pit',{},origin=origin,ctype=ctype)
            self.assertEqual(error.exception.code,code)
    def test_valid_demo_and_invalid_plans(self):
        with self.request('/api/pit',{'fuel':20},origin=self.base) as response:self.assertEqual(json.load(response)['status'],'demo')
        with self.assertRaises(HTTPError) as error:self.request('/api/pit',{'fuel':-1},origin=self.base)
        self.assertEqual(error.exception.code,400)

    def test_browser_modules_and_regional_flags_are_served(self):
        for path in ['/sw.js','/icon-192.png','/icon-512.png','/default-layout.mjs','/format.mjs','/race-view.mjs','/driving-view.mjs','/flags/gb-eng.svg','/flags/gb-sct.svg','/flags/gb-wls.svg','/flags/gb-nir.svg']:
            with self.request(path) as response:
                self.assertEqual(response.status,200)
                self.assertGreater(len(response.read()),20)

    def test_pwa_configuration_is_no_longer_exposed(self):
        for path in ['/manifest.webmanifest','/pwa.mjs']:
            with self.assertRaises(HTTPError) as error:self.request(path)
            self.assertEqual(error.exception.code,404)
        with self.request('/') as response:html=response.read().decode()
        self.assertNotIn('rel="manifest"',html)
        self.assertNotIn('apple-mobile-web-app-capable',html)
        with self.request('/sw.js') as response:worker=response.read().decode()
        self.assertIn('self.registration.unregister()',worker)
        self.assertNotIn("addEventListener('fetch'",worker)

    def test_unavailable_compound_is_rejected_before_dispatch(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/pit',{'compound':3},origin=self.base)
        self.assertEqual(error.exception.code,400)

if __name__=='__main__':unittest.main()
