import json
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import patch, MagicMock
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from irboard.network import connection_info, qr_svg
from irboard.server import create_server
from irboard.telemetry import Telemetry, DemoSource

class ConnectionTests(unittest.TestCase):
    def test_linux_loopback_hostname_uses_the_real_route_address(self):
        route=MagicMock();route.getsockname.return_value=('192.168.1.42',54321)
        with patch('irboard.network.socket.socket') as socket_factory, patch('irboard.network.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.1.1',0))]):
            socket_factory.return_value.__enter__.return_value=route
            info=connection_info('0.0.0.0',8000)
        self.assertEqual(info['urls'],['http://192.168.1.42:8000/'])
        route.send.assert_not_called();route.sendto.assert_not_called()

    def test_network_detection_failure_has_an_actionable_message(self):
        with patch('irboard.network.socket.socket',side_effect=OSError),patch('irboard.network.socket.getaddrinfo',side_effect=OSError):
            info=connection_info('0.0.0.0',8000)
        self.assertEqual(info['urls'],[])
        self.assertIn('--lan-host',info['message'])
    def test_explicit_lan_url(self):
        info=connection_info('0.0.0.0',8080,'192.168.1.25')
        self.assertEqual(info['urls'],['http://192.168.1.25:8080/'])
        self.assertTrue(info['lan_enabled'])
        self.assertNotIn('token',info['urls'][0])
    def test_loopback_is_not_advertised_as_lan(self):
        info=connection_info('127.0.0.1',8000)
        self.assertFalse(info['lan_enabled']);self.assertEqual(info['urls'],[])
    def test_bad_override_is_rejected(self):
        for name in ['https://host','host/path','host:8000','host?token=x']:
            with self.subTest(name=name),self.assertRaises(ValueError):connection_info('0.0.0.0',8000,name)
    def test_local_qr_is_svg(self):
        image=qr_svg('http://192.168.1.25:8000/')
        self.assertIn(b'<svg',image);self.assertIn(b'background:white',image)
        self.assertNotIn(b'<script',image)
    def test_removed_track_data_not_in_current_tree_or_telemetry(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'irboard/data/tracks.json').exists())
        self.assertFalse((root/'tools/build_track_maps.py').exists())
        self.assertNotIn('map',DemoSource().read())
    def test_qr_endpoint_public_but_only_advertised_urls(self):
        telemetry=Telemetry(demo=True)
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        server=create_server('127.0.0.1',0,telemetry,lan_host='192.168.1.25')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(base+'/api/connection') as response:info=json.load(response)
            self.assertRegex(info['manual_pairing']['code'],r'^[0-9]{6}$')
            self.assertNotIn('test-secret',json.dumps(info))
            from urllib.parse import quote
            with urlopen(base+'/qr.svg?url='+quote(info['urls'][0],safe='')) as response:
                self.assertIn(b'<svg',response.read())
            with self.assertRaises(HTTPError) as error:urlopen(base+'/qr.svg?url=https%3A%2F%2Fevil.example')
            self.assertEqual(error.exception.code,400)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
