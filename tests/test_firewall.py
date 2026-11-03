import base64
import unittest
from pathlib import Path

from irboard.firewall import encoded, rule_script


class FirewallTests(unittest.TestCase):
    def test_rule_is_scoped_to_app_private_subnet_and_port(self):
        script = rule_script('/tmp/iR-Board.exe')
        for argument in ['-Profile Private', '-Protocol TCP', '-LocalPort 8000',
                         '-RemoteAddress LocalSubnet', f"-Program '{Path('/tmp/iR-Board.exe').resolve()}'",
                         '-Direction Inbound', '-Action Allow']:
            self.assertIn(argument, script)
        self.assertNotIn('Set-NetFirewallProfile', script)
        self.assertNotIn('Set-NetConnectionProfile', script)

    def test_paths_are_literal_and_encoded_command_roundtrips(self):
        script = rule_script("/tmp/Driver's $PC/iR-Board.exe")
        self.assertIn("Driver''s $PC", script)
        self.assertEqual(base64.b64decode(encoded(script)).decode('utf-16le'), script)
