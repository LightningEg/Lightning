"""One clock (IT-3BI4): no naive datetime.now(), date.today() or datetime.today() outside core/dates.py.

UTC instants for the journal, sync, backups and market-data (`datetime.now(timezone.utc)`) are real wall-clock time on
purpose and are not matched here."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from lightning.core import dates

ROOT = Path(__file__).resolve().parent.parent / "lightning"
NAIVE = re.compile(r"datetime\.now\(\)|date\.today\(\)|datetime\.today\(\)")
ALLOWED = {"core/dates.py": "the one clock", "samples/__init__.py": "compares the real day with the sample's own day"}


def test_nothing_reads_the_system_clock_but_core_dates():
    hits = [f"{p.relative_to(ROOT).as_posix()}:{n}" for p in ROOT.rglob("*.py") if p.relative_to(ROOT).as_posix() not in ALLOWED
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if NAIVE.search(line)]
    assert not hits, hits


def test_now_follows_the_pinned_day(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    assert dates.now().date() == date(2026, 10, 2) and dates.today() == date(2026, 10, 2)
    monkeypatch.delenv("LIGHTNING_TODAY")
    assert dates.now().tzinfo is None
