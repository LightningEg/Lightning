"""Mohab's year on the phone: the same year as tests/test_mohab_year.py, lived through the phone app's screens
(guideline Part C). Every page renders in the phone frame, and where the phone's way differs from the PC's
he takes the phone's way: the add button and its sheet for a row, Select for several rows, ⋯ for the rarer
account actions, the tab bar for an account the PC lists in its sidebar.

What this checks: the whole year can be lived on the phone with no dead end (2026-10-06 audit: no CDs, no
buy or sell, no refund, no first plan, no budget limits, no delete, no selecting rows), every screen he
meets is in the phone frame, and the phone answers his questions. Where the phone's way differs from the
PC's, DETOURS names it; a new difference fails here until it is a deliberate phone way and added there."""
from __future__ import annotations

import html
import os
import re
from collections import Counter
from datetime import datetime, time, timezone

import pytest

import screens
from lightning.bootstrap import build
from lightning.core import dates
from test_mohab_year import Mohab, _live_the_year

# The PC's link or button -> the phone's taps. A step starting with "/" opens that page; with "?" it is
# typed into the page's search box; anything else is tapped on the page.
DETOURS = {
    "+ Add account": ("More", "Accounts", "Add account"),         # the PC's sidebar; the phone's Accounts ⋯
    "Manage accounts": ("More", "Accounts"),
    "Accounts": ("More", "Accounts"),                             # sections without a tab-bar slot live on More
    "Cash planning": ("More", "Cash planning"),
    "Investments": ("More", "Investments"),
    "Financial health": ("More", "Financial health"),
    "Add transaction": ("Add",),
    "Settings": ("More", "All settings"),
    "Health": ("More", "Financial health"),                       # the Overview opens on its answer, no tab row
    "Spending": ("More", "Spending"),
    "Currencies": ("More", "Financial health", "Currencies"),                         # the app bar's gear is a tab's own settings only                                  # the tab bar's Add, its word under the disc
    "NBE 3-year certificate": ("/accounts", "NBE 3-year certificate"),  # the PC lists accounts in its sidebar
    "Gold at home": ("/accounts", "Gold at home"),
    "Family flat (my share)": ("/accounts", "Family flat (my share)"),
    "Import statement": ("Import a statement",),                        # behind the account's ⋯
    "Loans still to pay": ("What you owe",),                      # the Overview's row that opens Loans
    "Data checks": ("/settings", "Data checks"),                  # from a settings sheet: Settings, then the tab
    "Categories": ("/settings", "Categories"),
    "Rules": ("/settings", "Rules"),
    "#Eid": ("?q=%23eid",),                                       # a note's tag: typed into the search
    "Investment planner": ("Planner",),
}
# Sections without a tab-bar slot (phone overhaul 2026-10-22): their taps go through More.
MOVED = {"Accounts", "Cash planning", "Investments", "Financial health", "Health", "Spending", "Currencies", "Settings"}
# The phone's Choose period sheet (phone overhaul 2026-10-22) names the PC's period buttons in words.
BUTTONS = {"Custom": "Apply", "YTD": "Year to date", "Monthly": "This month"}


def _phone(app):
    """The phone app: every request renders in the phone frame, as profile_app(phone=True) does."""
    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return wrapped


class PhoneBrowser(screens.Browser):
    def __init__(self, app):
        super().__init__(_phone(app))
        self.detours: Counter = Counter()
        self.unframed: set[str] = set()

    def _framed(self, page):
        if 'class="phone-appbar"' not in page.html:
            self.unframed.add(page.path)
        return page

    def open(self, path: str):
        if "?q=Talabat" in path:   # ticking rows starts with Select (or press and hold, C08.5)
            self.detours["Select"] += 1
            path += "&select=1"
        return self._framed(super().open(path))

    def click(self, text: str):
        wanted = " ".join(text.split()).casefold()
        moved = text in MOVED and self.page is not None and not any(
            " ".join(link.text.split()).casefold() == wanted for link in self.page.links)
        if not moved:  # a section moved to More is reached by its taps there, never by a look-alike link
            try:
                return self._framed(super().click(text))
            except AssertionError:
                if text not in DETOURS:
                    raise
        self.detours[text] += 1
        for step in DETOURS[text]:
            if step.startswith("/"):
                self.open(step)
            elif step.startswith("?"):
                self.open(self.page.path + step)
            else:
                self._framed(super().click(step))
        return self.page

    def submit(self, values=None, button=None, *args, **kwargs):
        try:
            return super().submit(values, button, *args, **kwargs)
        except (AssertionError, StopIteration):
            if button not in BUTTONS:
                raise
        self.detours[f"button {button}"] += 1
        return super().submit(values, BUTTONS[button], *args, **kwargs)


