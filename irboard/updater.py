"""HTTPS GitHub release checks and checksum-verified, user-approved updates."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .version import VERSION

MAX_INSTALLER = 512 * 1024 * 1024


def version_key(tag):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-test\.(\d+))?', tag or '')
    if not match:
        return None
    major, minor, patch, preview = match.groups()
    return (int(major), int(minor), int(patch), int(preview is None), int(preview or 0))


def release_source():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    file = root / 'release.json'
    info = json.loads(file.read_text(encoding='utf-8')) if file.is_file() else {}
    repository = info.get('repository', 'KarquGit/ir-board')
    tag = info.get('tag', f'v{VERSION}')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not version_key(tag):
        raise RuntimeError('Invalid update source in this installation.')
    return repository, tag


def fetch(url, limit):
    request = Request(url, headers={'User-Agent': f'iR-Board/{VERSION}', 'Accept': 'application/vnd.github+json' if urlsplit(url).hostname == 'api.github.com' else 'application/octet-stream'})
    with urlopen(request, timeout=30) as response:
        if urlsplit(response.url).scheme != 'https':
            raise RuntimeError('Update download requires HTTPS.')
        body = response.read(limit + 1)
        if len(body) > limit:
            raise RuntimeError('Update response exceeded its size limit.')
        return body


def select_update(releases, repository, current_tag):
    current = version_key(current_tag)
    candidates = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag = release.get('tag_name')
        key = version_key(tag)
        if release.get('draft') or key is None or key <= current:
            continue
        if current[3] and (release.get('prerelease') or not key[3]):
            continue
        version = '.'.join(str(v) for v in key[:3])
        filename = f'iR-Board-Setup-{version}-windows-x64.exe'
        assets = {a.get('name'): a for a in release.get('assets', []) if isinstance(a, dict)}
        if filename not in assets or filename + '.sha256' not in assets:
            continue
        prefix = f'https://github.com/{repository}/releases/download/{quote(tag, safe="")}/'
        expected = {filename: prefix + filename, filename + '.sha256': prefix + filename + '.sha256'}
        if any(assets[name].get('browser_download_url') != url for name, url in expected.items()):
            continue
        candidates.append(dict(tag=tag, filename=filename, url=expected[filename], checksum_url=expected[filename+'.sha256'], key=key))
    return max(candidates, key=lambda item: item['key']) if candidates else None


def check_update():
    repository, tag = release_source()
    releases = json.loads(fetch(f'https://api.github.com/repos/{repository}/releases?per_page=30', 2*1024*1024))
    if not isinstance(releases, list):
        raise RuntimeError('Release information is unavailable.')
    return select_update(releases, repository, tag)


def verify_installer(path, expected):
    with open(path, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError('Update checksum does not match. The installer will not run.')


def download_update(update):
    text = fetch(update['checksum_url'], 4096).decode('ascii').strip()
    parts = text.split()
    if len(parts) != 2 or not re.fullmatch('[0-9a-fA-F]{64}', parts[0]) or parts[1] != update['filename']:
        raise RuntimeError('Invalid installer checksum file.')
    directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'iR-Board/updates' / update['tag']
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / update['filename']
    expected = parts[0].lower()
    if target.is_file():
        try:
            verify_installer(target, expected)
            return target, expected
        except RuntimeError:
            target.unlink()
    temporary = target.with_suffix('.download')
    try:
        # Read in bounded chunks rather than keeping the full setup in RAM.
        with urlopen(Request(update['url'], headers={'User-Agent':f'iR-Board/{VERSION}'}), timeout=30) as response, temporary.open('wb') as output:
            if urlsplit(response.url).scheme != 'https':
                raise RuntimeError('Update download requires HTTPS.')
            total = 0
            while chunk := response.read(1024*1024):
                total += len(chunk)
                if total > MAX_INSTALLER:
                    raise RuntimeError('Installer exceeds its size limit.')
                output.write(chunk)
        verify_installer(temporary, expected)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, expected


def launch_installer(path, expected):
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Install updates from the installed Windows application.')
    verify_installer(path, expected)
    # Standard interactive setup: never silently stop an active driving session.
    subprocess.Popen([str(path), '/NORESTART'])
