"""Mohab's 2026 sample: every bank CSV imports through Import CSV with nothing to review, and the
whole sample loads, reconciles and opens on every tab."""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

import pytest

from lightning.samples import BANK_FILES, MOHAB_2026, load_mohab_2026, rows
from lightning.ui.web import create_app
from screens import Browser, Choose

D = Decimal


@pytest.fixture
def on_2_october(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")


def _lines(name: str) -> int:
    with open(MOHAB_2026 / name, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def _open_accounts(b: Browser) -> None:
    """The accounts from accounts.csv, through the Add account form."""
    labels = {"BANK": "Bank", "CASH": "Cash wallet", "BROKERAGE": "Brokerage", "DEPOSIT": "Certificate",
              "PHYSICAL_ASSET": "Physical asset"}
    for row in rows("accounts.csv"):
        b.open("/accounts/new")
        b.submit({"name": row["Name"], "account_type": Choose(labels[row["Type"]]),
                  "opening_balance": row["Opening balance"], "opening_balance_date": row["Opening date"]},
                 button="Add account")


def test_every_bank_csv_imports_every_row_with_nothing_to_review(c, on_2_october):
    b = Browser(create_app(c))
    _open_accounts(b)
    for name in BANK_FILES:   # CIB Payroll first: its transfers fill the others
        account = next(r["Name"] for r in rows("accounts.csv") if r["File"] == name)
        b.go(account, "Import statement")
        page = b.submit({}, button="Review statement",
                        files={"file": (name, (MOHAB_2026 / name).read_bytes(), "text/csv")})
        if page.shows("Match your columns"):   # the headers are Lightning's own, so this should not happen
            pytest.fail(f"{name} asked for its columns to be matched")
        assert page.shows("To fix 0", "Needs you 0", "Possible duplicates 0"), f"{name}: {page.text[:600]}"
        done = b.submit({}, button="Post ready rows")
        assert done.shows(f"{_lines(name)} posted · 0 skipped · 0 duplicates"), f"{name}: {done.text[:400]}"
    cib = next(a for a in c.accounts.list() if a.name == "CIB Payroll")
    transfers = c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='TRF' AND status='POSTED'")
    assert transfers == 21   # 9 ATM withdrawals, 9 Vodafone Cash top-ups, 3 moves to THNDR
    assert c.position.at(date(2026, 10, 2)).held_for_others == D("6000")   # Mom's 10,000 less the 4,000 back
    assert c.reporting.account_balance(cib.id) > 0


def test_an_internal_row_whose_account_is_unknown_asks_which_account(c, on_2_october):
    flows = c.account_flows
    cib = flows.open_account("CIB Current", "BANK", "2026-09-01", "50,000", institution="CIB")
    flows.open_account("Wallet", "CASH", "2026-09-01", "1,200")
    savings = flows.open_account("Savings", "BANK", "2026-09-01", "0", institution="NBE")
    b = Browser(create_app(c))
    data = ("Date,Amount,Counterparty,Category,Notes\n"
            "2026-09-10,-500.00,Savings pot,Internal transfer,Moved to savings\n"
            "2026-09-11,-300.00,Wallet,Internal transfer,ATM\n").encode()
    b.go("CIB Current", "Import statement")
    page = b.submit({}, button="Review statement", files={"file": ("moves.csv", data, "text/csv")})
    assert page.shows("The category says internal, but no account matches")
    fields = page.form("Post ready rows").fields
    # "Wallet" is one of his accounts, so it comes already picked as the account (a transfer to it).
    wallet = next(k.rsplit("_", 1)[1] for k, v in fields.items() if k.startswith("counterparty_") and v == "Wallet")
    assert fields[f"counterparty_pick_{wallet}"].startswith("account:")
    # The "Savings pot" row gets its account from the counterparty well, like picking it in the list.
    unknown = next(k.rsplit("_", 1)[1] for k, v in fields.items() if k.startswith("counterparty_") and v == "Savings pot")
    page = b.submit({f"counterparty_pick_{unknown}": f"account:{savings.id}"}, button="Post ready rows")
    assert page.shows("2 posted · 0 skipped · 0 duplicates")
    assert c.reporting.account_balance(savings.id) == D("500")
    assert c.reporting.account_balance(cib.id) == D("49200")


def test_the_whole_sample_loads_and_adds_up(c, on_2_october):
    summary = load_mohab_2026(c)
    assert summary == {"accounts": 7, "rows": sum(_lines(n) for n in BANK_FILES), "from": "2026-01-01",
                       "to": "2026-10-02"}
    day = date(2026, 10, 2)
    position = c.position.at(day)
    assert position.held_for_others == D("6000")          # Mom's 10,000, less the 4,000 she took back
    assert position.loans_still_to_pay == D("37500")      # 15 car-loan payments left
    assert position.net_worth == position.what_you_own - position.what_you_owe
    assert {check.status for check in c.integrity.checks(day)} == {"PASS"}
    assert not [p for p in c.planning.all_payments(day, day) if p.status.name == "DUE"]
    held = {c.assets.get_asset(p.asset_id).name for p in c.investments.portfolio(day).open}
    assert {"Commercial International Bank (COMI)", "Fawry for Banking Technology", "Talaat Moustafa Group",
            "Azimut money market fund", "L'Azurde ring", "Gold pound (from grandma)", "BTC 10 g bar",
            "Invesco NASDAQ 100 ETF"} <= held
    dollars = next(a for a in c.accounts.list() if a.name == "Dollar brokerage")
    etf = next(a for a in c.assets.investments() if a.ticker == "QQQM")
    assert (dollars.currency, etf.currency, etf.mic) == ("USD", "USD", "XNAS")
    b = Browser(create_app(c))
    for page in ("/", "/budget", "/investments", "/birdview/expenses", "/plan", "/plan/recurring", "/plan/loans",
                 "/plan/reserves", "/money-from-others", "/transactions", "/checks"):
        b.open(page)
    assert b.open("/checks").shows("Needs attention 0")


def test_the_welcome_page_loads_the_sample_and_the_files_stay_downloadable(c, on_2_october):
    b = Browser(create_app(c))
    welcome = b.open("/")
    assert welcome.shows("Mohab · A full year")
    for name in ("accounts.csv", *BANK_FILES, "thndr.csv", "usd-brokerage.csv", "gold-at-home.csv", "prices.csv",
                 "fx.csv"):
        assert b.client.get(f"/samples/mohab-2026/{name}").status_code == 200
    done = b.submit({}, action="/sample/mohab-2026")
    assert done.shows("Mohab's 2026 added")
    assert len(c.accounts.list()) == 7


def test_sample_opens_on_a_day_inside_its_data_with_no_late_bill(c, monkeypatch):
    """`--sample` pins today inside the data (3V2): opened months later it would show every bill late."""
    from lightning.core.dates import fmt_date, today
    from lightning.samples import SAMPLE_TODAY, pin_sample_today

    monkeypatch.delenv("LIGHTNING_TODAY", raising=False)
    assert pin_sample_today() == fmt_date(min(date.today(), SAMPLE_TODAY))
    assert today() <= SAMPLE_TODAY
    load_mohab_2026(c)
    assert not [p for p in c.planning.all_payments(today(), today()) if p.status.name == "DUE"]
    assert c.planning.what_you_owe(today()).bills_due == 0
    # A date the caller chose is kept: site_shots.py and the tests pin their own.
    assert pin_sample_today({"LIGHTNING_TODAY": "2026-10-02"}) == "2026-10-02"


def test_sample_loaded_on_a_later_day_shows_late_bills_which_is_why_it_is_pinned(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-21")
    load_mohab_2026(c)
    assert c.planning.what_you_owe(date(2026, 10, 21)).bills_due > 0
