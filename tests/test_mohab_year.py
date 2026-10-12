"""Mohab's year, through the screens only: the reference workflow in docs/PROJECT_OVERVIEW.md.

Mohab is 31, salaried, in Cairo. He starts with an empty Lightning on 30 September 2026, sets up the
last three months, and then lives a year in it: October 2026 to September 2027. He only does what a
person can do in the app: open pages, follow links, fill in the forms on the page and press their
buttons (tests/screens.py). Along the way he asks the questions a salaried person asks. Each one is
answered by starting at the Overview and clicking through to the page that answers it, and the test
for that question checks both the route he took and what the page told him.

Each open product gap has a direct screen assertion. When a gap is fixed, update its assertion and
the Overview's "Today" column in docs/PROJECT_OVERVIEW.md together.

What Mohab's test focuses on. Mohab is a real Egyptian user, not a tester: he judges Lightning by whether
he gets the right answer quickly, with as little effort and as few words to decode as possible.
Lightning ships as a Windows app (a WebView2 window over the same pages), so every check is a screen
he would see there.
- Right answers: every figure reconciles across tabs and after a year of real life (fees, refunds,
  a bonus, early pay, a raise, Eid, installments, a sale, a job change).
- Usability: each question is answered by starting at the Overview and clicking through; the route is
  checked, and a dead end, a missing way back or a lost half-done task is a failure.
- Efficiency: count the effort. One typed balance instead of clearing lines one by one; one fix
  instead of one per row; nothing he must re-enter.
- Speed: pages must feel instant on an ordinary PC, encrypted, in the WebView2 window; long
  periods stay summarised (months, not 365 days) and pages stay light.
- Simplicity: the fewest controls and choices that do the job; no placeholder text to delete, no
  feature he needs a manual for.
- Clarity: plain words and numbers a person can read (no "System", no −1,351.7%), the date or period
  every figure belongs to, and a warning when something cannot work as planned.
- UI: compact rows, readable messages, and layouts that work in the app window and on a phone.
User feedback (the "user feedback" folder) is added here as steps Mohab takes and checked by screen
assertions. Speed and look are judged on a real PC and in a browser; this file covers what screens show.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from lightning.bootstrap import build
from lightning.core import dates
from lightning.ui.web import create_app
from screens import TICK, Browser, Choose, Screen

D = Decimal


def money(text: str) -> Decimal:
    """The first amount in a piece of page text: '−1,299.00 EGP' -> Decimal('-1299.00')."""
    found = re.search(r"([+−-]?)\s?(\d[\d,]*(?:\.\d+)?)", text)
    assert found, f"No amount in {text!r}"
    sign = -1 if found.group(1) in ("−", "-") else 1
    return sign * D(found.group(2).replace(",", ""))


@dataclass
class Answer:
    question: str
    trail: list[str]          # the pages he went through, starting at the Overview
    screen: Screen            # where he found the answer

    def shows(self, *texts) -> bool:
        return self.screen.shows(*texts)

    def figure(self, label: str) -> Decimal:
        return money(self.screen.after(label))


class Mohab:
    """One user and his browser tab."""

    def __init__(self, c):
        self.c = c
        self.b = Browser(create_app(c))
        self.answers: dict[str, Answer] = {}
        self.notes: dict[str, object] = {}

    # -------------------------------------------------------------- time and questions
    def on(self, day: str) -> None:
        """A new day: he opens Lightning again, so the period he last picked is forgotten."""
        os.environ["LIGHTNING_TODAY"] = day
        self.b.client.cookies.clear()

    def ask(self, key: str, question: str, *clicks: str, start: str = "/") -> Screen:
        """Start at the Overview (or ``start``) and click through to the answer."""
        screen = self.b.go(*clicks, start=start)
        self.answers[key] = Answer(question, list(self.b.trail), screen)
        return screen

    # -------------------------------------------------------------- things he does
    def account(self, name: str, kind: str, balance: str, when: str = "1/7", bank: str = "") -> Screen:
        self.b.go("+ Add account")
        return self.b.submit({"name": name, "account_type": Choose(kind), "institution": bank,
                              "opening_balance": balance, "opening_balance_date": when}, button="Add account")

    def enter(self, account: str, when: str, party: str, category: str, amount: str, **more) -> Screen:
        """Type one row into an account's register and press Add."""
        self.b.go(account)
        return self.b.submit({"date": when, "counterparty": party, "category": category, "amount": amount} | more,
                             button="Add")

    def trade(self, action: str, when: str, find: str, **values) -> Screen:
        """Buy, sell or record a dividend in THNDR, picking the investment from the search results."""
        screen = self.b.go("THNDR")
        picked = next(x for x in screen.catalogue("trade-instrument-catalogue")
                      if find.casefold() in f"{x.get('ticker', '')} {x.get('name', '')}".casefold())
        return self.b.submit({"instrument_key": picked["key"], "trade_action": action, "date": when} | values,
                             action="investment-entry")

    def gold_piece(self, name: str, kind: str, grams: str) -> Screen:
        self.b.go("Gold at home", "Add item")
        return self.b.submit({"name": name, "kind": kind, "weight": grams, "karat": Choose("21K"),
                              "reference_asset_id": Choose("21K")}, button="Create item")

    def prices(self, when: str, typed: dict[str, str]) -> Screen:
        screen = self.b.go("Investments", "Prices")
        fields = {}
        for name, price in typed.items():
            rows = [block for block in re.findall(r"(?s)<tr\b.*?</tr>", screen.html)
                    if name.casefold() in re.sub(r"<[^>]+>", " ", block).casefold()]
            names = [re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', row)
                     for row in rows]
            field = next((field for row_names in names for field in row_names if field.startswith("p_")), None)
            assert field is not None, f"No latest-price field found for {name!r}"
            fields[field] = price
        return self.b.submit({"date": when} | fields,
                             button="Save prices")

    def track(self, name: str) -> Screen:
        """Cash planning › Recurring › 'Looks recurring' › Track, then Add on the filled-in form."""
        screen = self.b.go("Cash planning", "Recurring")
        link = next(l for l in screen.links if l.text == "Track" and f"name={name.replace(' ', '%20')}&" in l.href)
        self.b.open(link.href)
        return self.b.submit({}, button="Add")

    def add_loan(self, name: str, party: str, amount: str, first: str, payments: str, principal: str) -> Screen:
        self.b.go("Cash planning", "Loans", "Add loan")
        return self.b.submit({"name": name, "counterparty": party, "amount": amount, "start_date": first,
                              "payment_count": payments, "principal": principal,
                              "account_id": Choose("CIB Payroll")}, button="Add")

    def _pay_link(self, screen: Screen, name: str) -> str:
        at = screen.html.find(name)
        assert at >= 0, f"{name} is not on {screen.path}"
        found = re.search(r'href="(/plan/items/\d+/pay\?[^"]+)"', screen.html[at:])
        assert found, f"No Mark paid for {name} on {screen.path}"
        return found.group(1).replace("&amp;", "&")

    def pay_from_overview(self, item: str) -> Screen:
        """Overview › Needs you › Mark paid › Record and mark paid."""
        self.b.open(self._pay_link(self.b.go(), item))
        return self.b.submit({}, button="Record and mark")

    def receive_salary(self, employer: str) -> Screen:
        """Cash planning › Mark received › Record and mark received."""
        self.b.open(self._pay_link(self.b.go("Cash planning"), employer))
        return self.b.submit({}, button="Record and mark received")

    def transaction_id(self, account: str, party: str) -> str:
        """The newest register row for ``party`` in ``account``."""
        screen = self.b.go(account)
        for block in re.findall(r"(?s)<tr\b.*?</tr>", screen.html):
            if party in block:
                found = re.search(r"/transactions/(\d+)", block) or re.search(r"edit=(\d+)", block)
                if found:
                    return found.group(1)
        raise AssertionError(f"No row for {party} in {account}")

    def to_reserve(self, account: str, party: str, reserve: str) -> Screen:
        """Open the payment's details and apply it to the reserve it was for."""
        self.b.open(f"/transactions/{self.transaction_id(account, party)}")
        return self.b.submit({"reserve_id": Choose(reserve)}, button="Apply payment")

    def settle_due_income(self, name: str) -> Screen:
        """Cash planning › Recurring › the income's "N due" › confirm the payment it suggests, until none is due."""
        for _ in range(12):
            screen = self.b.go("Cash planning", "Recurring")
            at = screen.html.find(f">{name}<")
            due = re.search(r'href="(/plan/items/\d+/pay\?due=[^"]+)"[^>]*>\d+ due<', screen.html[at:]) if at >= 0 else None
            if not due:
                return screen
            popup = self.b.open(due.group(1).replace("&amp;", "&"))
            button = next((text for text in ("Use this", "Link this payment") if popup.shows(text)), None)
            assert button, f"Nothing is suggested for {name}'s payment: {popup.text[:300]}"
            self.b.submit({}, button=button)
        raise AssertionError(f"{name} kept showing payments due")

    def plan_category(self, name: str, amount: str) -> Screen:
        """On the Budget page he is on, type a new amount into the category's one field and save it."""
        found = re.search(rf'(?s)<form\b[^>]*action="(/budget/rule/\d+)"(?:(?!</form>).)*aria-label="Budget for {re.escape(html.escape(name))}:',
                          self.b.page.html)
        assert found, f"No budget field for {name} on {self.b.page.path}"
        return self.b.submit({"rule": amount}, action=found.group(1))

    def period(self, page: str, date_from: str, date_to: str) -> Screen:
        """Press Custom on a report and type the dates."""
        self.b.go(page) if page else self.b.go()
        return self.b.submit({"date_from": date_from, "date_to": date_to}, button="Custom")

    def delete_newest(self, account: str, party: str) -> Screen:
        self.b.open(f"/transactions/{self.transaction_id(account, party)}")
        return self.b.submit({}, button="Delete")

    def fix_amount(self, account: str, party: str, amount: str) -> Screen:
        """Edit the row in place: the register turns it into a form; change the amount and save."""
        txn = self.transaction_id(account, party)
        screen = self.b.go(account)
        self.b.open(next(l.href for l in screen.links if f"edit={txn}" in l.href))
        return self.b.submit({"amount": amount}, action=f"/register/{txn}")

    def month(self, m: str, salary: str | None = "45,000", rent: str = "12,000", employer: str = "ACME Egypt",
              skip: tuple[str, ...] = ()) -> None:
        """An ordinary month, typed into the registers: pay, rent, the car loan, food, phone, internet,
        electricity, the monthly gift to Mom and the bank fee."""
        rows = [(1, "CIB Payroll", employer, "Salary", salary),
                (2, "CIB Payroll", "Carrefour", "Food & Groceries", "-3,250"),
                (3, "CIB Payroll", "Landlord", "Housing & Rent", f"-{rent}"),
                (5, "CIB Payroll", "Cash wallet", "", "-3,000"),
                (5, "CIB Payroll", "Toyota Finance", "Loan payments", "-2,500"),
                (7, "CIB Payroll", "Vodafone Cash", "", "-1,000"),
                (9, "Vodafone Cash", "Vodafone", "Utilities & Bills", "-350"),
                (10, "CIB Payroll", "Talabat", "Eating Out", "-480"),
                (12, "Cash wallet", "Microbus", "Personal › Transportation", "-80"),
                (15, "CIB Payroll", "NBE", "Interest", "1,833.33"),
                (16, "Cash wallet", "Koshary El Tahrir", "Eating Out", "-190"),
                (20, "CIB Payroll", "WE Internet", "Utilities & Bills", "-650"),
                (22, "CIB Payroll", "Seoudi", "Food & Groceries", "-1,420"),
                (24, "CIB Payroll", "North Cairo Electricity", "Utilities & Bills", "-480"),
                (25, "CIB Payroll", "Mom", "Gifts & Donations", "-2,000"),
                (28, "CIB Payroll", "CIB", "Fees & Charges", "-15")]
        if m >= "2027-04":
            rows.append((15, "CIB Payroll", "valU", "Loan payments", "-2,000"))
        for day, account, party, category, amount in rows:
            if amount and party not in skip:
                self.enter(account, f"{m}-{day:02d}", party, category, amount)


