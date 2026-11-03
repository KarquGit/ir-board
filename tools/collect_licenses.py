"""Collect runtime dependency notices before creating a Windows installer."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys


def main():
    target=Path('build/licenses')
    target.mkdir(parents=True,exist_ok=True)
    for name in ['pyirsdk','qrcode','PyYAML','PyInstaller']:
        dist=distribution(name)
        folder=target/name
        folder.mkdir(exist_ok=True)
        found=[]
        for file in dist.files or []:
            lower=file.name.lower()
            if any(part in lower for part in ('license','licence','copying','copyright')):
                source=Path(dist.locate_file(file))
                if source.is_file():
                    destination=folder/(str(len(found))+'-'+file.name)
                    shutil.copyfile(source,destination)
                    found.append(str(file))
        if not found:
            raise RuntimeError(f'No license files found for {name}; inspect distribution before packaging')
        (folder/'PACKAGE.txt').write_text(f'{dist.metadata["Name"]} {dist.version}\nSource: {dist.metadata.get("Home-page", "see package metadata")}\n'+ '\n'.join(found),encoding='utf-8')
    candidates=[Path(sys.base_prefix)/name for name in ['LICENSE.txt','LICENSE','license.txt']]
    python_license=next((path for path in candidates if path.is_file()),None)
    if python_license is None:
        raise RuntimeError('Python license not found; include it before distributing the runtime')
    shutil.copyfile(python_license,target/'PYTHON-LICENSE.txt')


if __name__=='__main__':main()
