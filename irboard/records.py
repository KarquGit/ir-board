"""Small local store for observed clean personal-best laps."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


class LapRecords:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.cache={}

    def observe(self,key,lap_time=None):
        identifier=hashlib.sha256(json.dumps(key).encode()).hexdigest()
        path=self.directory/(identifier+'.json')
        if identifier not in self.cache:
            try:
                value=json.loads(path.read_text())
                best=value.get('time') if value.get('key')==list(key) else None
                self.cache[identifier]=best if type(best) in (int,float) and math.isfinite(best) and best>0 else None
            except (OSError,ValueError,TypeError,AttributeError):
                self.cache[identifier]=None
        best=self.cache[identifier]
        if type(lap_time) in (int,float) and math.isfinite(lap_time) and lap_time>0 and (best is None or lap_time<best):
            self.cache[identifier]=lap_time
            temporary=None
            try:
                self.directory.mkdir(parents=True,exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.directory,delete=False) as f:
                    temporary=Path(f.name)
                    json.dump(dict(key=list(key),time=lap_time),f,allow_nan=False)
                os.replace(temporary,path)
            except OSError:
                pass
            finally:
                if temporary is not None:
                    try:temporary.unlink(missing_ok=True)
                    except OSError:pass
        return self.cache[identifier]


class FuelRecords:
    """Persist clean consumption samples only, never live session state."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, key):
        return self.directory/(hashlib.sha256(json.dumps(key).encode()).hexdigest()+'.json')

    def load(self, key):
        try:
            path = self.path(key)
            if path.stat().st_size > 4096: return []
            value = json.loads(path.read_text(encoding='utf-8'))
            rows = value.get('samples')
            if value.get('key') != list(key) or value.get('format') != 1: return []
            if not isinstance(rows, list) or not 1 <= len(rows) <= 20: return []
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 < v <= 100 for v in rows): return []
            return rows
        except (OSError, ValueError, TypeError, AttributeError):
            return []

    def save(self, key, samples):
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(format=1, key=list(key), samples=list(samples)[-20:]), stream, allow_nan=False)
            os.replace(temporary, self.path(key))
        except OSError:
            pass
        finally:
            if temporary: temporary.unlink(missing_ok=True)