# ------------------------------------------------------------------ the year

def _statement() -> bytes:
    """Three months of CIB, as the bank exports it: one signed amount column."""
    rows = []
    for m, groceries, seoudi, talabat in (("07", "3,180.40", "1,388.10", "540.25"), ("08", "3,310.20", "1,452.60", "412.00"),
                                         ("09", "3,250.75", "1,420.40", "468.50")):
        rows += [(f"01/{m}/2026", "ACME EGYPT PAYROLL", "45,000.00"), (f"02/{m}/2026", "CARREFOUR MAADI", f"-{groceries}"),
                 (f"03/{m}/2026", "TRANSFER TO LANDLORD", "-12,000.00"), (f"05/{m}/2026", "ATM WITHDRAWAL", "-3,000.00"),
                 (f"05/{m}/2026", "TOYOTA FINANCE", "-2,500.00"), (f"07/{m}/2026", "VODAFONE CASH TOPUP", "-1,000.00"),
                 (f"10/{m}/2026", "TALABAT", f"-{talabat}"), (f"15/{m}/2026", "NBE CD INTEREST", "1,833.33"),
                 (f"20/{m}/2026", "WE INTERNET", "-650.00"), (f"22/{m}/2026", "SEOUDI MARKET", f"-{seoudi}"),
                 (f"24/{m}/2026", "NORTH CAIRO ELECTRICITY", "-480.00"), (f"25/{m}/2026", "INSTAPAY MOM", "-2,000.00"),
                 (f"28/{m}/2026", "CIB MONTHLY FEE", "-15.00")]
    rows += [("10/08/2026", "INSTAPAY FROM MOM", "10,000.00"), ("11/08/2026", "TRANSFER TO THNDR", "-20,000.00"),
             ("18/08/2026", "AMAZON.EG", "-1,299.00"), ("14/09/2026", "L AZURDE", "-18,450.00")]
    return ("Date,Description,Amount\n" + "\n".join(f'{d},{t},"{a}"' for d, t, a in rows) + "\n").encode()


# What Mohab answers for each imported name: (counterparty, category, transfer to, held for). None = skip.
IMPORT_DECISIONS = {
    "ACME EGYPT PAYROLL": ("ACME Egypt", "Salary", None, None),
    "CARREFOUR MAADI": ("Carrefour", "Food & Groceries", None, None),
    "TRANSFER TO LANDLORD": ("Landlord", "Housing & Rent", None, None),
    "ATM WITHDRAWAL": ("", None, "Cash wallet", None),
    "TOYOTA FINANCE": ("Toyota Finance", "Loan payments", None, None),
    "VODAFONE CASH TOPUP": ("", None, "Vodafone Cash", None),
    "TALABAT": ("Talabat", "Eating Out", None, None),
    "NBE CD INTEREST": ("NBE", "Interest", None, None),
    "WE INTERNET": ("WE Internet", "Utilities & Bills", None, None),
    "SEOUDI MARKET": ("Seoudi", "Food & Groceries", None, None),
    "NORTH CAIRO ELECTRICITY": ("North Cairo Electricity", "Utilities & Bills", None, None),
    "INSTAPAY MOM": ("Mom", "Gifts & Donations", None, None),
    "CIB MONTHLY FEE": ("CIB", "Fees & Charges", None, None),
    "INSTAPAY FROM MOM": ("Mom", "Money Held for Others", None, "Mom"),
    "TRANSFER TO THNDR": ("", None, "THNDR", None),
    "AMAZON.EG": ("Amazon", "Shopping", None, None),
    "L AZURDE": None,  # the ring: he records it from Gold at home instead, so it is not counted twice
}


def _first_evening(o: Mohab) -> None:
    """30 September 2026: an empty Lightning, the last three months set up."""
    b = o.b
    o.on("2026-09-30")
    o.ask("start", "I have nothing in here yet. Where do I start?")

    b.go("Bank")
    # CIB holds the 100,000 he puts into the NBE certificate on 1 July (a CD portfolio holds no cash).
    b.submit({"name": "CIB Payroll", "opening_balance": "138,500", "opening_balance_date": "1/7"}, button="Add account")
    for name, kind, balance, *bank in (("Cash wallet", "Cash wallet", "2,000"), ("Vodafone Cash", "Cash wallet", "1,200"),
                                ("THNDR", "Brokerage", "0"), ("NBE 3-year certificate", "Certificates of deposit", "0", "NBE"),
                                ("Gold at home", "Physical asset", "0")):
        o.account(name, kind, balance, bank=bank[0] if bank else "")
    b.go("NBE 3-year certificate", "View CDs")
    o.notes["cd_purchase"] = b.submit({
        "name": "NBE 3-year certificate · 22%", "start_date": "1/7", "principal": "100,000",
        "funding_account_id": Choose("CIB Payroll"), "annual_rate": "22", "interest_method": Choose("Simple"),
        "lockup_end_date": "2027-07-01", "maturity_date": "2029-07-01", "payout_frequency": Choose("Monthly"),
        "destination_account_id": Choose("CIB Payroll")}, button="Record CD purchase")
    o.ask("accounts", "Are all six accounts in, with the right balances?", "Manage accounts")
    o.ask("opening", "I typed 1/7. Did the starting balances go in on 1 July?", "Vodafone Cash")
    o.ask("setup", "My accounts are in. What should I do next?")

    # Three months of CIB from the bank's CSV.
    b.go("CIB Payroll", "Import CSV")
    b.submit({}, button="Review statement", files={"file": ("cib-jul-sep.csv", _statement(), "text/csv")})
    b.submit({"map_Date": Choose("Date"), "map_Amount": Choose("Amount"), "map_Counterparty": Choose("Description")},
             button="Preview rows")
    o.notes["review"] = b.page
    # Halfway through he leaves to check something, then comes back to the review from the Overview.
    o.ask("import_waiting", "I left the import half done. Does Lightning remember it?")
    o.notes["import_again"] = b.go("CIB Payroll", "Import CSV")
    b.go("Imported activity needs a decision")
    review = b.page.form("Post ready rows")
    # One decision per name: he answers each imported name once, and every row with that name follows it.
    names = {k.rsplit("_", 1)[1]: v for k, v in review.fields.items()
             if k.startswith("group_counterparty_") and not k.startswith("group_counterparty_choice_")}
    rows_of: dict[str, list[str]] = {}
    for k, group in review.fields.items():
        if k.startswith("group_of_"):
            rows_of.setdefault(group, []).append(k.rsplit("_", 1)[1])
    answers = {}
    for group, raw in names.items():
        decision = IMPORT_DECISIONS[raw]
        if decision is None:
            answers.update({f"skip_{row}": TICK for row in rows_of[group]})
            continue
        party, category, transfer_to, held_for = decision
        answers[f"group_counterparty_{group}"] = party
        if party:
            answers[f"group_counterparty_choice_{group}"] = "new"
        if transfer_to:
            answers[f"group_transfer_account_id_{group}"] = Choose(transfer_to)
        if category:
            answers[f"group_category_{group}"] = Choose(category)
        if held_for:
            answers[f"group_whom_{group}"] = held_for
    o.notes["import_decisions"] = len(names)
    o.notes["import"] = b.submit(answers, button="Post ready rows")

    # THNDR: two shares with their fees, then a money market fund he adds himself.
    o.trade("buy", "11/8", "COMI", units="150", total="12,150", fees="35")
    o.trade("buy", "11/8", "FWRY", units="500", total="4,450", fees="18")
    b.go("Investments", "Financial assets", "Add an investment")  # funds outside the catalogue: Holdings' gear
    o.notes["new_fund"] = b.submit({"name": "Azimut money market fund", "class_code": Choose("Money Market"),
                                   "symbol": "AZMM"}, button="Save")
    o.trade("buy", "1/9", "Azimut", total="3,000", unit_price="120")

    # Gold: the ring he paid for by card, and his grandmother's gold pound.
    screen = o.gold_piece("L'Azurde ring", "Ring", "4.3")
    b.submit({"action": Choose("Record purchase"), "date": "14/9", "total": "18,450", "workmanship": "1,950",
              "cash_account_id": Choose("CIB Payroll"), "notes": "Birthday ring"},
             action=screen.action_after("L'Azurde ring", "/trade"))
    screen = o.gold_piece("Gold pound (from grandma)", "Coin", "8")
    b.submit({"action": Choose("Add existing holding"), "date": "1/7", "total": "29,000", "notes": "Inherited"},
             action=screen.action_after("Gold pound (from grandma)", "/trade"))

    # Cash and Vodafone Cash never reach a statement: he types them in.
    for month, koshary, microbus in (("7", "180", "60"), ("8", "210", "75"), ("9", "165", "90")):
        o.enter("Cash wallet", f"16/{month}", "Koshary El Tahrir", "Eating Out", f"-{koshary}")
        o.enter("Cash wallet", f"12/{month}", "Microbus", "Personal › Transportation", f"-{microbus}")
        o.enter("Vodafone Cash", f"9/{month}", "Vodafone", "Utilities & Bills", "-350")

    for when, typed in (("31/7", {"21K gold": "3,900"}),
                        ("31/8", {"Commercial International": "84.20", "Fawry": "9.10", "21K gold": "4,200"}),
                        ("30/9", {"Commercial International": "86.50", "Fawry": "9.40", "Azimut": "121.30",
                                  "21K gold": "4,650"})):
        o.notes["prices_saved"] = o.prices(when, typed)

    o.ask("position", "How much do I have, and how much of it is really mine?")
    o.ask("moms_money", "How much of Mom's money am I holding?", "Accounts", "Held for others")

    # The plan: a budget from his own spending, an emergency fund, his bills and the car loan.
    b.go("Set a plan for 2026-09")
    b.submit({}, button="Create plan")
    b.go("Cash planning", "Reserves")
    b.submit({"allocated": "20,000"}, action="/reserves/emergency")
    o.ask("emergency_target", "Six months of income is far more than the cash I have. Does Lightning say so?",
          "Cash planning", "Reserves")
    for name in ("ACME Egypt", "Landlord", "WE Internet", "North Cairo Electricity"):
        o.track(name)
    o.add_loan("Car loan", "Toyota Finance", "2,500", "2026-07-05", "24", "60,000")

    o.ask("owe", "What do I owe, and when is the car paid off?", "Loans still to pay")
    o.ask("debt", "Is my debt under control?", "Cash planning", "Loans")
    o.ask("fixed_costs", "How much of my income is already promised?", "Cash planning", "Recurring")
    o.ask("safe", "How much can I spend before payday?", "Cash planning")
    o.ask("free_cash", "Why is my free cash lower than what I have?")
    o.ask("where", "Where did my money go in September?", "Spending")
    o.ask("plan", "Am I sticking to my plan?", "Budget")
    o.ask("investing", "How are my investments doing?", "Investments")
    o.ask("checks", "Is my data right?", "Settings", "Data checks")
    # The sidebar's Search (Ctrl-K opens the same search in the app window); a typo still finds the page.
    b.go("Search")
    b.submit({"q": "lons"}, button="Search")
    b.click("Loans")
    o.answers["search"] = Answer("Where are my loans? (typed as lons)", list(b.trail), b.page)


