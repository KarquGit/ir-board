"""Explicit, elevated setup of one narrowly scoped Windows Firewall rule."""
import base64
import os
from pathlib import Path
import subprocess
import sys


def encoded(script):
    return base64.b64encode(script.encode('utf-16le')).decode('ascii')


def rule_script(executable):
    program = str(Path(executable).resolve()).replace("'", "''")
    return f"""$ErrorActionPreference='Stop'
try {{
  $name='iR-Board-Tablet-Private-TCP-8000'
  Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule -Name $name -DisplayName 'iR-Board tablet access (Private LAN)' -Direction Inbound -Action Allow -Enabled True -Profile Private -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Program '{program}' | Out-Null
  exit 0
}} catch {{ exit 1 }}
"""


def allow_private_lan():
    if sys.platform != 'win32':
        raise RuntimeError('Automatic firewall setup is available on Windows only.')
    # Elevate only this short-lived helper; the dashboard continues as a normal user.
    inner = encoded(rule_script(sys.executable))
    outer = f"""$ErrorActionPreference='Stop'
try {{
  $process=Start-Process -FilePath "$PSHOME\\powershell.exe" -Verb RunAs -ArgumentList '-NoProfile -NonInteractive -EncodedCommand {inner}' -Wait -PassThru
  exit $process.ExitCode
}} catch {{ exit 1 }}
"""
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded(outer)],
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    if result.returncode:
        raise RuntimeError('Permission was cancelled or the firewall rule could not be created. Use Windows Defender Firewall settings or contact your administrator.')
