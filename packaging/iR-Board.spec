# Build from repository root with: pyinstaller --noconfirm packaging/iR-Board.spec
from pathlib import Path

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / 'launcher.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'build' / 'licenses'), 'licenses'),
           (str(root / 'build' / 'release.json'), '.'),
           (str(root / 'irboard' / 'static'), 'irboard/static'),
           (str(root / 'LICENSE'), '.'),
           (str(root / 'THIRD_PARTY_NOTICES.md'), '.')],
    hiddenimports=['irsdk', 'yaml', 'qrcode.image.svg'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='iR-Board',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon=str(root/'irboard/static/icon.ico'),
          version=str(root/'build/windows-version.txt'), manifest=str(root/'packaging/app.manifest'))
coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='iR-Board')
