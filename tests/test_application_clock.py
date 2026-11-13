"""IT-3BI4: business dates follow one clock; operational timestamps keep real time."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

import pytest

from lightning.core import dates
from lightning import sms_imports
from lightning.sms_imports import parse_sms


@pytest.mark.parametrize('pinned', ['2024-02-29', '2025-02-28', '2030-01-01'])
def test_application_clock_pins_only_the_date(monkeypatch, pinned):
    actual = datetime(2026, 12, 31, 23, 59, 58, 123456)
    monkeypatch.setattr(dates, 'wall_now', lambda: actual)
    monkeypatch.setenv('LIGHTNING_TODAY', pinned)
    expected = date.fromisoformat(pinned)
    assert dates.today() == expected
    assert dates.now() == datetime.combine(expected, actual.time())
    assert dates.now().tzinfo is None  # Existing local SMS timestamps remain naive.


def test_unpinned_date_and_timestamp_use_the_same_clock(monkeypatch):
    actual = datetime(2027, 1, 1, 0, 0, 1, 654321)
    monkeypatch.delenv('LIGHTNING_TODAY', raising=False)
    monkeypatch.setattr(dates, 'wall_now', lambda: actual)
    assert dates.now() == actual
    assert dates.today() == actual.date()


def test_wall_clock_ignores_a_simulated_profile_date(monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2000-01-01')
    before = datetime.now(timezone.utc)
    actual = dates.wall_now(timezone.utc)
    after = datetime.now(timezone.utc)
    assert before <= actual <= after
    assert dates.today() == date(2000, 1, 1)


def test_audit_timestamp_keeps_the_real_date_and_offset(monkeypatch):
    actual = datetime(2026, 9, 30, 12, 34, 56, tzinfo=timezone(timedelta(hours=3)))
    monkeypatch.setattr(dates, '_local_now', lambda: actual)
    monkeypatch.setenv('LIGHTNING_TODAY', '2000-01-01')
    assert dates.now_iso() == '2026-09-30T12:34:56+03:00'


def test_undated_sms_uses_the_application_date_but_keeps_explicit_receipt(monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2030-01-01')
    message = 'عميلنا العزيز لقد تم تحويل مبلغ EGP19,584.66 على حسابكم لدينا من جهة العمل'
    parsed = parse_sms(message)
    assert parsed is not None
    assert parsed.when.startswith('2030-01-01')
    received = datetime(2026, 10, 2, 9, 15)
    explicit = parse_sms(message, received=received)
    assert explicit is not None
    assert explicit.when.startswith('2026-10-02')


@pytest.mark.parametrize('replay', [None, datetime(2024, 2, 29, 9, 30)])
def test_sms_first_look_follows_real_receipts_or_an_explicit_replay_clock(c, monkeypatch, replay):
    class EmptyInbox:
        after = None

        def take_shared(self):
            return []

        def permission(self):
            return 'granted'

        def since(self, after):
            self.after = after
            return []

    actual = datetime(2026, 10, 3, 12, 30)
    monkeypatch.setattr(sms_imports, 'wall_now', lambda: actual)
    monkeypatch.setenv('LIGHTNING_TODAY', '2000-01-01')
    source = EmptyInbox()
    c.sms_imports.read_source(source, now=replay)
    expected = (replay or actual) - timedelta(days=sms_imports.FIRST_LOOK_DAYS)
    assert source.after == int(expected.timestamp() * 1000)


# These sync/journal files intentionally retain raw wall time. Their timestamps describe protocol
# events or real receipts, never a demo/business date; do not change the running journal work.
JOURNAL_CLOCKS = {
    'sync/identity.py',            # TLS validity uses real time; protocol imports exclude application modules.
    'sync/journal/local.py',       # Last successful synchronization.
    'sync/journal/store.py',       # Journal creation and seen-proposal receipts.
    'sync/journal/backups.py',     # Signed snapshot creation time.
    'sync/journal/device.py',      # Synchronization history and stale-device age.
    'runtime/journal_profile.py',  # Native journal backup file dates.
    'ui/journal.py',               # Real SMS receipt supplied to the journal adapter.
}


def test_direct_clock_calls_stay_in_core_or_documented_journal_files():
    root = Path(__file__).parents[1] / 'lightning'
    direct_clock = re.compile(r'\b(?:datetime\.now|date\.today)\s*\(')
    unexpected = []
    for path in root.rglob('*.py'):
        relative = path.relative_to(root).as_posix()
        if relative == 'core/dates.py' or relative in JOURNAL_CLOCKS:
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if direct_clock.search(line):
                unexpected.append(f'{relative}:{number}')
    assert not unexpected, 'Use core.dates for application or operational time: ' + ', '.join(unexpected)