def _live_the_year(o: Mohab) -> None:
    b = o.b
    _first_evening(o)

    # ============================================================== October: the first live month
    o.on("2026-10-06")
    o.ask("needs_you", "It's the 6th. What needs me today?")
    before = o.answers["needs_you"].figure("What you own")
    o.receive_salary("ACME Egypt")
    o.pay_from_overview("Landlord")
    o.pay_from_overview("Car loan")
    o.ask("paid_from_overview", "Did paying from the Overview move my money?")
    o.notes["what_you_own_before_paying"] = before

    o.on("2026-10-31")
    o.month("2026-10", skip=("ACME Egypt", "Landlord", "Toyota Finance"))   # those three went in from the popups
    o.enter("CIB Payroll", "2026-10-10", "Talabat", "Eating Out", "-480")      # the same order typed twice
    o.delete_newest("CIB Payroll", "Talabat")
    o.enter("CIB Payroll", "2026-10-26", "Carrefour", "Food & Groceries", "-4,600")  # meant 4,060
    o.fix_amount("CIB Payroll", "Carrefour", "-4,060")
    o.enter("CIB Payroll", "2026-10-10", "Cash wallet", "", "-2,000")          # ATM
    o.enter("CIB Payroll", "2026-10-10", "CIB", "Fees & Charges", "-25")      # and its fee
    o.enter("CIB Payroll", "2026-10-15", "Amazon", "Shopping", "1,299")        # August's purchase returned
    o.enter("CIB Payroll", "2026-10-18", "Al Mansour Service", "Personal › Transportation", "-6,500")
    o.to_reserve("CIB Payroll", "Al Mansour Service", "Emergency Fund")                         # paid from the emergency fund

    o.ask("atm", "What did the ATM withdrawal cost me in October?", "Spending")
    o.ask("refund", "Amazon refunded me. Did my spending go down?", "Spending")
    o.ask("emergency", "After the repair, how much is left in my emergency fund?", "Cash planning", "Reserves")
    o.ask("fixed", "Is the Carrefour mistake fixed, and the double Talabat gone?", "CIB Payroll")
    o.ask("reconcile", "Does Lightning match my bank statement?", "CIB Payroll", "Check against bank")
    # The register header is intentionally whole EGP (A16). Reconciliation shows the exact cents.
    statement_balance = money(o.answers["reconcile"].screen.after("Lightning shows"))
    o.answers["reconcile"].screen = b.submit({"date": "2026-10-31", "balance": str(statement_balance)}, button="Check")

    # ============================================================== November: a dividend
    o.on("2026-11-30")
    o.month("2026-11")
    o.trade("dividend", "2026-11-20", "COMI", total="300")
    o.ask("dividend", "Did my shares pay me anything this month?", "Investments", "See them")

    # ============================================================== December: bonus, reimbursement, early pay
    o.on("2026-12-31")
    o.month("2026-12")
    o.enter("CIB Payroll", "2026-12-10", "Uber", "Work › Transportation", "-1,200")
    o.enter("CIB Payroll", "2026-12-22", "ACME Egypt", "Work › Transportation", "1,200")
    o.enter("CIB Payroll", "2026-12-20", "ACME Egypt", "Bonus", "90,000")
    o.enter("CIB Payroll", "2026-12-24", "ACME Egypt", "Salary", "45,000", notes="January salary, paid early")
    o.ask("work", "Did ACME pay back my work Uber?", "Spending")
    o.ask("bonus", "Where did my bonus go?")

    # ============================================================== January: no pay arrives; a yearly bill
    o.on("2027-01-31")
    o.month("2027-01", salary=None)
    o.ask("january_pay", "January's salary came early. Does Lightning know?", "Cash planning", "Recurring")
    o.settle_due_income("ACME Egypt")   # he confirms the 24 December payment it suggests
    o.ask("january_pay_after", "And after I confirm it?", "Cash planning", "Recurring")
    o.ask("january_saved", "January's pay came in December. Does Lightning say I saved too little?")
    o.ask("bonus_budget", "Does the bonus change what I can budget?", "Cash planning", "Reserves")
    b.go("Cash planning", "Reserves")
    b.submit({"name": "Car insurance", "target": "9,000", "due_date": "2027-04-30"}, button="Add reserve")
    o.ask("set_aside", "How much should I put aside each month for the insurance?", "Cash planning")

    # ============================================================== February: the raise
    o.on("2027-02-28")
    o.month("2027-02", salary="50,000")
    o.ask("raise", "Was my raise received, and does the plan know?", "Cash planning", "Recurring")
    o.settle_due_income("ACME Egypt")   # he confirms the 50,000 it suggests
    o.notes["raise_offered"] = b.go("Cash planning", "Recurring").shows("Use 50,000.00 from now on")
    b.submit({}, button="Use 50,000.00 from now on")
    o.ask("raise_after", "Is the plan at 50,000 now?", "Cash planning", "Recurring")
    # Needs you notices the raise is not in his average yet; he keeps his plan and saves the 5,000.
    o.ask("income_up", "My pay went up. What should my plan do with it?", "Choose")
    o.notes["raise_saved"] = b.submit({}, button="Save it")
    o.ask("raise_target", "Did my savings target go up?", "Health")

    # ============================================================== March: Eid, and a phone on installments
    o.on("2027-03-31")
    o.month("2027-03", salary="50,000")
    o.enter("Cash wallet", "2027-03-09", "Eidiya", "Gifts & Donations", "-3,000", notes="For the nephews #Eid")
    o.enter("Cash wallet", "2027-03-10", "Uncle Hassan", "Gifts Received", "1,000", notes="#eid")
    o.add_loan("Phone installments", "valU", "2,000", "2027-04-15", "12", "24,000")
    o.ask("owe_more", "With the phone, what do I owe now?", "Loans still to pay")
    o.ask("eid", "What did Eid cost me?", "Spending")
    o.ask("eid_tag", "And everything I tagged #eid?", "Cash wallet", "#Eid")

    # ============================================================== April: the insurance, and selling COMI
    o.on("2027-04-30")
    o.month("2027-04", salary="50,000")
    screen = b.go("Cash planning", "Reserves")
    b.submit({"allocated": "9,000"}, action=screen.action_after("Car insurance", "/allocate"))
    o.enter("CIB Payroll", "2027-04-25", "Misr Insurance", "Personal › Transportation", "-9,000")
    o.to_reserve("CIB Payroll", "Misr Insurance", "Car insurance")
    o.prices("2027-04-20", {"Commercial International": "95"})
    o.trade("sell", "2027-04-20", "COMI", units="75", total="7,100", fees="25")
    o.enter("THNDR", "2027-04-21", "CIB Payroll", "", "-7,100")
    o.ask("sale", "What did I make on the COMI I sold?", "Investments", "Commercial International Bank")
    # The phone installments started this month, on top of the car: the plan still says 2,500 for loans.
    o.ask("loans_planned", "Does my plan cover both loans?")
    b.click("Change the plan")
    o.notes["loans_replanned"] = o.plan_category("Loan payments", "4,500")
    o.ask("loans_planned_after", "And now?")
    o.ask("safe_keeps_saving", "Does Safe to spend leave what I mean to save?", "Cash planning")
    o.ask("insurance", "Is the insurance paid from its goal?", "Cash planning", "Reserves")

    # ============================================================== May and June: the rent goes up
    o.on("2027-05-31")
    o.month("2027-05", salary="50,000")
    # A laptop by the end of June: Needs you says the plan cannot get there in time, and that his free cash
    # can; he sets the 60,000 aside.
    b.go("Cash planning", "Reserves")
    b.submit({"name": "New laptop", "target": "60,000", "due_date": "2027-06-30"}, button="Add reserve")
    o.ask("laptop", "Can I have a 60,000 laptop by the end of June?")
    screen = b.go("Cash planning", "Reserves")
    o.notes["laptop_set_aside"] = b.submit({"allocated": "60,000"}, action=screen.action_after("New laptop", "/allocate"))
    o.ask("laptop_after", "And once the money is set aside?")
    o.on("2027-06-30")
    o.month("2027-06", salary="50,000", rent="13,200")
    o.ask("rent", "My rent went up to 13,200. Does the plan know?", "Cash planning", "Recurring")
    if b.page.shows("Use 13,200.00 from now on"):
        b.submit({}, button="Use 13,200.00 from now on")
    o.ask("rent_after", "And now?", "Cash planning", "Recurring")
    o.ask("rent_planned", "Does my budget know the rent went up?")
    b.click("Change the plan")
    o.notes["rent_replanned"] = o.plan_category("Housing & Rent", "13,200")
    o.ask("rent_planned_after", "And now?")

    # ============================================================== July and August: Sahel, and a new job
    o.on("2027-07-31")
    o.month("2027-07", salary="50,000", rent="13,200")
    # The new model is out in the autumn: he lets the laptop goal go and its 60,000 is free again.
    o.ask("laptop_late", "The laptop's date has passed. What now?")
    screen = b.go("Cash planning", "Reserves")
    o.notes["laptop_done"] = b.submit({}, action=screen.action_after("New laptop", "/complete"))
    b.go("Cash planning", "Reserves")
    b.submit({"name": "Sahel trip", "target": "15,000", "due_date": "2027-08-15", "allocated": "15,000"},
             button="Add reserve")
    o.on("2027-08-31")
    o.month("2027-08", salary="50,000", rent="13,200")
    o.enter("CIB Payroll", "2027-08-12", "Hacienda Bay", "Personal › Travel", "-14,200")
    o.to_reserve("CIB Payroll", "Hacienda Bay", "Sahel trip")
    o.ask("trip", "How much is left from the Sahel money?", "Cash planning", "Reserves")
    o.enter("CIB Payroll", "2027-08-31", "ACME Egypt", "Bonus", "30,000", notes="End of service")
    o.ask("end_of_service", "Does my end-of-service money change what I can budget?", "Cash planning", "Reserves")
    b.go("Cash planning", "Recurring", "ACME Egypt")
    b.submit({}, button="Stop")
    b.go("Cash planning", "Recurring", "Add recurring item")
    b.open(b.page.path.replace("kind=BILL", "kind=INCOME"))  # choosing Income reloads the form with income categories
    b.submit({"name": "Valeo", "amount": "55,000", "start_date": "2027-10-01",
              "account_id": Choose("CIB Payroll"), "category_id": Choose("Salary"), "counterparty": "Valeo"},
             button="Add")

    # ============================================================== September: between jobs
    o.on("2027-09-30")
    o.month("2027-09", salary=None, rent="13,200")
    o.ask("next_pay", "I'm between jobs. When is my next pay?", "Cash planning")
    o.ask("last", "How long could my emergency fund carry me?", "Cash planning", "Reserves")
    # He would rather count it in months of what he spends; Reserves links to the setting.
    b.go("Cash planning", "Reserves", "Change in Settings")
    b.submit({"emergency_basis": "spending"}, button="Save budget settings")
    o.ask("last_in_spending", "And in months of what I spend?", "Cash planning", "Reserves")
    b.go("Cash planning", "Reserves", "Change in Settings")
    b.submit({"emergency_basis": "income"}, button="Save budget settings")

    # ============================================================== the year
    for key, question, page in (("year", "How did my year go?", ""),
                                ("year_spending", "Where did the year's money go?", "Spending"),
                                ("year_investing", "How did my investments do this year?", "Investments")):
        screen = o.period(page, "2026-10-01", "2027-09-30")
        o.answers[key] = Answer(question, list(b.trail) + ["Custom 2026-10-01 to 2027-09-30"], screen)
    o.ask("year_checks", "Is everything still right after a year?", "Settings", "Data checks")
    _the_feedback_round(o)
    _exercise_cash_ownership(o)
    _a_rule_for_vodafone(o)


