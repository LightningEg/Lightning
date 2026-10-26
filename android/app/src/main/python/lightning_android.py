"""The phone app's Python side: the shared profile app on 127.0.0.1 for the WebView, and the PC listener.

Profiles live in app-private storage (`files/Lightning`), sync records beside them (`files/appdata`, where the
optional fingerprint slots also sit, in `biometric/`, outside every profile folder); all are
excluded from Google backup and device transfer (res/xml/data_extraction_rules.xml). The server keeps running
while the process lives, so reopening the app does not ask for a new launch link."""
from pathlib import Path

_host = None
_devices = None
_launched = False


def configure_device_credentials():
    """Install the native adapter before any pairing identity is opened."""
    try:
        from java import jclass
    except ImportError:
        return False  # Desktop probe only; Android platform detection still fails closed.
    from lightning.security.device_credentials import configure_android_credentials
    configure_android_credentials(jclass("org.lightning.app.DeviceCredentialBridge"))
    return True


def start(files_dir):
    """The URL the WebView opens: the single-use launch link the first time, the app itself afterwards."""
    global _host, _devices, _launched
    if _host is None:
        configure_device_credentials()
        from lightning.runtime.app import profile_app
        from lightning.runtime.devices import Devices
        from lightning.runtime.http import Host

        from lightning.security.biometric import FingerprintUnlock

        files = Path(files_dir)
        _devices = Devices(files / "appdata")
        fingerprint = FingerprintUnlock(files / "appdata" / "biometric", AndroidBiometric.create())
        _host = Host(lambda credentials: profile_app(credentials, files / "Lightning", devices=_devices, phone=True,
                                                     sms=AndroidSms.create(), biometric=fingerprint)).start()
    if not _launched:
        _launched = True
        return _host.launch_url
    return _host.origin + "/"


class AndroidSms:
    """`lightning.sms_imports.SmsSource` over the Java `SmsBridge`."""

    def __init__(self, bridge):
        self.bridge = bridge

    @classmethod
    def create(cls):
        """None off the phone (the probe's tests run this module on a PC)."""
        try:
            from java import jclass
        except ImportError:
            return None
        return cls(jclass("org.lightning.app.SmsBridge"))

    def permission(self):
        return str(self.bridge.permission())

    def request(self):
        self.bridge.request()

    def since(self, after_ms):
        import json
        return [(str(sender), str(body), int(received)) for sender, body, received in
                json.loads(str(self.bridge.since(int(after_ms))))]

    def take_shared(self):
        import json
        return [str(text) for text in json.loads(str(self.bridge.takeShared()))]


class AndroidBiometric:
    """`lightning.security.biometric.BiometricBridge` over the Java `BiometricBridge`: strings in and out
    (base64 and JSON), so nothing depends on how Chaquopy converts byte arrays."""

    def __init__(self, bridge):
        self.bridge = bridge

    @classmethod
    def create(cls):
        """None off the phone, so a PC (and the probe's tests) never offer fingerprint unlock."""
        try:
            from java import jclass
        except ImportError:
            return None
        return cls(jclass("org.lightning.app.BiometricBridge"))

    def available(self):
        return bool(self.bridge.available())

    @staticmethod
    def _result(reply):
        import base64
        import json
        from lightning.security.biometric import BridgeResult, Outcome

        document = json.loads(str(reply))
        try:
            outcome = Outcome(document.get("status"))
        except ValueError:
            outcome = Outcome.UNAVAILABLE
        if outcome is not Outcome.OK:
            return BridgeResult(outcome)
        return BridgeResult(outcome, base64.b64decode(document.get("iv", "")), base64.b64decode(document.get("data", "")))

    def encrypt(self, profile_id, plaintext, aad):
        import base64
        return self._result(self.bridge.encrypt(profile_id, base64.b64encode(plaintext).decode("ascii"),
                                                base64.b64encode(aad).decode("ascii")))

    def decrypt(self, profile_id, iv, ciphertext, aad):
        import base64
        return self._result(self.bridge.decrypt(profile_id, base64.b64encode(iv).decode("ascii"),
                                                base64.b64encode(ciphertext).decode("ascii"),
                                                base64.b64encode(aad).decode("ascii")))

    def delete_key(self, profile_id):
        self.bridge.deleteKey(profile_id)


def background_note():
    """What the notification says while the phone must keep listening (pairing, or the ledger is away), or ""
    when it may sleep."""
    from lightning.runtime.devices import home_state_line

    if _devices is None or _devices.server is None:
        return ""
    desk = _devices.desk
    if desk is not None and desk.pending is not None and not desk.pending.paired_name:
        return "Waiting for your PC to pair"
    for node in _devices.home_nodes():
        try:
            line = home_state_line(node)
        except Exception:  # noqa: BLE001 - an unreadable record still needs the listener
            line = "Checking where your ledger is"
        if line:
            return line
    return ""


def sync_journal(files_dir):
    """Android background entry point. Only an unlocked, registered phone session can synchronize."""
    import asyncio
    from lightning.runtime.journal_android import sync_once

    try:
        return asyncio.run(sync_once(files_dir))
    except Exception:  # noqa: BLE001 - leave the journal pending for a later scheduler opportunity
        return "offline"