class PhoneMohab(Mohab):
    """Mohab with the phone in his hand."""

    def __init__(self, c):
        super().__init__(c)
        from lightning.ui.web import create_app
        self.b = PhoneBrowser(create_app(c))

    def enter(self, account, when, party, category, amount, **more):
        """The add button opens the entry sheet (C05.2, C09): Out, In or Transfer, then the fields."""
        self.b.go("Accounts", account, "Add transaction")  # the Overview leads with transactions now (C11.1)
        value = amount.replace(",", "")
        targets = [label for _, label in self.b.page.form("Save").options.get("to_account_id", [])]
        if any(party.casefold() == t.split(" · ")[0].strip().casefold() for t in targets):
            return self.b.submit({"kind": "transfer", "date": when, "to_account_id": screens.Choose(party),
                                  "amount": value.lstrip("-+")} | more)
        return self.b.submit({"kind": "out" if value.startswith("-") else "in", "date": when, "counterparty": party,
                              "category_id": screens.Choose(category.split(" › ")[-1]),
                              "amount": value.lstrip("-+")} | more)

    def _pay_link(self, screen, name):
        """On the phone the bill's row itself opens its pay sheet."""
        found = re.search(r'href="(/plan/items/\d+/pay\?[^"]+)"[^>]*><span>' + re.escape(name), screen.html)
        return found.group(1).replace("&amp;", "&") if found else super()._pay_link(screen, name)

    def transaction_id(self, account, party):
        """The phone's list: each row opens its sheet; the newest comes first."""
        screen = self.b.go("Accounts", account)  # the Overview leads with transactions now (C11.1)
        for href, body in re.findall(r'(?s)<a class="phone-txn" href="([^"]+)"[^>]*>(.*?)</a>', screen.html):
            if party in html.unescape(body):
                return re.search(r"/transactions/(\d+)", href).group(1)
        raise AssertionError(f"No row for {party} in {account}")

    def fix_amount(self, account, party, amount):
        """Tap the row; change the amount in its sheet."""
        self.b.open(f"/transactions/{self.transaction_id(account, party)}/edit-popup?return_to=/")
        return self.b.submit({"amount": amount.lstrip("-")})


@pytest.fixture(scope="module")
def mohab(tmp_path_factory):
    pinned = os.environ.get("LIGHTNING_TODAY")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dates, "_local_now", lambda: datetime.combine(dates.today(), time(12), timezone.utc))
        c = build(tmp_path_factory.mktemp("mohab-phone") / "mohab.db")
        try:
            person = PhoneMohab(c)
            _live_the_year(person)
            yield person
        finally:
            c.db.close()
            os.environ["LIGHTNING_TODAY"] = pinned or ""


def test_the_whole_year_is_lived_on_the_phone_with_only_the_known_detours(mohab):
    expected = set(DETOURS) | {f"button {b}" for b in BUTTONS} | {"Select"}
    assert set(mohab.b.detours) <= expected, set(mohab.b.detours) - expected


def test_every_screen_he_meets_is_in_the_phone_frame(mohab):
    assert not mohab.b.unframed, mohab.b.unframed


def test_a_refund_and_a_typed_budget_limit_work_on_the_phone(mohab):
    # Amazon's refund went in as money in to Shopping (no "matches this transaction type" refusal).
    assert mohab.answers["refund"].screen.path.startswith("/birdview/expenses")
    # He typed the loans limit beside the category on the phone's Budget (Mohab.plan_category).
    assert mohab.b.client.get("/budget?month=2027-04").status_code == 200


def test_several_rows_get_one_category_together(mohab):
    rows = mohab.notes["bulk_rows"]
    assert rows >= 12   # one Talabat order a month, chosen with Select
    assert mohab.notes["bulk_done"].shows(f"Food & Groceries is now the category of {rows} rows.")


def test_a_tag_gathers_its_rows_with_their_totals(mohab):
    assert mohab.answers["eid_tag"].shows("Tagged #eid", "Money in", "Money out")


def test_needs_you_and_get_set_up_say_what_a_tap_does(mohab):
    overview = mohab.b.client.get("/").text
    assert 'class="phone-row-action"' in overview
