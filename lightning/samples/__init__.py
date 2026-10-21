"""Sample data people can load to try Lightning without their own: Mohab's 2026, one CSV per account.

The files live in ``lightning/samples/mohab_2026`` (``generate_mohab_2026.py`` writes them):

- ``accounts.csv``: the seven accounts and their 1 January balances (a Currency column: blank is the profile currency).
- ``cib-payroll.csv``, ``cash-wallet.csv``, ``vodafone-cash.csv``: bank CSV format. They load through
  the same importer as Import CSV and need nothing reviewed. Import CIB Payroll first: its transfers
  fill the wallet, Vodafone Cash and THNDR.
- ``nbe-3-year-certificate.csv``: the certificate bought from CIB on 1 January (a CD portfolio holds
  certificates, not cash).
- ``thndr.csv``: buys, a sale and a dividend; ``gold-at-home.csv``: the gold pieces; ``prices.csv``:
  month-end prices, which drive the revaluations.
- ``usd-brokerage.csv``: the dollar brokerage's Nasdaq ETF (its Exchange column makes the asset USD); ``fx.csv``:
  what a dollar cost in pounds, typed month-end rates.

``load_mohab_2026`` fills an empty Lightning with all of it, then adds the plan (budget, emergency
fund, recurring bills, a yearly course and bonus, the car loan), the same way the screens would.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from lightning.core.dates import fmt_date, today
from lightning.core.errors import NotFoundError

MOHAB_2026 = Path(__file__).parent / "mohab_2026"
BANK_FILES = ("cib-payroll.csv", "cash-wallet.csv", "vodafone-cash.csv")   # in this order
FILES = ("accounts.csv", "nbe-3-year-certificate.csv", *BANK_FILES, "thndr.csv", "usd-brokerage.csv", "gold-at-home.csv",
         "prices.csv", "fx.csv")
SAMPLE_TODAY = date(2026, 10, 2)  # the sample's last row: its bills are paid up to here, none is late
GOLD_PRICES = {"GOLD21": "REF:GLD-21K", "GOLD24": "REF:GLD-24K"}


def pin_sample_today(environ=None) -> str:
    """Make "today" a day inside Mohab's 2026 when ``--sample`` opens, so it never shows bills late for months
    that have no rows. A ``LIGHTNING_TODAY`` the caller already set is kept. Returns the date in use."""
    import os
    environ = os.environ if environ is None else environ
    if not environ.get("LIGHTNING_TODAY"):
        environ["LIGHTNING_TODAY"] = fmt_date(min(date.today(), SAMPLE_TODAY))
    return environ["LIGHTNING_TODAY"]


def rows(name: str) -> list[dict[str, str]]:
    with open(MOHAB_2026 / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _due(day: str, until: date) -> bool:
    return date.fromisoformat(day) <= until


def _investment(c, name: str, class_code: str, ticker: str, mic: str = ""):
    from lightning.assets.domain import INVESTMENT_KINDS
    try:
        return c.assets.get_asset_by_code(f"{INVESTMENT_KINDS[class_code].prefix}:{ticker}")
    except NotFoundError:
        return c.assets.create_investment(name, class_code, ticker, mic=mic)


def import_bank_file(c, account_id: int, name: str) -> dict:
    """Import one bank-format sample file the way Import CSV does, posting every ready row.

    Returns the import summary; a row that is not ready is an error in the sample."""
    data = (MOHAB_2026 / name).read_bytes()
    batch_id, _ = c.bank_imports.stage(account_id, name, data)
    _, staged = c.bank_imports.preview(batch_id)
    waiting = [row for row in staged if not row["_ready"]]
    if waiting:
        raise ValueError(f"{name}: {len(waiting)} rows need a decision, starting at line {waiting[0]['_line']}")
    result = c.bank_imports.confirm(batch_id, {row["_import_row_id"]: {} for row in staged})
    if result["errors"]:
        raise ValueError(f"{name}: {result['errors']}")
    return result


def load_mohab_2026(c, as_of: date | None = None) -> dict:
    """Fill an empty Lightning with Mohab's 2026. Returns a short summary for messages."""
    if c.accounts.list():
        raise ValueError("The 2026 sample can only be added to an empty Lightning.")
    day = as_of or today()
    accounts = {}
    with c.db.transaction():
        for code in sorted({row["Currency"] for row in rows("accounts.csv") if row.get("Currency")}):
            c.currencies.register(code)
        for row in rows("fx.csv"):
            if _due(row["Date"], day):
                c.fx.save(row["Currency"], row["Date"], row["Rate"])
        for row in rows("accounts.csv"):
            accounts[row["Name"]] = c.account_flows.open_account(
                row["Name"], row["Type"], row["Opening date"], row["Opening balance"],
                institution=row["Institution"], currency=row.get("Currency") or None).id
    files = {row["File"]: accounts[row["Name"]] for row in rows("accounts.csv") if row["File"]}
    for row in rows("nbe-3-year-certificate.csv"):
        if _due(row["Date"], day):
            c.deposits.purchase(files["nbe-3-year-certificate.csv"], row["Certificate"], row["Date"],
                                row["Earliest withdrawal"], row["Maturity"], row["Principal"], row["Annual rate"],
                                row["Interest"], row["Payout"], "MONTHLY", accounts[row["Interest to"]],
                                accounts[row["Paid from"]])
    posted = 0
    for name in BANK_FILES:
        posted += import_bank_file(c, files[name], name)["posted"]

    with c.db.transaction():
        gold = files["gold-at-home.csv"]
        for name in ("thndr.csv", "usd-brokerage.csv"):
            for row in rows(name):
                if not _due(row["Date"], day):
                    continue
                account = files[name]
                asset = _investment(c, row["Investment"], row["Class"], row["Ticker"], row.get("Exchange", ""))
                if row["Action"] == "Dividend":
                    c.investments.dividend(row["Date"], account, asset.id, row["Total"], row["Notes"])
                    continue
                trade = c.investments.buy_total if row["Action"] == "Buy" else c.investments.sell_total
                trade(row["Date"], account, asset.id, row["Units"], row["Total"], notes=row["Notes"], fees=row["Fees"])
                fees = float(row["Fees"] or 0)
                gross = float(row["Total"]) - fees if row["Action"] == "Buy" else float(row["Total"]) + fees
                c.assets.set_price(asset.id, row["Date"], f"{gross / float(row['Units']):.4f}")
        for row in rows("gold-at-home.csv"):
            if not _due(row["Date"], day):
                continue
            reference = c.assets.get_asset_by_code(f"REF:GLD-{row['Karat']}K")
            piece = c.physical_items.create(gold, row["Piece"], row["Kind"], row["Grams"], int(row["Karat"]),
                                            reference.id)
            if row["Action"] == "Already owned":
                txn = c.investments.add_holding(gold, piece, "1", row["Total"], row["Date"], row["Notes"])
                c.physical_items.record_trade_details(txn.id, piece, "OPN", "0", row["Notes"])
            else:
                txn = c.investments.buy_total(row["Date"], gold, piece, "1", row["Total"],
                                              accounts[row["Paid from"]], row["Notes"], "0", True)
                c.physical_items.record_trade_details(txn.id, piece, "BUY", row["Workmanship"], row["Notes"])
        for row in rows("prices.csv"):
            if not _due(row["Date"], day):
                continue
            code = GOLD_PRICES.get(row["Ticker"])
            asset = (c.assets.get_asset_by_code(code) if code else
                     next(a for a in c.assets.investments() if a.code.endswith(f":{row['Ticker']}")))
            c.assets.set_price(asset.id, row["Date"], row["Price"])

        _plan(c, accounts, day)
    c.planning.match_payments(day)
    try:
        c.reevaluations.process_due()
    except Exception:  # valuation checkpoints are detail; the sample stands without them
        pass
    return {"accounts": len(accounts), "rows": posted, "from": "2026-01-01", "to": fmt_date(day)}


