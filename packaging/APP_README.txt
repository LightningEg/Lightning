Lightning for Windows — v@VERSION@

This unsigned release includes private profiles protected by a password and a
recovery key, plus the Lightning finance app. You may use sample or real data;
keep an independent backup. This release has not been code-signed.

Windows requirements
--------------------
Windows x64 and the Microsoft Edge WebView2 Runtime are required. Install the
runtime from Microsoft's official page if it is not already available:
https://developer.microsoft.com/microsoft-edge/webview2/consumer/

No Python installation is needed.

Getting started
---------------
1. Extract the downloaded ZIP once into a new folder you can write to.
2. Double-click Lightning.exe in that folder and create a profile.
3. Choose a passphrase of at least 12 characters. Save the displayed recovery
   key offline in a safe place. The recovery key can reset a forgotten password.
4. Create or open financial data in the profile.

Profile databases and their backups are stored separately from this application,
under Documents/Lightning. Do not open the same database on two computers at the
same time, including through a synced Documents folder.

Updating and backups
--------------------
Settings > Lightning version has a Check for updates button (Lightning looks
only when you press it). If a newer version is found it downloads it, checks it,
and restarts into it by itself; if the new version does not start, the old one
comes back and is also kept beside it in a folder ending in .previous. It
refuses while a phone's ledger is lent to this PC, and in a folder it cannot
change (such as Program Files). Profiles in Documents/Lightning are never touched.

You can also update by hand: close Lightning, extract the new ZIP to a fresh
folder, and open the new Lightning.exe. Keep the old app folder until the new build opens. You
can then remove the old app folder; profile data in Documents/Lightning stays
separate. Keep a separate copy of the profile backup folder before making
changes to valuable data.

Current limits
--------------
This preview does not include legacy database import or a backup-restore screen.
Import CSV accepts bank CSV files up to 5 MiB; other forms are limited to 512 KiB.

Linux developers can continue using the source browser app with:
  python -m lightning --profiles

The Linux source app retains its browser workflow and profile storage behavior.
