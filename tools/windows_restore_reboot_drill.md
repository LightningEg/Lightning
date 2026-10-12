# Ordinary Windows restore reboot drill

Use an ordinary Windows PC and this branch's source. The script creates only
encrypted dummy profiles in a new folder under your local app data. It stops a
separate process at each durable phase, P0–P5. One normal Windows restart then
lets the script check all six profiles against their retained recovery copies.
This checks reboot recovery; it does not simulate an abrupt power cut.

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/windows/)
   if `py -3.12 --version` does not work. Download and extract the
   [source ZIP](https://github.com/elfekimuhammed/Lightning/archive/refs/heads/main.zip).
   Open PowerShell in its `Lightning-main` folder.
2. Run these commands in PowerShell:

   ```powershell
   py -3.12 -m venv .venv
   & .\.venv\Scripts\python.exe -m pip install -e '.[encrypted]'
   $drill = Join-Path $env:LOCALAPPDATA ('LightningRestoreDrill-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
   Set-Content -Path (Join-Path $env:LOCALAPPDATA 'LightningRestoreDrillPath.txt') -Value $drill
   & .\.venv\Scripts\python.exe tools\windows_restore_reboot_drill.py prepare $drill
   ```

   The last command should print `P0` through `P5` as interrupted. If it fails,
   keep the drill folder and share the error instead of rebooting for this run.
3. Restart Windows normally from Start → Power → Restart.
4. Open PowerShell in the same extracted source folder and run:

   ```powershell
   $drill = Get-Content (Join-Path $env:LOCALAPPDATA 'LightningRestoreDrillPath.txt')
   & .\.venv\Scripts\python.exe tools\windows_restore_reboot_drill.py verify $drill
   ```

   A passing run prints `P0` through `P5` as recovered and verified. Share only
   the `drill.json` file in the printed drill folder. It contains the device,
   filesystem, boot change and per-phase result, with no profile password or
   recovery key. Keep the folder until the result has been reviewed.
