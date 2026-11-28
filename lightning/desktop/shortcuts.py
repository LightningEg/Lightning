"""Rebind the user's existing Windows desktop links after an install folder swap."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


def refresh_desktop_shortcuts(exe: Path, previous: Path) -> None:
    # Keep path data out of the command. Re-save matches even when Windows
    # reports the canonical path so the shell records the new file identity.
    script = """
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$current = $env:LIGHTNING_SHORTCUT_EXE
$previous = $env:LIGHTNING_SHORTCUT_PREVIOUS
Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' -File | ForEach-Object {
    $link = $shell.CreateShortcut($_.FullName)
    if ($link.TargetPath -in @($current, (Join-Path $previous 'Lightning.exe'))) {
        $link.TargetPath = $current
        if ($link.WorkingDirectory -eq $previous) {
            $link.WorkingDirectory = Split-Path -Parent $current
        }
        $link.Save()
    }
}
"""
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                   env=dict(os.environ, LIGHTNING_SHORTCUT_EXE=str(exe), LIGHTNING_SHORTCUT_PREVIOUS=str(previous)),
                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=20, check=True)
