"""9K: opening a profile and `python -m lightning` run one list of tasks, so month-end checkpoints are posted
even when no price file fills (before, only the legacy entrypoint posted them)."""

import logging

from lightning.samples import load_mohab_2026
from lightning.workflows import profile_open


def test_opening_a_profile_posts_the_month_end_checkpoints_that_are_due(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    before = c.db.scalar("SELECT COUNT(*) FROM reevaluation_periods")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-05")  # October and November month-ends have passed
    monkeypatch.setattr("lightning.workflows.market_prices.fill_if_due", lambda c, on: None)  # no price file
    profile_open.open_profile_tasks(c, wait=False)
    after = c.db.scalar("SELECT COUNT(*) FROM reevaluation_periods")
    assert after > before
    c.reevaluations.process_due()
    assert c.db.scalar("SELECT COUNT(*) FROM reevaluation_periods") == after  # nothing left for the legacy path


def test_a_failing_price_step_is_logged_and_the_profile_still_opens(c, monkeypatch, caplog):
    def broken(container, on):
        raise RuntimeError("price file unreadable")
    monkeypatch.setattr("lightning.workflows.market_prices.fill_if_due", broken)
    with caplog.at_level(logging.WARNING, logger="lightning.workflows.profile_open"):
        reports = profile_open.open_profile_tasks(c, wait=True)
    assert "Price step broken failed" in caplog.text and "price file unreadable" in caplog.text
    assert any("monthly checkpoint" in str(report) for report in reports)
