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
from lightning.ui.phone.router import mount_phone
from test_mohab_year import Answer, Mohab, _live_the_year

# The PC's link or button -> the phone's taps. A step starting with "/" opens that page; with "?" it is
# typed into the page's search box; anything else is tapped on the page.
DETOURS = {
    "Add account": ("Money", "Accounts", "Add account"),           # the PC's sidebar +; the phone's Accounts ⋯
    "Held for others": ("Money", "Accounts", "Held for others"),   # an Accounts tab; Transactions opens on this month
    "Accounts": ("Money", "Accounts"),                             # sections without a tab-bar slot live on More
    "Cash planning": ("Money", "Cash planning"),
    "Investments": ("Money", "Investments"),
    "Financial health": ("Money", "Financial health"),
    "Add transaction": ("Add",),
    "Settings": ("Money", "All settings"),
    "Health": ("Money", "Financial health"),                       # the Overview opens on its answer, no tab row
    "Spending": ("Money", "Spending"),
    "Safety": ("Money", "Reserves"),                               # the app bar's page menu is gone (3AN2): Reserves is a row on More
    "Currencies": ("Money", "Financial health", "Currencies"),                         # the app bar's gear is a tab's own settings only                                  # the tab bar's Add, its word under the disc
    "NBE 3-year certificate": ("/money/accounts", "NBE 3-year certificate"),  # the PC lists accounts in its sidebar
    "Gold at home": ("/money/accounts", "Gold at home"),
    "Family flat (my share)": ("/money/accounts", "Family flat (my share)"),
    "Import statement": ("Import a statement",),                        # behind the account's ⋯
    "Loans still to pay": ("Money", "What you owe"),  # Money's What you owe row opens the loans page, which states what is still to pay (3AY10)
    "Data checks": ("/settings", "Data checks"),                  # from a settings sheet: Settings, then the tab
    "Categories": ("/settings", "Categories"),
    "Rules": ("/settings", "Rules"),
    "#Eid": ("?q=%23eid",),                                       # a note's tag: typed into the search
    "See them": ("Allocation, income and horizon", "See them"),  # income collected sits on the fuller page behind Investments
    "Investment planner": ("Planner",),
    "Zakat": ("Money", "Zakat"),                                  # Money's places, when Zakat is on
    "Set a plan for 2026-09": ("/budget?month=2026-09", "Make my plan"),  # the new Budget's no-plan step leads to the plan form
    "Needs you": ("/needs-you",),                                  # Home's To do names three rows; See all opens this whole list
    "Imported activity needs a decision": ("/activity?tab=review", "Finish the import"),  # Activity's To review card (3AY8)
}
# Home names no account (3AY6): the accounts the PC lists in its sidebar are reached through Money, then its Accounts
# page (3AY10), which lists every balance.
VIA_CASH_YOU_OWN = "Cash you own"
# The Overview's period report (how did my year go?) has no phone screen yet: Home is always today (3AY6, D2).
OVERVIEW_REPORT = "Overview report"
# Home's To do shows three rows; See all opens the whole list.
TODO_SEE_ALL = "To do: See all"
# Sections without a tab-bar slot (phone overhaul 2026-10-22): their taps go through More.
MOVED = {"Accounts", "Cash planning", "Investments", "Financial health", "Health", "Spending", "Currencies", "Settings"}
# The phone's Choose period sheet (phone overhaul 2026-10-22) names the PC's period buttons in words.
BUTTONS = {"Custom": "Apply", "YTD": "Year to date", "Monthly": "This month", "Search": None}  # the phone's Search is live: no button, Enter sends it (3AN6)


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
                    if self.page is not None and self.page.path.split("?")[0] in ("/", "/home", "/money") and text not in MOVED:
                        self.detours[VIA_CASH_YOU_OWN] += 1   # Home names no account: Money's Accounts lists every balance
                        self._framed(super().click("Money"))
                        self._framed(super().click("Accounts"))
                        return self._framed(super().click(text))
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
        if button in ("All time", "Year to date") and not args and kwargs.get("page") is None:
            self.detours[OVERVIEW_REPORT] += 1   # Home is always today: the period buttons are the report's chips
            self.open("/money/report?period=" + ("all" if button == "All time" else "ytd"))
            return self.page
        try:
            return super().submit(values, button, *args, **kwargs)
        except (AssertionError, StopIteration):
            if button not in BUTTONS:
                raise
        self.detours[f"button {button}"] += 1
        return super().submit(values, BUTTONS[button] or None, *args, **kwargs)


class PhoneMohab(Mohab):
    """Mohab with the phone in his hand."""

    def __init__(self, c):
        super().__init__(c)
        from lightning.ui.web import create_app
        app = create_app(c)
        mount_phone(app)  # the phone's own screens answer first, as profile_app(phone=True) does
        self.b = PhoneBrowser(app)

    def ask(self, key, question, *clicks, start="/"):
        """Home leads with Safe to spend and To do; what he owns lives on Money (3AY6, 3AY10)."""
        return super().ask(key, question, *clicks, start="/money" if key == "needs_you" and not clicks else start)

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

    def ask_needs(self, key, question, group, *actions):
        """Budget and saving decisions (a raise) are on the Budget screen; the rest sit on Home's To do."""
        if group != "Budget and saving":
            # Home's To do shows three rows; its See all opens the whole Needs you list (the PC page, in the phone frame)
            self.b.open("/")
            self.b.detours[TODO_SEE_ALL] += 1
            screen = self.b.open("/needs-you")
            if any(link.text.startswith(group + " · ") for link in screen.links):
                screen = self.b.click(group + " · ")
            for action in actions:
                screen = self.b.click(action)
            self.answers[key] = Answer(question, list(self.b.trail), screen)
            return screen
        screen = self.b.open("/budget")
        for action in actions:
            screen = self.b.click(action)
        self.answers[key] = Answer(question, list(self.b.trail), screen)
        return screen

    def period(self, page, date_from, date_to):
        """Home is always today (3AY6, owner D2): the year's report is the Overview with a period, opened with its
        address until the report has a phone home of its own (a known detour, named in DETOURS' neighbour below)."""
        if page:
            return super().period(page, date_from, date_to)
        self.b.detours[OVERVIEW_REPORT] += 1
        self.b.open("/money/report?period=custom")
        screen = self.b.submit({"date_from": date_from, "date_to": date_to}, button="Apply")
        return screen

    def pay_from_overview(self, item):
        """Home's To do shows three rows; every bill is one tap away on Money's Bills page (3AY10)."""
        self.b.open(self._pay_link(self.b.go("Money", "All bills"), item))
        return self.b.submit({}, button="Record and mark")

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
    expected = set(DETOURS) | {f"button {b}" for b in BUTTONS} | {"Select", VIA_CASH_YOU_OWN, OVERVIEW_REPORT, TODO_SEE_ALL}
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
    assert mohab.answers["eid_tag"].shows("Tagged #eid", "In +1,000 · Out −3,000")   # the period's money in and out, one quiet line (D2)


def test_needs_you_and_get_set_up_say_what_a_tap_does(mohab):
    # Home's To do rows each end with the one action a tap does (3AY6). At the year's end everything may be settled,
    # and Home then leads with the hero alone; test_phone_home.py holds the busy states.
    home = mohab.b.client.get("/").text
    assert 'id="home-hero"' in home
    if 'id="todo-heading"' in home:
        assert re.search(r"<b>(Pay|Plan|Catch up|Sort|Review|Open) ›</b>", home)