def _a_rule_for_vodafone(o: Mohab) -> None:
    """Rules with conditions (Upcoming projects #5): a phone bought at the Vodafone shop is Shopping, while
    the monthly 350 stays a bill. He leaves the category empty and the rule decides on saving."""
    o.on("2027-09-30")
    b = o.b
    b.go("Settings", "Rules", "Add rule")
    o.notes["rule_saved"] = b.submit({"counterparty": "Vodafone", "amount_op": Choose("Between"), "amount": "1,000",
                                      "amount_to": "50,000", "category_id": Choose("Shopping")}, button="Add rule")
    o.enter("CIB Payroll", "2027-09-30", "Vodafone", "", "-350")
    o.enter("CIB Payroll", "2027-09-30", "Vodafone", "", "-12,000", notes="new phone")
    o.ask("rule_filed", "Did the rule file the phone as Shopping and keep the bill?", "CIB Payroll")


def _exercise_cash_ownership(o: Mohab) -> None:
    """Use the account workflow to assign part of the cash to Mom, then record an expense she paid."""
    o.on("2027-09-30")
    b = o.b
    account = b.go("CIB Payroll")
    gross_before = money(account.after("In this account"))
    b.click("Change ownership")
    assignment = b.submit({"mode": Choose("Change who owns this money"), "date": "2027-09-30", "amount": "500",
                           "from_owner_id": Choose("You"), "to_owner_id": Choose("Mom")}, button="Save")
    gross_after_assignment = money(b.go("CIB Payroll").after("In this account"))

    b.click("Change ownership")
    external_expense = b.submit({"mode": Choose("Someone paid an expense for you"), "date": "2027-09-30",
                                 "amount": "400", "from_owner_id": Choose("You"),
                                 "to_owner_id": Choose("Mom"), "category_id": Choose("Food & Groceries"),
                                 "notes": "Mom paid for groceries"}, button="Save")
    gross_after_expense = money(b.go("CIB Payroll").after("In this account"))
    o.notes["cash_ownership"] = {"assignment": assignment, "expense": external_expense,
                                 "gross_before": gross_before,
                                 "gross_after_assignment": gross_after_assignment,
                                 "gross_after_expense": gross_after_expense}


