"""Task 04b: the committed encrypted dummy profile gives the same report on every platform.

Windows CI runs this file too, and the Android probe runs the same `lightning.runtime.roundtrip` against the
same fixture and compares with the same `expected.json`, so equal lines mean equal figures, inventory and
key recovery on Linux, Windows and the phone."""
import hashlib
from pathlib import Path

from lightning.runtime.roundtrip import expected, fingerprint, run

FIXTURE = Path(__file__).parent / "fixtures" / "roundtrip"


def test_round_trip_report_matches_expected_and_fixture_is_unchanged():
    before = hashlib.sha256((FIXTURE / "profile.db").read_bytes()).hexdigest()
    lines, seconds = run(FIXTURE)
    assert lines == expected(FIXTURE)
    assert hashlib.sha256((FIXTURE / "profile.db").read_bytes()).hexdigest() == before
    assert set(seconds) == {"unlock (password)", "open", "write", "unlock (recovery key)", "reopen"}


def test_report_proves_the_write_and_the_refusals():
    lines = expected(FIXTURE)
    for line in ("plain SQLite refused: True", "wrong key refused: True", "recovery key opens the data key: True",
                 "new password opens: True", "old password refused: True", "integrity: ok",
                 "cipher integrity problems: 0", "after June money out: 24413.10"):
        assert line in lines
    assert fingerprint(lines) == __import__("json").loads((FIXTURE / "expected.json").read_text())["fingerprint"]


def test_wrong_recovery_key_is_refused():
    import pytest

    with pytest.raises(ValueError):
        run(FIXTURE, recovery_key="AAAAA-AAAAA-AAAAA-AAAAA")


def test_the_committed_fixture_is_the_generated_demo_household(tmp_path):
    """1E6: the committed encrypted profile is the generated demo household, not anyone's real data."""
    from lightning.runtime import roundtrip

    roundtrip.make(tmp_path)
    assert expected(tmp_path) == expected(FIXTURE)
    assert run(FIXTURE)[0] == run(tmp_path)[0]
