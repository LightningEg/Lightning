"""Use-case audit 2026-10-29: reproduce each finding on throwaway dummy profiles.

Run from the repo root: python reports/2026-10-29-use-case-audit/evidence/use_cases.py
Each block prints what a person would see. F2 and F4 print the fixed behaviour on the branch that fixes them.
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LIGHTNING_TODAY", "2026-12-31")
os.environ["LIGHTNING_PRICES_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from lightning.bootstrap import build  # noqa: E402
from lightning.core.errors import LightningError  # noqa: E402
from lightning.ui.web import create_app  # noqa: E402


def profile():
    return build(Path(tempfile.mkdtemp()) / "dummy.db")


def tried(action):
    try:
        action()
        return "accepted"
    except LightningError as exc:
        return f"refused: {exc.message}"


def f1_deficit_before_opening():
    c = profile()
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    bank = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "10,000")
    c.transactions.record_outflow("2026-01-10", bank.id, "9,000", food)
    print("F1 move the opening date past January's spending:",
          tried(lambda: c.account_flows.update_account(bank.id, "Bank", "BANK", "2026-03-01", "10000")))
    print("   balance on 2026-01-31:", c.reporting.account_balance(bank.id, "2026-01-31"))
    check = next(x for x in c.integrity.checks("2026-01-31") if x.name.startswith("No cash account"))
    print("   Integrity:", check.name, check.status)


def f2_skip_part_paid_instalment():
    c = profile()
    bank = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "100,000")
    loan = c.planning.create(kind="LOAN", name="Car", amount="2500", frequency="MONTHLY", start_date="2026-02-01",
                             payment_count="12", account_id=bank.id)
    client = TestClient(create_app(c), follow_redirects=False)
    client.post(f"/plan/items/{loan}/pay", data={"due": "2026-02-01", "outcome": "record", "date_paid": "2026-02-01",
                                                 "amount": "1000", "account_id": str(bank.id)})
    still = lambda: c.planning.loan_progress(c.planning.get(loan))["still_to_pay"]
    print("F2 still to pay after paying 1,000 of 2,500:", still())
    print("   Move to the end offered:",
          "Move to the end of the loan" in client.get(f"/plan/items/{loan}/pay?due=2026-02-01").text)
    client.post(f"/plan/items/{loan}/pay", data={"due": "2026-02-01", "outcome": "skip"})
    print("   still to pay after posting skip:", still(), "· linked payments:", len(c.planning.linked_transaction_ids()))


def f3_bill_link_after_edit():
    c = profile()
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    bank = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "100,000")
    bill = c.planning.create(kind="BILL", name="Internet", amount="500", frequency="MONTHLY", start_date="2026-02-05",
                             account_id=bank.id, category_id=food)
    paid = c.planning.record_payment(bill, "2026-02-05", "2026-02-05", "500", bank.id)
    c.transactions.update_money(paid, "2026-12-05", bank.id, "5000", food)
    february = c.planning.payments(c.planning.get(bill), "2026-02-28", date(2026, 2, 28))[0]
    print("F3 after moving the payment to December at 5,000: February is", february.status.value,
          "for", february.paid_amount, "· bills due on 2026-02-28:", c.planning.what_you_owe(date(2026, 2, 28)).bills_due)


def f4_resent_money_forms():
    c = profile()
    bank = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "500,000")
    circle = c.account_flows.open_account("Office", "GAMEYA", "2026-01-01", "0")
    c.gameya.save_terms(circle.id, organiser="Organiser", members=10, installment="2000", first_date="2026-02-05",
                        my_turn=3, funding_account_id=bank.id, payout_account_id=bank.id)
    client = TestClient(create_app(c), follow_redirects=False)
    import re
    token = re.search(r'name="submission" value="([a-f0-9]{32})"', client.get(f"/gameya/{circle.id}").text).group(1)
    form = {"date": "2026-02-05", "amount": "2000", "account_id": str(bank.id), "submission": token}
    for _ in range(2):
        client.post(f"/gameya/{circle.id}/instalment", data=form)
    print("F4 instalments recorded after one form sent twice:", c.gameya.progress(circle.id).paid)


def f5_swapped_conversion():
    c = profile()
    bank = c.account_flows.open_account("Bank", "BANK", "2026-01-01", "100,000")
    c.currencies.register("USD")
    c.fx.save("USD", "2026-01-01", "50")
    usd = c.account_flows.open_account("Dollars", "BANK", "2026-01-01", "0", currency="USD")
    c.transactions.record_conversion("2026-01-05", bank.id, usd.id, "5000", "100")
    print("F5 net worth before the typo:", c.reporting.net_worth("2026-01-06").total)
    print("   quote for sent 100, received 5,000:", c.transactions.conversion_quote("2026-01-10", bank.id, usd.id, "100", "5000"))
    print("   saving it:", tried(lambda: c.transactions.record_conversion("2026-01-10", bank.id, usd.id, "100", "5000")))
    print("   net worth on 2026-01-31:", c.reporting.net_worth("2026-01-31").total)


for finding in (f1_deficit_before_opening, f2_skip_part_paid_instalment, f3_bill_link_after_edit,
                f4_resent_money_forms, f5_swapped_conversion):
    finding()