def _year_statement() -> bytes:
    """A year of Vodafone Cash as the wallet exports it: 300 rows, seven columns, debit and credit apart."""
    shops = ("CARREFOUR MAADI", "TALABAT", "SEOUDI MARKET", "UBER", "VODAFONE", "WE INTERNET", "PHARMACY 19011",
             "SHELL FUEL", "AMAZON.EG", "INSTAPAY")
    rows, balance = [], D("50000")
    for n in range(300):
        day = dates.parse_date("2026-10-01") + timedelta(days=n * 365 // 300)
        topup = n % 25 == 0
        amount = D("5000") if topup else D((n * 37) % 900 + 50)
        balance += amount if topup else -amount
        rows.append(f"{day:%d/%m/%Y},{day:%d/%m/%Y},{'TOP UP FROM CIB' if topup else shops[n % 10]},VF{26000000 + n},"
                    f"{'' if topup else amount},{amount if topup else ''},{balance}")
    return ("Date,Value date,Description,Reference,Debit,Credit,Balance\n" + "\n".join(rows) + "\n").encode()


def _the_feedback_round(o: Mohab) -> None:
    """30 September 2027, after the year's answers are read: the pain points users reported in
    user feedback/user-feedback-batch-001.md, walked through by Mohab. Nothing here changes an answer above."""
    b = o.b
    # Reports: All time, a past month, and what is a snapshot of today.
    b.go()
    o.answers["all_time"] = Answer("What is my savings rate over all time?", ["/", "All time"],
                                   b.submit({}, button="All time"))
    o.answers["past_month"] = Answer("What did October 2026 look like?", ["/", "Custom 2026-10-01 to 2026-10-31"],
                                     o.period("", "2026-10-01", "2026-10-31"))
    o.on("2027-09-30")   # opening Lightning again forgets the period he picked

    # Categories, the investment plan, and editing several rows at once.
    # Looks recurring offers bills, not his groceries or the certificate's interest; Mom's gift he hides.
    o.ask("looks_recurring", "What does Lightning think repeats?", "Cash planning", "Recurring")
    o.notes["not_recurring"] = b.submit({}, action=b.page.action_after("<b>Mom</b>", "not-recurring"))
    o.ask("categories", "Which categories are income, which are spending, and which repeat?", "Settings", "Categories")
    o.ask("invest_monthly", "Can I keep a goal of investing 3,000 every month?", "Investments", "Planner")
    o.ask("bulk", "I selected six Talabat rows. Can I change their category together?", "CIB Payroll")
    # He types Talabat in CIB Payroll's search box, ticks every row and gives them one category.
    found = b.open(f"{b.go('CIB Payroll').path.split('?')[0]}?q=Talabat")
    talabat = re.findall(r'class="transaction-select"[^>]*value="(\d+)"', found.html) or \
        re.findall(r'value="(\d+)"[^>]*class="transaction-select"', found.html)
    o.notes["bulk_rows"] = len(talabat)
    o.notes["bulk_done"] = b.submit({"txn_ids": talabat, "category_id": Choose("Food & Groceries"),
                                     "back": found.path}, action="/transactions/bulk-category")
    # Talabat is food now, so Food runs over its plan every month; Needs you offers room from Shopping.
    o.ask("food_over", "Food is over its plan every month now. What can I do?")
    o.notes["move_popup"] = b.click("Move it")
    o.notes["moved"] = b.submit({}, button="Move it")
    o.ask("food_over_after", "And now?")
    o.ask("fund_value", "THNDR shows the fund's value, not its unit price. Can I type that?",
          "Investments", "Prices")

    # His share of the family flat: he only knows what it is worth.
    o.account("Family flat (my share)", "Other", "400,000", when="2027-09-30")
    o.ask("flat", "Is my share of the flat in my investments?", "Investments")
    o.ask("flat_jump", "My net worth jumped this month. Did I really gain 400,000?")
    o.notes["flat_page"] = b.go("Family flat (my share)")

    # What does the bank say? He counts his wallet 30 short; CIB's app shows 5,000 less than Lightning.
    wallet = money(b.go("Cash wallet", "Check against bank").after("Lightning shows"))
    o.notes["wallet_check"] = b.submit({"date": "2027-09-30", "balance": str(wallet - 30)}, button="Check")
    o.notes["wallet_adjusted"] = b.submit({}, button="Post adjustment")
    b.go("Cash wallet", "Check against bank")
    o.notes["wallet_rechecked"] = b.submit({"date": "2027-09-30", "balance": str(wallet - 30)}, button="Check")
    cib = money(b.go("CIB Payroll", "Check against bank").after("Lightning shows"))
    o.notes["cib_check"] = b.submit({"date": "2027-09-30", "balance": str(cib - 5000)}, button="Check")

    # A year of Vodafone Cash in one big file, with a mistake in one row.
    b.go("Vodafone Cash", "Import CSV")
    o.notes["upload_form"] = b.page
    b.submit({}, button="Review statement", files={"file": ("vodafone-year.csv", _year_statement(), "text/csv")})
    o.notes["big_review"] = b.submit({"amount_model": "SEPARATE", "map_Date": Choose("Date"), "map_Inflow": Choose("Credit"),
                                      "map_Outflow": Choose("Debit"), "map_Counterparty": Choose("Description"),
                                      "map_Reference": Choose("Reference")}, button="Preview rows")
    first = min(int(k.rsplit("_", 1)[1]) for k in b.page.form("Post ready rows").fields if k.startswith("notes_"))
    o.notes["import_error"] = b.submit({f"date_{first}": "31/31/2026"}, button="Post ready rows")


@pytest.fixture(scope="module")
def mohab(tmp_path_factory):
    pinned = os.environ.get("LIGHTNING_TODAY")
    with pytest.MonkeyPatch.context() as patch:
        # Records are stamped with the day Mohab made them, not the day the test runs.
        patch.setattr(dates, "_local_now", lambda: datetime.combine(dates.today(), time(12), timezone.utc))
        c = build(tmp_path_factory.mktemp("mohab") / "mohab.db")
        try:
            person = Mohab(c)
            _live_the_year(person)
            yield person
        finally:
            c.db.close()
            os.environ["LIGHTNING_TODAY"] = pinned or ""


# ------------------------------------------------------------------ what Mohab found, question by question
# Each test: the route from the Overview, then what the page told him.

def route(mohab, key):
    """The pages he went through, without the period each one remembered in its address."""
    return [step.split("?")[0] for step in mohab.answers[key].trail]


def test_an_empty_lightning_says_where_to_start(mohab):
    answer = mohab.answers["start"]
    assert route(mohab, "start") == ["/"]
    assert answer.shows("Where do you keep your money?", "Bank account", "Certificates", "Brokerage", "Gold and other things")


def test_six_accounts_with_their_balances(mohab):
    answer = mohab.answers["accounts"]
    assert route(mohab, "accounts") == ["/", "/accounts"]
    assert answer.figure("Total balance") == D("141700")
    for name in ("CIB Payroll", "Cash wallet", "Vodafone Cash", "THNDR", "NBE 3-year certificate", "Gold at home"):
        assert answer.shows(name)


def test_the_overview_says_what_to_set_up_next_and_then_gets_out_of_the_way(mohab):
    setup = mohab.answers["setup"]
    assert route(mohab, "setup") == ["/"]
    # Accounts are in; moving money into the NBE certificate is not history yet (review 2026-10-04: the
    # step ticked on the CD purchase alone). History, salary, the emergency fund and the budget are next.
    assert setup.shows("Get set up", "1 of 5 done", "Bring in your history", "Add your salary and bills",
                       "Set an emergency fund", "Make a budget")
    # With the CIB statement half reviewed, the step points back to it instead of ticking.
    assert mohab.answers["import_waiting"].shows("Bring in your history", "cib-jul-sep.csv is waiting for your review",
                                                 "Finish the import")
    assert not mohab.answers["needs_you"].shows("Get set up")  # all five done by October


def test_dates_typed_as_day_and_month_become_full_dates(mohab):
    assert mohab.answers["opening"].shows("2026-07-01")


def test_the_import_posts_what_he_decided_and_skips_the_card_payment(mohab):
    assert mohab.notes["import"].shows("42 posted · 1 skipped · 0 duplicates")


def test_what_he_owns_leaves_out_moms_money(mohab):
    position = mohab.answers["position"]
    assert route(mohab, "position") == ["/"]
    assert position.shows("Excludes money held for others")
    assert position.figure("What you own Excludes money held for others") == D("250565")  # reports show whole pounds
    assert position.figure("Gold") == D("57195")  # 8 g + 4.3 g of 21K at 4,650
    moms = mohab.answers["moms_money"]
    assert route(mohab, "moms_money") == ["/", "/accounts", "/money-from-others"]
    assert moms.shows("Mom CIB Payroll 10,000.00")


def test_what_he_owes_and_when_the_car_is_paid_off(mohab):
    answer = mohab.answers["owe"]
    assert route(mohab, "owe") == ["/", "/plan/loans"]
    assert answer.figure("Loans still to pay") == D("52500")
    assert answer.shows("Paid off on 2028-06-05", "3 of 24 payments made")


def test_safe_to_spend_until_payday(mohab):
    answer = mohab.answers["safe"]
    assert route(mohab, "safe") == ["/", "/plan"]
    # 20,000 of a 270,000 emergency target: the top-up the budget asks for (250,000 over 24 months,
    # 10,417) is kept back too, as Saving for goals is (owner request 2026-10-05: one plan).
    assert answer.figure("Safe to spend until 2026-10-01") == D("40937")
    assert answer.shows("Budget left to spend −1,309 Emergency fund top-up −10,417 Safe to spend 40,937")


def test_free_cash_shows_what_was_taken_off(mohab):
    answer = mohab.answers["free_cash"]
    assert answer.shows("Cash you own 72,663 Reserves −20,000 Emergency fund 20,000")
    assert answer.figure("Free cash After reserves and bills due Cash planning") == D("52663")


def test_september_spending_by_category(mohab):
    answer = mohab.answers["where"]
    assert route(mohab, "where") == ["/", "/birdview/expenses"]
    assert answer.shows("Money out 23,390 EGP Against 2026-08 −1,364", "Housing & Rent 12,000 · 51%")
    # Rent did not change and food moved by 5 EGP: both read 0%, never "+0%" or "−0%".
    assert answer.shows("Housing & Rent 12,000 12,000 0%", "Food & Groceries 4,666 4,671 0%")


def test_the_budget_says_what_is_over(mohab):
    answer = mohab.answers["plan"]
    assert route(mohab, "plan") == ["/", "/budget"]
    assert answer.shows("Categories over plan 2 Transportation, Food & Groceries")
    # Each "80 of 67 · 13 over" adds up as he reads it: plans built from his spending are whole EGP.
    for spent, planned, gap, word in re.findall(r"([\d,]+) of ([\d,]+) ([\d,]+) (over|left)", answer.screen.text):
        spent, planned, gap = (money(x) for x in (spent, planned, gap))
        assert gap == (spent - planned if word == "over" else planned - spent), (spent, planned, gap, word)


def test_investments_lead_with_the_periods_result(mohab):
    answer = mohab.answers["investing"]
    assert route(mohab, "investing") == ["/", "/investments"]
    # 5,673 from prices and the dividend, plus the certificate's 1,833 interest paid into CIB
    assert answer.shows("Net gain or loss 2026-09 +7,506")


def test_data_checks_pass_after_setup(mohab):
    assert route(mohab, "checks") == ["/", "/settings", "/checks"]
    assert mohab.answers["checks"].shows("Passed 8 Needs attention 0")


def test_adding_an_investment_confirms_it_by_name(mohab):
    message = mohab.notes["new_fund"].text
    assert "Azimut money market fund" in message and "FND:AZMM" not in message


def test_needs_you_lists_the_bills_that_are_due(mohab):
    answer = mohab.answers["needs_you"]
    assert answer.shows("Bill due: Landlord", "Loan payment due: Car loan")


def test_paying_from_the_overview_moves_net_worth_only_by_the_salary(mohab):
    before = mohab.answers["needs_you"].figure("Net worth Excludes money held for others")
    after = mohab.answers["paid_from_overview"].figure("Net worth Excludes money held for others")
    assert after - before == D("45000")  # rent and the loan were already owed
    assert mohab.answers["paid_from_overview"].shows("Nothing needs you today")


def test_a_mistake_is_fixed_in_place_and_a_double_entry_deleted(mohab):
    register = mohab.answers["fixed"]
    assert register.shows("Carrefour Food & Groceries 2026-10-26 −4,060")
    assert "−4,600" not in register.screen.text
    assert register.screen.text.count("Talabat Eating Out 2026-10-10") == 1


def test_the_atm_fee_is_only_inside_others(mohab):
    # Four, then Other (guideline 3.6): the fees (the monthly 15 and the ATM's 25) are inside Other, with
    # Eating Out 670, Utilities & Bills 1,480 and Gifts & Donations 2,000.
    assert mohab.answers["atm"].shows("Other 4,190")


def test_a_refund_lowers_money_out(mohab):
    assert mohab.answers["refund"].shows("Money out 32,701 EGP Against 2026-09 +9,311")


def test_where_it_went_adds_up_to_money_out(mohab):
    # Fixed 2026-10-04: the refund-only category is its own row, and shares are of Money out.
    text = mohab.answers["refund"].screen.text
    table = text[text.find("Show the numbers Category Money out Share"):text.find("Is this period unusual?")]
    body, footer = table[:table.rfind(" Money out ")], table[table.rfind(" Money out "):]
    rows = re.findall(r"([−+]?[\d,]+(?:\.\d\d)?) [−]?[\d.]+%", body)
    assert sum(money(m) for m in rows) == D("32701") == money(footer)
    assert "Refunds took 1,299 off money out: Shopping" in text
    assert "Housing & Rent 12,000 · 37%" in text      # 12,000 of 32,701, not of 34,000


def test_a_repair_paid_from_the_emergency_fund(mohab):
    answer = mohab.answers["emergency"]
    assert route(mohab, "emergency") == ["/", "/plan", "/plan/reserves"]
    assert answer.shows("13,500 of 270,000")


def test_checking_october_against_the_bank_balance(mohab):
    answer = mohab.answers["reconcile"]
    assert route(mohab, "reconcile") == ["/", "/accounts/1", "/accounts/1/reconcile"]
    assert answer.figure("Difference") == 0
    assert answer.shows("It matches")   # one typed balance, no line-by-line clearing


def test_a_dividend_is_listed_under_dividends_collected(mohab):
    assert route(mohab, "dividend")[:2] == ["/", "/investments"]
    assert mohab.answers["dividend"].shows("2026-11-20", "Commercial International Bank")


def test_the_dividends_list_says_how_much(mohab):
    assert mohab.answers["dividend"].shows("300.00")


def test_a_reimbursed_work_expense_leaves_no_spending(mohab):
    text = mohab.answers["work"].screen.text
    assert mohab.answers["work"].shows("Money out 23,415 EGP Against 2026-11 0 · 0%")  # the same as November
    assert "Work" not in text[text.find("Where did it go?"):text.find("Is this period unusual?")]


def test_the_bonus_shows_in_money_in(mohab):
    answer = mohab.answers["bonus"]
    assert answer.shows("Bonus 90,000")


def test_average_monthly_income_ignores_the_bonus_and_counts_early_pay_when_due(mohab):
    assert mohab.answers["bonus_budget"].figure("Average monthly income") == D("45000")


def test_an_early_payday_is_suggested_and_settles_once_confirmed(mohab):
    assert re.search(r"ACME Egypt Income [^+]* 1 due", mohab.answers["january_pay"].screen.text)
    assert not re.search(r"ACME Egypt Income [^+]* \d+ due", mohab.answers["january_pay_after"].screen.text)


def test_a_yearly_bill_is_spread_over_the_months_left(mohab):
    answer = mohab.answers["set_aside"]
    assert route(mohab, "set_aside") == ["/", "/plan"]
    assert answer.shows("Saving for goals −2,250")


def test_a_raise_waits_for_mohab_to_confirm_it(mohab):
    # A different amount is suggested, never matched on its own: he chooses it.
    assert re.search(r"ACME Egypt Income [^+]* 1 due", mohab.answers["raise"].screen.text)


def test_recurring_offers_the_raise_for_later_months(mohab):
    assert mohab.notes["raise_offered"]


def test_after_the_raise_the_plan_is_at_50000(mohab):
    assert re.search(r"ACME Egypt Income [^+]*\+50,000\.00", mohab.answers["raise_after"].screen.text)


def test_an_early_paid_january_is_not_a_month_that_saved_too_little(mohab):
    # January's pay came on 24 December: the Overview says what happened, and Needs you does not call it
    # a month that missed the savings target (less than half the usual income came in).
    answer = mohab.answers["january_saved"]
    assert answer.shows("Savings rate 2027-01 — 21,582 more went out than the 1,833 that came in")
    assert not answer.shows("saved less than your target")


def test_financial_health_says_the_early_paid_january_in_words(mohab):
    # As the Overview does: a rate of −1,177% says nothing when the pay landed in December.
    answer = mohab.answers["raise_target"]
    assert answer.shows("Savings rate — Below your limit 21,582 more went out than the 1,833 that came in 2027-01")
    assert not answer.shows("1177")


def test_needs_you_offers_the_raise_to_the_plan(mohab):
    # Recurring says 50,000 and his average still 45,000: plan with it, save the difference, or wait.
    offer = mohab.answers["income_up"]
    assert route(mohab, "income_up") == ["/", "/budget/raise"]
    assert offer.shows("Recurring expects 50,000 EGP a month; your average is 45,000",
                       "What should the plan do with 5,000 EGP more a month?",
                       "Most you can plan becomes 36,313 EGP; your 20% target stays",
                       "Keep today's plan and raise your savings target to 28.0%")
    # 20% of 45,000 is 9,000; with the 5,000 raise he keeps 14,000 of 50,000.
    assert mohab.notes["raise_saved"].shows("Savings target raised to 28.0%: the plan stays and saves the difference. "
                                            "Most you can plan this month is now 31,313; this month's plan fits.")
    assert mohab.answers["raise_target"].shows("Your limit At least 28.0%")


def test_a_plan_below_both_loans_is_named_and_fixed(mohab):
    answer = mohab.answers["loans_planned"]
    assert answer.shows("Loan payments is planned below its bills Planned 2,500 EGP; bills and loan payments "
                        "scheduled this month come to 4,500. Change the plan")
    assert mohab.notes["loans_replanned"].shows("Budget saved.")
    assert not mohab.answers["loans_planned_after"].shows("planned below its bills")


def test_safe_to_spend_keeps_the_rest_of_the_savings_target(mohab):
    # His 28% target is 13,533 of 48,333; the emergency top-up already holds back 11,521 of it.
    assert route(mohab, "safe_keeps_saving") == ["/", "/plan"]
    assert mohab.answers["safe_keeps_saving"].shows(
        "Free cash 313,205 Emergency fund top-up −11,521 Rest of savings target −2,013 Safe to spend 299,672")


def test_a_goal_the_plan_cannot_reach_says_when_and_what_else_works(mohab):
    answer = mohab.answers["laptop"]
    assert answer.shows("New laptop will not be ready by its date Due 2027-06-30 · it needs 30,000 EGP a month and "
                        "your plan leaves 23,301 for it. Setting aside 23,301 a month, it is ready in July 2027. "
                        "Set aside 60,000 of your 339,623 free cash now, or give it a later date.")
    assert mohab.notes["laptop_set_aside"].shows("Updated cash assigned to New laptop.")
    assert not mohab.answers["laptop_after"].shows("New laptop will not be ready")
    assert mohab.answers["laptop_late"].shows("New laptop is past its date Due 2027-06-30 · 60,000 EGP still set aside.")
    assert mohab.notes["laptop_done"].shows("Completed New laptop; its assigned cash is free again.")


def test_installments_are_owed_like_a_loan(mohab):
    answer = mohab.answers["owe_more"]
    assert answer.figure("Loans still to pay") == D("61500")
    assert answer.shows("Phone installments", "Last payment 2028-03-15")


def test_eid_gifts_given_are_spending_and_gifts_received_are_not(mohab):
    assert mohab.answers["eid"].shows("Money out 26,415 EGP", "Gifts & Donations 5,000 · 19%")


def test_a_tag_in_a_note_gathers_eid(mohab):
    """He wrote #Eid and #eid in two notes; the tag's link opens both, with their money in and out."""
    assert route(mohab, "eid_tag")[-1] == "/transactions"
    assert mohab.answers["eid_tag"].shows("Tagged #eid · 2 transactions · Money in 1,000.00 · Money out 3,000.00",
                                         "For the nephews")


def test_a_sale_shows_its_gain_after_fees(mohab):
    answer = mohab.answers["sale"]
    assert route(mohab, "sale")[:2] == ["/", "/investments"]   # then the holding itself
    assert answer.shows("Gain from sales +1,025", "Total return +2,375")  # 7,100 − 75/150 of 12,150


def test_the_insurance_is_paid_from_its_goal(mohab):
    assert mohab.answers["insurance"].shows("Car insurance", "9,000 spent · 0 still set aside")


def test_the_rent_rise_is_offered_and_taken(mohab):
    assert mohab.answers["rent"].shows("Last paid 13,200.00 Use 13,200.00 from now on")
    assert mohab.answers["rent_after"].shows("Landlord Bill · Housing & Rent 13,200.00")


def test_the_rent_rise_reaches_the_budget(mohab):
    assert mohab.answers["rent_planned"].shows("Housing & Rent is planned below its bills Planned 12,000 EGP; "
                                               "bills and loan payments scheduled this month come to 13,200.")
    assert mohab.notes["rent_replanned"].shows("Budget saved.")
    assert not mohab.answers["rent_planned_after"].shows("planned below its bills")


def test_the_trip_goal_keeps_what_was_not_spent(mohab):
    text = mohab.answers["trip"].screen.text
    assert re.search(r"Sahel trip .*?800\b", text)


def test_end_of_service_is_not_monthly_pay(mohab):
    assert mohab.answers["end_of_service"].figure("Average monthly income") == D("50000")


def test_between_jobs_the_next_pay_is_the_new_employer(mohab):
    answer = mohab.answers["next_pay"]
    assert answer.shows("Safe to spend until 2027-10-01", "Valeo 2027-10-01 · Income +55,000")


def test_looks_recurring_leaves_spending_and_interest_to_the_budget_and_forecast(mohab):
    answer = mohab.answers["looks_recurring"]
    assert route(mohab, "looks_recurring") == ["/", "/plan", "/plan/recurring"]
    offered = re.findall(r"<b>([^<]+)</b><small class=\"muted\">\d+ months", answer.screen.html)
    assert "Mom" in offered and not {"Carrefour", "Talabat", "Seoudi", "Koshary El Tahrir", "NBE"} & set(offered)
    assert mohab.notes["not_recurring"].shows("Mom will not be suggested again.")
    assert not re.search(r"<b>Mom</b><small", mohab.notes["not_recurring"].html)


def test_search_finds_a_page_through_a_typo(mohab):
    assert route(mohab, "search") == ["/", "/search", "/plan/loans"]  # the typed search is a form, not a page in the trail
    assert mohab.answers["search"].shows("Loans still to pay")


def test_is_my_debt_under_control(mohab):
    """Cash planning › Loans leads with three ratios, each with the two amounts it divides, and those
    amounts are the Overview's own (2026-09-30: the car loan has 21 payments of 2,500 left)."""
    debt, overview = mohab.answers["debt"], mohab.answers["free_cash"]
    assert route(mohab, "debt") == ["/", "/plan", "/plan/loans"]
    assert [overview.figure(x) for x in ("What you owe", "Net worth", "Cash you own")] == [D("-52500"), D("198065"), D("72663")]
    assert debt.shows("Debt to net worth 2026-09-30 26.5 % 52,500 owed against 198,065 net worth",
                      "Debt to cash 2026-09-30 72.3 % 52,500 owed against 72,663 cash you own",
                      "Loan payments to income 2026-09-30 5.6 % 2,500 a month of 45,000 income")


def test_how_much_of_my_income_is_already_promised(mohab):
    """Cash planning › Recurring: bills and subscriptions a month plus the car loan's 2,500, of income."""
    fixed = mohab.answers["fixed_costs"]
    assert route(mohab, "fixed_costs") == ["/", "/plan", "/plan/recurring"]
    assert fixed.figure("Bills and subscriptions") + D("2500") == D("15630")
    assert fixed.shows("Fixed costs to income 2026-09-30 34.7 % 15,630 a month of 45,000 income · bills, subscriptions and loans")


def test_the_emergency_fund_in_months(mohab):
    answer = mohab.answers["last"]
    assert answer.shows("Emergency fund covers 0.3 months")


def test_the_emergency_fund_in_months_of_spending(mohab):
    answer = mohab.answers["last_in_spending"]
    # 13,500 left in the fund after the repair, over June to August's spending (no one-offs, no investing)
    assert answer.shows("Emergency fund covers 0.4 months", "Of average monthly spending. The aim is six.",
                        "2027-06 to 2027-08 · 3 months with spending", "Counted in months of spending")
    assert answer.figure("Average monthly spending") == D("31348")


def test_the_year_on_the_overview(mohab):
    answer = mohab.answers["year"]
    assert answer.figure("Savings rate 2026-10-01 to 2027-09-30") == D("50.5")
    assert answer.figure("Change in net worth 2026-10-01 to 2027-09-30") == D("341284")
    assert answer.figure("Loans still to pay") == D("34500")


def test_the_years_spending(mohab):
    assert mohab.answers["year_spending"].shows("Money out 333,266 EGP", "Housing & Rent 148,800 · 45%")


def test_the_years_investments(mohab):
    # 1,025 from the sale + 225 price change + 300 dividends + 12 × 1,833.33 of certificate interest
    assert mohab.answers["year_investing"].shows("Net gain or loss 2026-10-01 to 2027-09-30 +23,550")
    # The interest lands on CIB Payroll from NBE, the certificate's bank, and is still the certificate's return.
    assert mohab.answers["flat"].shows("NBE 3-year certificate 1 certificate 100,000 100,000 100,000 100,000 17.5% 0 0.0% +24.6%")


def test_data_checks_pass_after_a_year(mohab):
    assert mohab.answers["year_checks"].shows("Passed 8 Needs attention 0")


def test_cash_ownership_and_external_expense_keep_the_account_total(mohab):
    flow = mohab.notes["cash_ownership"]
    assert flow["assignment"].shows("Ownership change")
    assert flow["expense"].shows("Expense paid for you", "Food & Groceries", "Mom")
    assert flow["gross_before"] == flow["gross_after_assignment"] == flow["gross_after_expense"]


# ------------------------------------------------------------------ what users reported (user feedback, batch 001)
# The pain points from "user feedback/user-feedback-batch-001.md", met by Mohab on his way through the year.
# Fixed points are checked like any other answer; each named gap has a direct screen assertion.

def _review_choices(screen: Screen, prefix: str) -> list[str]:
    """The choices one name's picker offers (every name offers the same)."""
    return [label for _, label in screen.form("Post ready rows").options[f"group_{prefix}0"]]


def test_leaving_an_import_keeps_it_waiting_on_the_overview(mohab):
    assert route(mohab, "import_waiting") == ["/"]
    assert mohab.answers["import_waiting"].shows("Imported activity needs a decision", "cib-jul-sep.csv")


def test_import_csv_leads_back_to_the_waiting_import(mohab):
    assert mohab.notes["import_again"].shows("cib-jul-sep.csv is waiting for you", "Continue the review", "Discard it")


def test_one_decision_per_name_in_the_import(mohab):
    # 43 rows from three months of CIB are 17 names: he answers 17 times, not 43.
    assert mohab.notes["import_decisions"] == 17


def test_thndr_can_be_where_a_transfer_went(mohab):
    assert "THNDR" in _review_choices(mohab.notes["review"], "transfer_account_id_")


def test_an_unanswered_category_starts_empty(mohab):
    # Nothing to delete before choosing: an empty "Choose a category"; "Uncategorized" is still a choice.
    form = mohab.notes["review"].form("Post ready rows")
    categories = {name: value for name, value in form.fields.items() if name.startswith("group_category_")}
    assert categories and all(value == "" for value in categories.values())
    assert "Uncategorized" in _review_choices(mohab.notes["review"], "category_")


def test_category_choices_sit_under_their_group(mohab):
    # Guideline 3.6: the L1 as a header with its categories under it, never "L1 › L2".
    html = mohab.notes["review"].html
    select = html[html.index('name="group_category_'):]
    select = select[:select.index("</select>")]
    groups = dict(re.findall(r'<optgroup label="([^"]+)">(.*?)</optgroup>', select, re.S))
    assert ">Transportation<" in groups["Personal"] and ">Transportation<" in groups["Work"]
    assert "›" not in select


def test_a_saved_change_says_so_in_a_status_message(mohab):
    assert re.search(r'class="flash"[^>]*role="status"', mohab.notes["prices_saved"].html)


def test_certificate_keeps_its_purchase_value_without_month_end_price_prompts(mohab):
    certificate = next(asset for asset in mohab.c.assets.investments(active_only=True)
                       if asset.name == "NBE 3-year certificate · 22%")
    screen = mohab.b.go("Investments", "Prices")
    assert certificate.name in screen.text and f'name="p_{certificate.id}"' not in screen.html
    assert all(row["asset_id"] != certificate.id for row in mohab.c.reevaluations.pending_prices())


def test_an_emergency_target_above_his_cash_is_flagged(mohab):
    assert mohab.answers["emergency_target"].shows("more than the cash you own")


def test_old_prices_are_flagged_and_fresh_ones_are_not(mohab):
    # Honest numbers: a year on, his fund, shares and gold still carry September 2026 prices.
    assert mohab.answers["all_time"].shows("Prices are out of date", "Update prices")
    assert not mohab.answers["position"].shows("Prices are out of date")   # priced the same evening


def test_the_savings_rate_for_all_time(mohab):
    assert mohab.answers["all_time"].figure("Savings rate All time") == D("50.3")


def test_the_overview_says_which_parts_follow_the_period(mohab):
    answer = mohab.answers["past_month"]
    assert answer.shows("Cash flow 2026-10-01 to 2026-10-31", "Investments 2026-10-01 to 2026-10-31",
                        "Month by month 2026-07 to today")


def test_your_position_stays_today_whatever_the_period(mohab):
    assert mohab.answers["past_month"].shows("Your position As of 2027-09-30")


def test_where_money_went_folds_small_categories_into_other(mohab):
    assert mohab.answers["year"].shows("Other")


def test_a_month_of_spending_is_shown_day_by_day(mohab):
    assert mohab.answers["where"].shows("Day by day")


def test_a_year_of_spending_is_shown_month_by_month(mohab):
    assert not mohab.answers["year_spending"].shows("Day by day")


def test_categories_say_which_way_money_moves_and_whether_it_repeats(mohab):
    assert mohab.answers["categories"].shows("− Expense + Income ± Both Recurring One-off")


def test_categories_need_no_sign_key(mohab):
    assert not mohab.answers["categories"].shows("− expense · + income · ± both")


def test_a_monthly_investing_goal_is_kept(mohab):
    screen = mohab.answers["invest_monthly"].screen
    assert any("month" in name for form in screen.forms for name in form.fields)
    mohab.b.open(screen.path)
    mohab.b.submit({"amount": "3000", "monthly_goal": "3000"}, button="Show suggested split")
    saved = mohab.b.open(screen.path)
    assert any(value == "3000" for form in saved.forms for name, value in form.fields.items()
               if name == "monthly_goal")


def test_selected_rows_can_be_edited_together(mohab):
    assert mohab.answers["bulk"].shows("Set category")
    rows = mohab.notes["bulk_rows"]
    assert rows >= 12   # one Talabat order a month, and the doubled one he deleted is gone
    done = mohab.notes["bulk_done"]
    assert done.shows(f"Food & Groceries is now the category of {rows} rows.")
    assert done.shows("Talabat Food & Groceries") and "Talabat Eating Out" not in done.text


def test_food_over_plan_two_months_running_gets_room_from_shopping(mohab):
    # Talabat is Food now (the bulk change above), so July and August ran 480 over: one move fixes September on.
    answer = mohab.answers["food_over"]
    assert answer.shows("Food & Groceries over plan two months running Over its plan in July and August, by up to "
                        "500 EGP. Move 500 from Shopping, which had that left both months. Move it")
    assert mohab.notes["move_popup"].shows("Move plan to Food & Groceries", "From 2027-09 on · the total plan stays the same")
    assert mohab.notes["moved"].shows("Moved plan from Shopping to Food & Groceries from 2027-09 on.")
    assert not mohab.answers["food_over_after"].shows("over plan two months running")


def test_a_fund_can_be_valued_by_its_total(mohab):
    screen = mohab.answers["fund_value"].screen
    field = next(field for block in re.findall(r"(?s)<tr\b.*?</tr>", screen.html)
                 if "Azimut" in re.sub(r"<[^>]+>", " ", block)
                 for field in re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', block)
                 if field.startswith("value_"))
    mohab.b.open(screen.path)
    saved = mohab.b.submit({"date": "2027-09-30", field: "20000"}, button="Save prices")
    assert saved.shows("Saved 1 price")


def test_other_investments_are_in_the_investment_analysis(mohab):
    assert route(mohab, "flat") == ["/", "/investments"]
    assert mohab.answers["flat"].shows("Other Investments", "400,000")
    # Recording the flat is not growth: the investments line and the net worth chart both say so.
    assert re.search(r"since six months ago, not counting 400,000 of opening balances", mohab.answers["flat"].screen.text)
    assert mohab.answers["flat_jump"].shows("2027-09 includes 400,000 of opening balances: yours before, so not a change.")


def test_the_flat_can_be_given_a_new_value(mohab):
    page = mohab.notes["flat_page"]
    assert any("value" in (text or "").casefold() for form in page.forms for text, *_ in form.buttons)
    account_id = int(re.search(r"/accounts/(\d+)", page.path).group(1))
    mohab.b.open(page.path)
    saved = mohab.b.submit({"date": "2027-09-30", "value": "425000"}, button="Update value")
    assert saved.shows("Dated estimated value saved")
    assert mohab.c.reporting.account_value(account_id, "2027-09-30") == D("425000")


def test_a_300_row_statement_with_seven_columns_reaches_review(mohab):
    form = mohab.notes["big_review"].form("Post ready rows")
    assert sum(name.startswith("notes_") for name in form.fields) == 300


def test_a_review_with_errors_still_has_a_way_on_and_a_way_back(mohab):
    screen = mohab.notes["import_error"]
    assert screen.shows("Nothing was imported")
    assert screen.form("Post ready rows")
    assert screen.link("Finish later").href == "/accounts/3"


def test_a_waiting_import_can_be_discarded(mohab):
    assert mohab.notes["import_error"].shows("Discard this import")


def test_several_statements_can_be_uploaded_together(mohab):
    assert re.search(r'<input[^>]*type="file"[^>]*\bmultiple\b', mohab.notes["upload_form"].html)


def test_a_small_difference_from_the_bank_is_one_adjustment(mohab):
    check = mohab.notes["wallet_check"]
    assert check.shows("A small difference", "Lightning is 30.00 EGP above your bank", "Post adjustment of −30.00")
    assert mohab.notes["wallet_adjusted"].shows("Balance adjustment", "The account now matches your bank")
    assert mohab.notes["wallet_adjusted"].shows("Balance adjustment Other Personal 2027-09-30 Bank showed",
                                                "−30 Balance 42,950")
    assert mohab.notes["wallet_rechecked"].shows("It matches")


def test_a_big_difference_from_the_bank_is_reviewed_not_adjusted(mohab):
    check = mohab.notes["cib_check"]
    assert check.shows("Too big to adjust", "Review 2027-09 row by row", "Import the statement again")
    assert not any("Post adjustment" in (text or "") for form in check.forms for text, *_ in form.buttons)
    review = check.link("Review 2027-09 row by row").href
    assert review.startswith("/accounts/1?date_from=2027-09-01&date_to=2027-09-30&return_to=/accounts/1/reconcile")


def test_settings_prepares_one_owned_ai_analysis_workbook(mohab):
    from io import BytesIO
    from xml.etree import ElementTree as ET
    from zipfile import ZipFile

    screen = mohab.b.go("Settings")
    assert screen.shows("Your data", "Export for AI", "All time", "YTD", "Monthly", "Custom",
                        "Prepare AI analysis", "Prompt for your AI tool", "Copy prompt")
    screen = mohab.b.submit(button="All time", action=r"/settings$")
    assert screen.shows("2026-07-01 to 2027-09-30", "transactions", "investment records")
    prompt = screen.html.split('data-ai-prompt', 1)[1].split('>', 1)[1].split('</textarea>', 1)[0]
    prompt = prompt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    assert "lightning-analysis-2026-07-01-to-2027-09-30.xlsx" in prompt
    assert "Categories used in the exported activity" in prompt
    form = screen.form(button="Prepare AI analysis", action=r"/settings/ai-analysis")
    response = mohab.b.client.post(form.action, data=form.fields)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert 'filename="lightning-analysis-2026-07-01-to-2027-09-30.xlsx"' in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as workbook:
        xml = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        root = ET.fromstring(workbook.read("xl/workbook.xml"))
        assert [sheet.attrib["name"] for sheet in root.findall(f".//{{{xml}}}sheet")] == [
            "Summary", "Transactions", "Investment ledger", "Categories"]
        transaction_sheet = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))
        roles = {row.findall(f"{{{xml}}}c")[6].find(f"{{{xml}}}is/{{{xml}}}t").text
                 for row in transaction_sheet.findall(f".//{{{xml}}}row")[1:]
                 if len(row.findall(f"{{{xml}}}c")) > 6}
        assert {"transfer", "refund", "investment contribution", "investment sale", "dividend",
                "ownership change", "expense paid externally"} <= roles


