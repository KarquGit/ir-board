import tempfile
import threading
import unittest
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from irboard.layout import LayoutStore
from irboard.server import create_server
from irboard.telemetry import Telemetry


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.json'
        self.store = LayoutStore(self.path)
        self.layout = dict(pages=[dict(name='Race', widgets=[dict(type='tachometer', colors={'rpm':'#123456'}, hidden=['oil'])])], theme='original')

    def test_persistence_and_conflict_preserve_winning_change(self):
        saved = self.store.update(self.layout, 0)
        self.assertEqual(saved['revision'], 1)
        self.assertIsNone(self.store.update(self.layout, 0))
        self.assertEqual(LayoutStore(self.path).read(), saved)
        copy = self.store.read()
        copy['layout']['pages'].clear()
        self.assertTrue(self.store.read()['layout']['pages'])

    def test_two_concurrent_writers_cannot_overwrite_each_other(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.update(self.layout, 0), range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(self.store.read()['revision'], 1)

    def test_retired_widgets_do_not_discard_saved_pages_or_other_appearance(self):
        original=json.loads(json.dumps(self.layout))
        original['pages'][0]['widgets'] += [dict(type='navigator'),dict(type='brakecoach'),dict(type='irlogic',coachReference='personal')]
        self.path.write_text(json.dumps(dict(revision=7,layout=original)))
        restored=LayoutStore(self.path).read()
        self.assertEqual(restored['revision'],7)
        self.assertEqual([w['type'] for w in restored['layout']['pages'][0]['widgets']],['tachometer','irlogic'])
        self.assertEqual(restored['layout']['pages'][0]['widgets'][0],self.layout['pages'][0]['widgets'][0])
        self.assertEqual(restored['layout']['pages'][0]['widgets'][1]['coachReference'],'personal')
        saved=self.store.update(original,0)
        self.assertEqual(saved['layout'],restored['layout'])
        self.assertEqual(len(original['pages'][0]['widgets']),4)

    def test_logic_default_title_migration_preserves_custom_titles_and_settings(self):
        original = dict(pages=[dict(name='Keep',widgets=[
            dict(type='irlogic',title='iR-logic (Experimental)',coachReference='personal'),
            dict(type='irlogic',title='My sectors'),
            dict(type='learnedmap',title='Learned track map (Experimental)')
        ])],alerts={'flags':{'mode':'off'}},active=0)
        saved = self.store.update(original,0)
        self.assertEqual([w['title'] for w in saved['layout']['pages'][0]['widgets']],
                         ['iR-logic','My sectors','Learned track map (Experimental)'])
        self.assertEqual(saved['layout']['alerts'],original['alerts'])
        self.assertEqual(original['pages'][0]['widgets'][0]['title'],'iR-logic (Experimental)')
        self.assertEqual(LayoutStore(self.path).read(),saved)
        self.path.write_text(json.dumps(dict(revision=3,layout=original)))
        self.assertEqual(LayoutStore(self.path).read()['layout'],saved['layout'])

    def test_invalid_layout_does_not_change_revision(self):
        for layout in [None, {}, {'pages':[]}, {'pages':[{'name':'x','widgets':[None]}]}, {'pages':[{'name':'x','widgets':[{'type':'unknown'}]}]}]:
            with self.assertRaises(ValueError): self.store.update(layout, 0)
        self.assertEqual(self.store.read()['revision'], 0)

    def test_http_roundtrip_conflict_and_origin(self):
        server = create_server('127.0.0.1', 0, Telemetry(demo=True), layout_store=self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            def post(revision, origin=None):
                headers={'Content-Type':'application/json'}
                if origin: headers['Origin']=origin
                return urlopen(Request(base+'/api/layout', data=json.dumps(dict(layout=self.layout, revision=revision)).encode(), headers=headers))
            with post(0) as response: self.assertEqual(json.load(response)['revision'], 1)
            with urlopen(base+'/api/layout') as response: self.assertEqual(json.load(response)['layout'], self.layout)
            with self.assertRaises(HTTPError) as error: post(0)
            self.assertEqual(error.exception.code, 409)
            with self.assertRaises(HTTPError) as error: post(1, 'https://example.com')
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class LayoutRestartTests(unittest.TestCase):
    def test_appearance_survives_server_process_restart(self):
        import os
        import subprocess
        import sys
        code = """from irboard.server import create_server
from irboard.telemetry import Telemetry
server=create_server('127.0.0.1',0,Telemetry(demo=True))
print(server.server_port,flush=True)
server.serve_forever()
"""
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, IRBOARD_DATA_DIR=directory)
            def start():
                process = subprocess.Popen([sys.executable, '-u', '-c', code], env=environment,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                port = int(process.stdout.readline())
                return process, f'http://127.0.0.1:{port}'
            def stop(process):
                process.terminate()
                process.communicate(timeout=5)
            layout = {'pages':[{'name':'Persisted race','widgets':[{'type':'tachometer','title':'My RPM',
                       'hidden':['water','oil'], 'colors':{'rpm':'#123456'},
                       'layouts':{'portrait':{'x':0,'y':0,'w':1,'h':.4}}}]}],
                      'theme':'original','driverCountries':{'123':'PL'},
                      'alerts':{'flags':{'mode':'center','duration':6,'opacity':.65,'enabled':{'green':False}},
                                'spotter':{'mode':'bars','opacity':.4}}}
            process, base = start()
            try:
                request = Request(base+'/api/layout', data=json.dumps({'revision':0,'layout':layout}).encode(),
                                  headers={'Content-Type':'application/json'})
                with urlopen(request, timeout=5) as response:
                    saved = json.load(response)
                    self.assertEqual(saved['revision'], 1)
            finally:
                stop(process)
            process, base = start()
            try:
                with urlopen(base+'/api/layout', timeout=5) as response:
                    restored = json.load(response)
                self.assertEqual(restored, saved)
                self.assertEqual(restored['layout'], layout)
            finally:
                stop(process)

    def test_windows_settings_directory_is_outside_installation(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from irboard.track import data_directory
        import os
        with patch('irboard.track.os', SimpleNamespace(name='nt', environ=dict(os.environ, LOCALAPPDATA='/user/AppData/Local'))):
            self.assertEqual(data_directory(), Path('/user/AppData/Local/iR-Board'))
