"""Generate transparent Windows file metadata from the versioned source."""
from pathlib import Path
import sys
import json
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from irboard.version import VERSION, DISPLAY_VERSION

parts=tuple(int(p) for p in VERSION.split('.'))
if len(parts)!=3:raise ValueError('Use major.minor.patch')
version=parts+(0,)
text=f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version!r},prodvers={version!r},mask=0x3f,flags=0,OS=0x40004,fileType=0x1,subtype=0,date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0',[
    StringStruct('CompanyName','iR-Board contributors'),
    StringStruct('FileDescription','iR-Board local iRacing dashboard'),
    StringStruct('FileVersion','{DISPLAY_VERSION}'),
    StringStruct('InternalName','iR-Board'),
    StringStruct('LegalCopyright','Copyright 2026 iR-Board contributors'),
    StringStruct('OriginalFilename','iR-Board.exe'),
    StringStruct('ProductName','iR-Board'),
    StringStruct('ProductVersion','{DISPLAY_VERSION}')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
'''
Path('build').mkdir(exist_ok=True)
Path('build/windows-version.txt').write_text(text,encoding='utf-8')
repository = os.environ.get('GITHUB_REPOSITORY', 'KarquGit/ir-board')
tag = os.environ.get('GITHUB_REF_NAME', f'v{VERSION}')
if not tag.startswith(f'v{VERSION}'):
    tag = f'v{VERSION}'
Path('build/release.json').write_text(json.dumps(dict(repository=repository,tag=tag)),encoding='utf-8')
