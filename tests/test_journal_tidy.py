"""IT-4K: shared helpers keep the bytes and limits the copied code had."""
import hashlib
import json

from test_journal_finance import devices  # noqa: F401  (fixture)
from test_journal_nearby import setup
from lightning.sync.journal.codec import stable_digest, stable_json
from lightning.sync.journal.pairing import MAX_CODE_REQUESTS, MAX_REQUESTS


def test_stable_json_keeps_the_bytes_of_each_copied_variant():
    value = {"b": [1, "é", None], "a": {"z": 2.5, "y": "سجل"}, "rows": list(range(300))}
    assert stable_json(value) == json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                            allow_nan=False).encode("utf-8")
    legacy = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    assert stable_digest(value, ensure_ascii=True, default=str, allow_nan=True) == hashlib.sha256(legacy.encode()).hexdigest()


def _with_attempts(hs, attempts):
    state = hs._value("pairing")
    state["attempts"] = attempts
    hs._save("pairing", state)


def test_a_code_offer_stops_advertising_once_its_three_requests_are_spent(devices):
    hs = setup(devices)
    keys = hs.keys()
    hs.desk.begin(keys, "Pairing password")
    _with_attempts(hs, MAX_CODE_REQUESTS - 1)
    assert hs.advertise("0" * 64, 47513) is not None
    _with_attempts(hs, MAX_CODE_REQUESTS)
    assert hs.advertise("0" * 64, 47513) is None
    hs.begin("Pairing password")  # number matching takes twelve
    _with_attempts(hs, MAX_CODE_REQUESTS)
    assert hs.advertise("0" * 64, 47513) is not None
    _with_attempts(hs, MAX_REQUESTS)
    assert hs.advertise("0" * 64, 47513) is None


def test_one_helper_decides_a_journal_profile_and_its_role(tmp_path):
    from lightning.runtime.devices import Devices
    from lightning.runtime.paths import JOURNAL_MARKERS, is_journal_profile
    assert not is_journal_profile(tmp_path)
    for name in JOURNAL_MARKERS:
        folder = tmp_path / name.split(".")[0]
        folder.mkdir()
        (folder / name).write_text("{}", encoding="utf-8")
        assert is_journal_profile(folder)
        assert Devices(tmp_path / "devices").role_for(str(folder / "ledger.db")) == "home"
