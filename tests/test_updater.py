import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from irboard.updater import select_update, version_key, verify_installer, download_update


def release(tag, version, prerelease=False):
    filename = f'iR-Board-Setup-{version}-windows-x64.exe'
    prefix = f'https://github.com/KarquGit/ir-board/releases/download/{tag}/'
    return dict(tag_name=tag, prerelease=prerelease, assets=[
        dict(name=name, browser_download_url=prefix+name)
        for name in [filename, filename+'.sha256']])


class UpdaterTests(unittest.TestCase):
    def test_release_channels_and_version_order(self):
        stable=release('v1.1.0','1.1.0')
        preview=release('v1.2.0-test.1','1.2.0',True)
        releases=[stable,preview]
        self.assertEqual(select_update(releases,'KarquGit/ir-board','v1.0.0')['tag'],'v1.1.0')
        self.assertEqual(select_update(releases,'KarquGit/ir-board','v1.0.0-test.1')['tag'],'v1.2.0-test.1')
        self.assertGreater(version_key('v1.0.0'),version_key('v1.0.0-test.2'))
        self.assertIsNone(select_update([stable],'KarquGit/ir-board','v2.0.0'))
        self.assertIsNone(version_key('../../installer.exe'))

    def test_foreign_assets_and_missing_checksums_never_selected(self):
        candidate=release('v1.1.0','1.1.0')
        candidate['assets'][0]['browser_download_url']='https://example.com/setup.exe'
        self.assertIsNone(select_update([candidate],'KarquGit/ir-board','v1.0.0'))
        candidate=release('v1.1.0','1.1.0');candidate['assets'].pop()
        self.assertIsNone(select_update([candidate],'KarquGit/ir-board','v1.0.0'))

    def test_hash_rechecked_and_invalid_manifest_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'setup.exe';path.write_bytes(b'example')
            digest=hashlib.sha256(b'example').hexdigest()
            verify_installer(path,digest)
            path.write_bytes(b'tampered')
            with self.assertRaises(RuntimeError):verify_installer(path,digest)
        with patch('irboard.updater.fetch',return_value=b'bad checksum'):
            with self.assertRaises(RuntimeError):
                download_update(dict(checksum_url='https://github.com/test',filename='setup.exe'))
