import concurrent.futures
import http.client
import json
import socket
import tempfile
from unittest.mock import patch
from contextlib import nullcontext
import threading
import unittest
from urllib.parse import urlsplit
from irboard.security import Pairing,valid_host,PAIR_TTL,SESSION_TTL,local_client
from irboard.server import create_server
from irboard.telemetry import Telemetry

class PairingTests(unittest.TestCase):
    def test_manual_code_is_six_digits_single_use_expiring_and_not_fixed(self):
        now=[0];pair=Pairing(lambda:now[0])
        code=pair.manual_code()['code']
        self.assertRegex(code,r'^[0-9]{6}$')
        self.assertEqual(pair.manual_code()['code'],code)
        session=pair.exchange(code,'tablet')
        self.assertTrue(session)
        self.assertNotEqual(pair.manual_code()['code'],code)
        self.assertIsNone(pair.exchange(code,'tablet'))
        self.assertNotIn('; Secure',pair.cookie(session))
        code=pair.manual_code()['code'];now[0]=PAIR_TTL+1
        self.assertIsNone(pair.exchange(code,'new-tablet'))
        self.assertNotEqual(pair.manual_code()['code'],code)
        self.assertFalse(Pairing().authorized(pair.cookie(session)))

    def test_numeric_code_concurrency_leading_zero_and_global_guess_limit(self):
        now=[0];pair=Pairing(lambda:now[0]);pair.pin='001234';pair.pin_expires=300
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(lambda _:pair.exchange('001234','tablet'),range(8)))
        self.assertEqual(sum(value is not None for value in result),1)
        pair=Pairing(lambda:now[0]);code=pair.manual_code()['code']
        wrong='111111' if code!='111111' else '222222'
        for index in range(30): self.assertIsNone(pair.exchange(wrong,f'client-{index}'))
        self.assertIsNone(pair.exchange(code,'another-client'))
        now[0]=61
        self.assertTrue(pair.exchange(code,'another-client'))

    def test_malformed_attempts_are_limited_and_unicode_digits_rejected(self):
        pair=Pairing();code=pair.manual_code()['code']
        for _ in range(10): self.assertIsNone(pair.exchange(None,'tablet'))
        self.assertIsNone(pair.exchange(code,'tablet'))
        pair.pin='123456';pair.pin_expires=pair.clock()+300
        self.assertIsNone(pair.exchange('１２３４５６','other'))

    def test_only_the_server_computer_is_exempt(self):
        self.assertTrue(local_client('127.0.0.1','127.0.0.1'))
        self.assertTrue(local_client('192.168.1.10','192.168.1.10'))
        self.assertFalse(local_client('192.168.1.11','192.168.1.10'))
    def test_single_use_expiring_pair_code_and_session(self):
        now=[0];pair=Pairing(lambda:now[0]);code=pair.issue()
        session=pair.exchange(code,'tablet');self.assertTrue(session)
        self.assertIsNone(pair.exchange(code,'tablet'))
        cookie=Pairing.cookie(session);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertTrue(pair.authorized(cookie));now[0]=SESSION_TTL+1;self.assertFalse(pair.authorized(cookie))
        code=pair.issue();now[0]+=PAIR_TTL+1;self.assertIsNone(pair.exchange(code,'tablet'))
    def test_concurrent_redemption_is_single_use(self):
        pair=Pairing();code=pair.issue()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:result=list(pool.map(lambda _:pair.exchange(code,'tablet'),range(8)))
        self.assertEqual(sum(value is not None for value in result),1)
    def test_pairing_rate_limit(self):
        pair=Pairing()
        for _ in range(10):pair.exchange('incorrect-code-0123456789','tablet')
        self.assertIsNone(pair.exchange(pair.issue(),'tablet'))
    def test_host_header_cannot_introduce_rebinding_origin(self):
        for host in ['evil.example:8000','127.0.0.1:9999','user@127.0.0.1:8000','127.0.0.1:8000/path','localhost:bad']:
            self.assertFalse(valid_host(host,8000,{'localhost','127.0.0.1'}),host)
        self.assertTrue(valid_host('localhost:8000',8000,{'localhost'}))

class LANCommandSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        telemetry=Telemetry(demo=True);telemetry._data.update(connected=True,pit={'can_control':True})
        cls.directory=tempfile.TemporaryDirectory()
        cls.server=create_server('0.0.0.0',0,telemetry)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_port
        cls.lan=urlsplit(cls.server.connection_info['urls'][0]).hostname if cls.server.connection_info['urls'] else None
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.directory.cleanup()
    def request(self,path,body=None,host='127.0.0.1',cookie=None,origin=None,host_header=None,extra_headers=None):
        client=http.client.HTTPConnection(host,self.port,timeout=5)
        headers={}
        if body is not None:headers['Content-Type']='application/json'
        if cookie:headers['Cookie']=cookie
        if origin:headers['Origin']=origin
        if host_header:headers['Host']=host_header
        if extra_headers:headers.update(extra_headers)
        try:
            # Same-process LAN requests simulate a different physical computer here.
            with patch('irboard.server.local_client',return_value=False) if host == self.lan else nullcontext():
                client.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
                result=client.getresponse();return result.status,result.read(),dict(result.getheaders())
        finally:client.close()
    def test_unknown_host_is_rejected_before_api(self):
        status,_,_=self.request('/api/connection',host_header='evil.example:'+str(self.port));self.assertEqual(status,403)
    def test_cross_origin_cannot_issue_pairing_codes(self):
        status,_,_=self.request('/api/pairing',{},origin='http://evil.example');self.assertEqual(status,403)
    def test_remote_pit_control_requires_local_pairing_and_cookie(self):
        if not self.lan:self.skipTest('No non-loopback interface available for LAN integration test')
        status,body,_=self.request('/api/telemetry',host=self.lan)
        self.assertEqual(status,401);self.assertNotIn('car',json.loads(body))
        status,_,_=self.request('/api/pit',{},host=self.lan);self.assertEqual(status,401)
        status,_,_=self.request('/api/layout',{},host=self.lan);self.assertEqual(status,401)
        url=self.server.connection_info['urls'][0]
        status,_,_=self.request('/api/pairing',{'url':url},host=self.lan);self.assertEqual(status,403)
        status,body,_=self.request('/api/pairing',{'url':url});self.assertEqual(status,200)
        pair=json.loads(body);self.assertNotIn('session',pair)
        code=urlsplit(pair['join_url']).fragment.removeprefix('pair=')
        status,_,headers=self.request('/api/pair',{'code':code},host=self.lan);self.assertEqual(status,200)
        cookie=headers['Set-Cookie']
        status,_,_=self.request('/api/pit',{'fuel':5},host=self.lan,cookie=cookie);self.assertEqual(status,200)
        status,_,_=self.request('/api/pair',{'code':code},host=self.lan);self.assertEqual(status,401)
        status,_,_=self.request('/api/pit',{},host=self.lan,cookie=cookie,origin='http://evil.example');self.assertEqual(status,403)

    def test_remote_portal_and_assets_are_private_and_headers_cannot_bypass(self):
        if not self.lan:self.skipTest('No LAN interface available')
        for path in ['/api/telemetry','/api/layout','/api/connection','/api/health','/app.js','/default-layout.mjs','/certificate.cer']:
            with self.subTest(path=path):
                status,_,_=self.request(path,host=self.lan,
                    extra_headers={'Authorization':'Bearer old-token','X-Forwarded-For':'127.0.0.1'})
                self.assertEqual(status,401)
        status,_,headers=self.request('/',host=self.lan)
        self.assertEqual(status,303);self.assertEqual(headers['Location'],'/auth')
        for path in ['/auth','/auth.js','/auth.css']:
            self.assertEqual(self.request(path,host=self.lan)[0],200)

    def test_manual_pairing_enables_reading_without_exposing_the_operator_code(self):
        if not self.lan:self.skipTest('No LAN interface available')
        status,body,_=self.request('/api/connection')
        self.assertEqual(status,200);operator=json.loads(body)
        code=operator['manual_pairing']['code']
        status,_,headers=self.request('/api/pair',{'code':code},host=self.lan)
        self.assertEqual(status,200);cookie=headers['Set-Cookie']
        self.assertIn('HttpOnly',cookie)
        status,body,_=self.request('/api/telemetry',host=self.lan,cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['access']['can_control'])
        status,body,_=self.request('/api/connection',host=self.lan,cookie=cookie)
        self.assertEqual(status,200);self.assertNotIn('manual_pairing',json.loads(body))
        self.assertNotIn('certificate',json.loads(body))
        self.assertEqual(self.request('/api/pair',{'code':code},host=self.lan)[0],401)

    def test_idle_http_connection_does_not_block_new_clients(self):
        idle=socket.create_connection(('127.0.0.1',self.port),timeout=2)
        try:
            self.assertEqual(self.request('/api/health')[0],200)
        finally: idle.close()

if __name__=='__main__':unittest.main()
