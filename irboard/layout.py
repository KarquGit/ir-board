"""Persistent shared appearance, with optimistic concurrency between devices."""
import copy
import json
import os
import tempfile
import threading
from pathlib import Path

from .track import data_directory


def retire_widgets(layout):
    layout=copy.deepcopy(layout)
    if isinstance(layout,dict) and isinstance(layout.get('pages'),list):
        for page in layout['pages']:
            if isinstance(page,dict) and isinstance(page.get('widgets'),list):
                page['widgets']=[w for w in page['widgets'] if not isinstance(w,dict) or w.get('type') not in ('navigator','brakecoach')]
                for widget in page['widgets']:
                    if isinstance(widget,dict) and widget.get('type') == 'irlogic' and widget.get('title') == 'iR-logic (Experimental)':
                        widget['title'] = 'iR-logic'
    return layout


class LayoutStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_directory() / 'layout.json'
        self.lock = threading.Lock()
        self.value = dict(revision=0, layout=None)
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            value['layout']=retire_widgets(value['layout'])
            self.validate(value['layout'])
            if type(value['revision']) is int and value['revision'] > 0:
                self.value = value
        except (OSError, ValueError, KeyError, TypeError):
            pass

    @staticmethod
    def validate(layout):
        if not isinstance(layout, dict) or not isinstance(layout.get('pages'), list) or not 1 <= len(layout['pages']) <= 100:
            raise ValueError('Invalid layout pages')
        types = {'standings','relative','inputs','tachometer','laps','fuel','weather','systems','flag','learnedmap','flatmap','radar','trace','inspector','pit','irlogic'}
        for page in layout['pages']:
            if not isinstance(page, dict) or not isinstance(page.get('name'), str) or not isinstance(page.get('widgets'), list):
                raise ValueError('Invalid layout page')
            if len(page['widgets']) > 500 or any(not isinstance(w, dict) or not isinstance(w.get('type'), str) or w['type'] not in types for w in page['widgets']):
                raise ValueError('Invalid widgets')
        # JSON must be portable; reject NaN and oversized documents.
        if len(json.dumps(layout, allow_nan=False).encode()) > 1048576:
            raise ValueError('Layout is too large')

    def read(self):
        with self.lock:
            return json.loads(json.dumps(self.value))

    def update(self, layout, revision):
        layout=retire_widgets(layout)
        self.validate(layout)
        with self.lock:
            if type(revision) is not int or revision != self.value['revision']:
                return None
            value = dict(revision=revision + 1, layout=layout)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as file:
                    temporary = Path(file.name)
                    json.dump(value, file, allow_nan=False)
                os.replace(temporary, self.path)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
            self.value = json.loads(json.dumps(value))
            return self.value
