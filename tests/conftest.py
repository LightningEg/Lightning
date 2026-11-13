from __future__ import annotations

import os

import pytest

# Tests use dates across 2026; pin "today" so future-date rules don't depend on when they run.
os.environ["LIGHTNING_TODAY"] = "2026-12-31"
# Never ask the real price sources from a test (lightning/workflows/live_prices.py).
os.environ["LIGHTNING_PRICES_OFFLINE"] = "1"

from lightning.bootstrap import Container, build


_BROWSER_SKIP = ("playwright", "chromium")


def _browser_skip(report) -> bool:
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else str(longrepr)
    return any(word in reason.lower() for word in _BROWSER_SKIP)


def _fail_browser_skip(report):
    # CI sets LIGHTNING_REQUIRE_BROWSER=1 (tests/browser_support.py): a browser test may not skip for want of a browser.
    if report.skipped and os.environ.get("LIGHTNING_REQUIRE_BROWSER") == "1" and _browser_skip(report):
        report.outcome = "failed"
        report.longrepr = f"Browser test skipped while LIGHTNING_REQUIRE_BROWSER=1: {report.longrepr}"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    _fail_browser_skip(outcome.get_result())


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    _fail_browser_skip(outcome.get_result())


def pytest_configure(config):
    config.addinivalue_line("markers", "real_kdf: keep the shipped Argon2 costs instead of the cheap test ones")


@pytest.fixture(autouse=True)
def cheap_key_locks(request, monkeypatch):
    # Profile keys are locked with Argon2 at 128 and 256 MiB (lightning/security/keys.py), most of the
    # suite's time. Tests use the smallest cost the key file accepts; lock two stays the slower one.
    if request.node.get_closest_marker("real_kdf"):
        return
    from lightning.security import keys
    monkeypatch.setattr(keys, "ARGON2_MEMORY_KIB", keys._ARGON2_MEMORY_MIN_KIB)
    monkeypatch.setattr(keys, "ARGON2_ITERATIONS", keys._ARGON2_ITERATIONS_MIN)
    monkeypatch.setattr(keys, "RECOVERY_MEMORY_KIB", keys._ARGON2_MEMORY_MIN_KIB)
    monkeypatch.setattr(keys, "RECOVERY_ITERATIONS", keys._ARGON2_ITERATIONS_MIN + 1)


@pytest.fixture(autouse=True)
def nearby_on_this_machine(monkeypatch):
    """The PC's phone search (NF-4M) asks only this machine and briefly: the suite never broadcasts to the network."""
    from lightning.sync import nearby
    monkeypatch.setattr(nearby, "destinations", lambda: ["127.0.0.1"])
    monkeypatch.setattr(nearby, "SEARCH_SECONDS", 0.15)


@pytest.fixture(autouse=True)
def fixed_audit_clock(monkeypatch):
    # Historical fixtures also depend on record creation timestamps, not only
    # LIGHTNING_TODAY. Keep them independent of the host clock and timezone.
    from datetime import datetime, timezone
    from lightning.core import dates
    monkeypatch.setattr(dates, "_local_now", lambda: datetime(2026, 9, 30, 12, tzinfo=timezone.utc))


@pytest.fixture
def c(tmp_path) -> Container:
    container = build(tmp_path / "test.db")
    yield container
    container.db.close()


@pytest.fixture
def strict_c(tmp_path) -> Container:
    """A plaintext fixture with the owning-thread and closed-session checks of encrypted profiles."""
    container = build(tmp_path / "strict.db", strict_thread=True)
    yield container
    container.db.close()


@pytest.fixture
def setup(c):
    """A typical household: bank, wallet, a CD, THNDR cash."""
    f = c.account_flows
    accounts = {
        "cib": f.open_account("CIB Current", "BANK", "2026-09-01", "50,000", institution="CIB"),
        "wallet": f.open_account("Wallet", "CASH", "2026-09-01", "1200"),
        # Emulate a pre-portfolio database: these historical accounts had liquid
        # cash in DEPOSIT. Current CD portfolios are created with zero cash and
        # certificates are entered through DepositService.purchase().
        "cd": f.open_account("CIB CD", "BANK", "2026-09-01", "5000", institution="CIB"),
        "thndr": f.open_account("THNDR", "BROKERAGE", "2026-09-01", "0", institution="THNDR"),
    }
    legacy_class = c.assets.get_class_by_code("DEPOSIT.CD")
    c.db.execute("UPDATE accounts SET code=?,account_type='DEPOSIT',cash_class_id=? WHERE id=?",
                 ("CIB-CD-EGP", legacy_class.id, accounts["cd"].id))
    accounts["cd"] = c.accounts.get(accounts["cd"].id)
    cats = {code: c.categories.get_by_code(code) for code in (
        "EXP.PERSONAL.FOOD", "EXP.WORK.SOFTWARE", "EXP.WORK.SALARY", "EXP.INVEST.INTEREST")}
    return accounts, cats
