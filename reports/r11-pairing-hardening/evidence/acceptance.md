# Pairing acceptance kit

This kit creates **new dummy profiles only**. It refuses a nonempty root and does
not change a firewall, network interface, phone setting or production profile.

From the repository root, with its locked Python environment installed:

```sh
python tools/pairing_acceptance.py --dummy --root /path/to/new-empty-dummy-folder
```

Use a new folder on every run. Keep `ROOT/report.json`; do not share the dummy
profile databases, identity files or enrollment state. The report excludes
passwords, device/session identifiers and private keys. `automated-process-kill`
cases kill the worker after durable request, challenge, reveal, proof and status
boundaries, then resume through a different process. `automated-loopback` cases
use actual local UDP and pinned TLS, including certificate substitution and
changing discovery hints. These are not physical Wi-Fi evidence.

Run native credential checks on Windows:

```powershell
python -m lightning.runtime.pairing_probe --require-native
```

The normal review workflow also runs that DPAPI probe on a Windows runner. A
Linux report is labelled `development-provider` and never claims native storage
protection. Android Keystore requires the debug review APK installed on a real
phone or emulator. Launch its internal dummy probe through the debug-only entry:

```sh
adb shell am start -S -n org.lightning.app.test/org.lightning.app.MainActivity --ez pairing_probe true
adb logcat -d -s LightningPairingProbe
```

The probe opens no finance profile; retain its sanitized JSON. Production builds
do not expose that debug entry. A build alone is not an Android Keystore run.

## Physical Windows + Android matrix — unrun in the cloud workspace

Install the Windows/Android review builds. Create a disposable dummy profile,
choose **Edit from your devices**, and use **Join your existing home** on the PC.
Keep both screens available to compare/select the six-digit number. Never use a
real financial profile for fault drills. Record app commit, OS versions, network
type, case, observed result and whether a retry or explicit new pairing was
needed; do not record passwords or device/session identifiers.

| Case | Action | Required safe result |
| --- | --- | --- |
| Same Wi-Fi | Pair, close/reopen both apps, reconnect | Automatic discovery; number selection and PC password; exactly one membership admission |
| Phone hotspot | Repeat using the phone hotspot | Discover or report unavailable; no address typing and no relaxed certificate checks |
| Guest isolation | Use a guest network with client isolation | Unavailable is expected; saved edits and pairing state remain intact |
| Firewall | Manually deny, then allow the Windows review app on a private network | No mutation while blocked; saved attempt resumes or expires explicitly |
| Address switch | Change Wi-Fi or reconnect to obtain another IP | Discover the same pinned identity; refuse another certificate |
| Screen off / Doze | Sleep the phone, then reopen | No promised permanent listener; saved state resumes when reachable |
| App death / reboot | Force-stop or reboot at request/reveal/proof/download | Resume the same request and first challenge, or require explicit fresh pairing after expiry |
| Pending lease | Start an abandoned claim, wait for its lease, then pair another device | Old reveal/proof/approval rejected; new claimant inherits no old confirmation |
| Interrupted download | Disconnect or stop an app during first enrollment | Resume verified chunks; preserve financial fingerprint; no second writable home |
| Revocation | Revoke before retrying a cached approval/download | No current membership or encrypted enrollment material served to the revoked identity |
| Credential loss | Clear only the disposable app's OS key binding | Fail closed with reconnect/repair guidance; never silently create a replacement identity |

Do not automatically set firewall rules, disable security software, change Wi-Fi
or force-stop arbitrary apps. Keep every physical row `unrun` until exercised on
those devices. External professional cryptographic review is a separate evidence
category; the independent source/design review and automated matrix do not claim
that certification.