def _plan(c, accounts: dict[str, int], day: date) -> None:
    """The plan side: a budget from his spending, a 20,000 emergency fund, his bills and the car loan."""
    month = fmt_date(day)[:7]
    suggested = c.budgets.suggested_plan(month)
    if suggested:
        c.budgets.save_month(month, suggested)
    c.reserves.set_emergency_fund("20,000", c.budgets.emergency_fund(month, None).target or 0)

    def category(text):
        return str(c.categories.find_by_text(text).id)

    def party(name):
        found = c.counterparties.resolve(name)
        return str(found["id"] if found else c.counterparties.create(name))

    cib, vodafone = str(accounts["CIB Payroll"]), str(accounts["Vodafone Cash"])
    for kind, name, amount, start, account, text in (
            ("INCOME", "ACME Egypt", "50,000", "2026-10-01", cib, "Work › Salary"),
            ("BILL", "Landlord", "12,000", "2026-10-03", cib, "Personal › Housing & Rent"),
            ("SUBSCRIPTION", "Netflix", "240", "2026-10-12", cib, "Personal › Entertainment"),
            ("BILL", "WE Internet", "650", "2026-10-20", cib, "Personal › Utilities & Bills"),
            ("BILL", "North Cairo Electricity", "720", "2026-10-24", cib, "Personal › Utilities & Bills"),
            ("SUBSCRIPTION", "Vodafone", "350", "2026-10-09", vodafone, "Personal › Utilities & Bills")):
        c.planning.create(kind=kind, name=name, amount=amount, frequency="MONTHLY", interval_count="1",
                          start_date=start, account_id=account, category_id=category(text),
                          counterparty_id=party(name))
    # Two yearly events, so the months ahead differ: the English course renews in November, the bonus comes in December.
    for kind, name, amount, start, text, payee in (
            ("BILL", "English course", "7,800", "2026-11-15", "Personal › Education", "British Council"),
            ("INCOME", "Year-end bonus", "50,000", "2026-12-20", "Work › Bonus", "ACME Egypt")):
        c.planning.create(kind=kind, name=name, amount=amount, frequency="YEARLY", interval_count="1",
                          start_date=start, account_id=cib, category_id=category(text),
                          counterparty_id=party(payee))
    c.planning.create(kind="LOAN", name="Car loan", amount="2,500", frequency="MONTHLY", interval_count="1",
                      start_date="2026-01-05", payment_count="24", principal="60,000", account_id=cib,
                      category_id=category("System Categories › Loan payments"), counterparty_id=party("Toyota Finance"),
                      notes="Toyota Finance")