# ------------------------------------------------------------------ the same number on every tab, for every period
# Owner request 2026-10-04: check time horizons, and that a figure shown on several tabs reads the same on each.

def _figure(html: str, pattern: str):
    found = re.search(pattern, html, re.S)
    if not found:
        return None
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found.group(1)))
    return text.strip()


@pytest.mark.parametrize("period", ["period=month&month=2027-09", "period=month&month=2026-12", "period=ytd&month=2027-09",
                                    "period=all&month=2027-09", "period=custom&date_from=2026-10-01&date_to=2027-09-30",
                                    "period=custom&date_from=2027-02-01&date_to=2027-03-31"])
def test_a_figure_reads_the_same_on_every_tab(mohab, period):
    mohab.on("2027-09-30")
    get = lambda path: mohab.b.client.get(f"{path}?{period}").text
    overview, expenses, investments, budget = get("/"), get("/birdview/expenses"), get("/investments"), get("/budget")
    flat = lambda html: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    money_out = {"Overview": _figure(overview, r"<summary><span>Money out</span><b>([^<]+)</b>"),
                 "Expense analysis": _figure(expenses, r'aria-label="Money out".*?stat-tile-value[^>]*>([^<]+)<'),
                 # Budget's Spent covers only months with a plan, so it matches Money out within one month.
                 "Budget": _figure(flat(budget), r"Spent ([\d,]+) ") if "period=month" in period else None}
    assert len({money(v).copy_abs() for v in money_out.values() if v}) == 1, money_out
    money_in = {"Overview": _figure(overview, r"<summary><span>Money in</span><b>([^<]+)</b>"),
                "Investments": _figure(flat(investments), r"Of ([\d,]+) money in")}
    assert len({money(v) for v in money_in.values() if v}) == 1, money_in
    savings = {"Overview": _figure(overview, r'aria-label="Savings rate".*?stat-tile-value[^>]*>(.*?)</span>'),
               "Investments": _figure(flat(investments), r"Saved and invested.*? ([\d.,−—-]+ ?%?) Savings rate")}
    assert len({v.replace(" ", "").rstrip("%") for v in savings.values() if v}) == 1, savings
    gain = {"Overview": _figure(overview, r"<span>Net gain or loss</span><b[^>]*>([^<]+)</b>"),
            "Investments": _figure(investments, r'inv-result-tile.*?stat-tile-value[^>]*>([^<]+)<')}
    assert len({v.strip() for v in gain.values() if v}) == 1, gain
    cash = {"Overview": _figure(flat(overview), r"Brokerage cash ([\d,]+)"),
            "Investments": _figure(flat(investments), r"Brokerage cash ([\d,]+)")}
    assert len({v for v in cash.values() if v}) == 1, cash
    if "2027-03-31" not in period and "2026-12" not in period:   # the Investments tile is as of today
        # Deposits are their own figure: the CD used to count in Portfolio value on Investments only.
        portfolio = {"Overview": _figure(flat(overview), r"Portfolio value ([\d,]+)"),
                     "Investments": _figure(flat(investments), r"Portfolio value Last 6 months ([\d,]+)")}
        assert None not in portfolio.values() and len(set(portfolio.values())) == 1, portfolio



def test_a_rule_files_a_new_phone_as_shopping_and_keeps_the_monthly_bill(mohab):
    assert mohab.notes["rule_saved"].shows("Rule saved.", "Counterparty contains Vodafone · Amount between 1,000 and 50,000",
                                           "Shopping")
    assert route(mohab, "rule_filed") == ["/", "/accounts/1"]
    answer = mohab.answers["rule_filed"]
    assert answer.shows("Vodafone Shopping 2027-09-30 new phone −12,000",
                        "Vodafone Utilities & Bills 2027-09-30 −350")
