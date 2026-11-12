"""The phone's capture half (IV-3AN: 3AN3, NF-3AD1, NF-3AD2, 3AN5, 3AN6, 3AN8, the Transactions part of 3AN12).

Add opens a sheet on the amount with the account last used as one chip and the usual categories as chips; a row opens
its own sheet to look at first; the sheet of a row nobody sorted leads with category chips and walks the To sort list;
a pasted bank SMS fills the same sheet without asking for an account; Search looks for money first, live. The figures
come from services (usual categories, plan left, the To sort queue); these tests read what the pages show of them.
What a browser must show (Save above the keyboard, the chips on one screen, the tap counts) is measured by
`tools/phone_check.py` and the audit's `evidence/flows.py`."""
from __future__ import annotations

import re
from decimal import Decimal as D
from html import unescape

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _phone(c) -> TestClient:
    from lightning.ui.phone.router import mount_phone
    app = create_app(c)
    mount_phone(app)   # the real phone app: its router answers first (3AY11)

    @app.middleware("http")
    async def use_phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    return TestClient(app)


@pytest.fixture
def month(c, setup):
    """September 2026 in a household with a history: food most often, then software, one salary; two rows nobody sorted."""
    accounts, cats = setup
    cib, wallet = accounts["cib"], accounts["wallet"]
    t = c.transactions
    t.record_in_account(cib.id, "2026-09-02", "45000", cats["EXP.WORK.SALARY"].id, None, "ACME Egypt", "")
    for day, amount, party in (("2026-09-03", "-1200", "Carrefour"), ("2026-09-10", "-300", "Carrefour"), ("2026-09-12", "-250", "Seoudi")):
        t.record_in_account(cib.id, day, amount, cats["EXP.PERSONAL.FOOD"].id, None, party, "")
    t.record_in_account(wallet.id, "2026-09-04", "-300", cats["EXP.WORK.SOFTWARE"].id, None, "Figma", "")
    t.record_transfer("2026-09-05", cib.id, wallet.id, "2000")
    t.record_outflow("2026-09-06", cib.id, "80", c.categories.get_by_code("EXP.UNACCOUNTED").id, counterparty="Kiosk",
                     allow_system_category=True)
    t.record_inflow("2026-09-07", cib.id, "500", c.categories.get_by_code("INC.UNACCOUNTED").id, counterparty="Someone",
                    allow_system_category=True)
    t.record_outflow("2026-09-08", cib.id, "40", c.categories.get_by_code("EXP.UNACCOUNTED").id, counterparty="Stall",
                     allow_system_category=True)
    return c, accounts, cats


def _txn_id(c, party: str) -> int:
    return int(c.db.scalar("SELECT id FROM transactions WHERE counterparty = ? ORDER BY id DESC", (party,)))


# ---- the services behind the chips ----------------------------------------------------------------------------------

def test_the_usual_categories_come_from_the_history_most_used_first(month):
    c, _, cats = month
    out = c.transactions.usual_capture_categories("out")
    assert out[0] == cats["EXP.PERSONAL.FOOD"].id and out[1] == cats["EXP.WORK.SOFTWARE"].id   # 3 uses, then 1
    assert len(out) == 4 and len(set(out)) == 4                                                  # a thin history is filled to four
    unfiled = {c.categories.get_by_code(code).id for code in ("EXP.UNACCOUNTED", "INC.UNACCOUNTED")}
    assert not unfiled & set(out)                                                                # never "Unaccounted"
    assert c.transactions.usual_capture_categories("in")[0] == cats["EXP.WORK.SALARY"].id
    assert c.transactions.usual_capture_categories("transfer") == []


def test_the_chips_put_this_part_of_the_days_hand_typed_entries_first(month):
    """3AY7: software typed by hand in the morning leads at 9 am although food is used more; at 8 pm food leads."""
    c, _, cats = month
    c.db.execute("UPDATE transactions SET source = 'MANUAL', created_at = '2026-09-04T20:00:00+03:00'")
    c.db.execute("UPDATE transactions SET created_at = '2026-09-04T09:05:00+03:00' WHERE counterparty = 'Figma'")
    assert c.transactions.usual_capture_categories("out", hour=9)[0] == cats["EXP.WORK.SOFTWARE"].id
    assert c.transactions.usual_capture_categories("out", hour=20)[0] == cats["EXP.PERSONAL.FOOD"].id
    assert c.transactions.usual_capture_categories("out", hour=3)[0] == cats["EXP.PERSONAL.FOOD"].id


def test_the_account_add_opens_on_is_the_one_used_most(month):
    c, accounts, _ = month
    both = [accounts["cib"].id, accounts["wallet"].id]
    assert c.transactions.usual_account(both) == accounts["cib"].id
    assert c.transactions.usual_account([accounts["wallet"].id]) == accounts["wallet"].id
    assert c.transactions.usual_account([]) is None


# ---- the Add sheet ----------------------------------------------------------------------------------------------------

def test_the_add_sheet_is_amount_first_with_chips_and_no_card(month):
    c, accounts, cats = month
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{accounts['cib'].id}/transaction/new").text
    assert 'inputmode="decimal"' in sheet and 'placeholder="0"' in sheet and "autofocus" in sheet
    assert " card " not in sheet.split('class="app-popup-content phone-entry')[1].split("</section>")[0]  # no card inside the sheet
    assert 'class="phone-save-bar"' in sheet and sheet.count('class="btn primary phone-save"') == 1     # one Primary, pinned
    assert 'data-account-chip' in sheet and 'data-sms-paste' in sheet and 'type="date"' in sheet
    out_group = re.search(r'data-chip-kind="out"[^>]*>(.*?)</span>', sheet, re.S).group(1)
    chips = re.findall(r'data-category="(\d+)"[^>]*>([^<]+)<', out_group)
    assert [int(i) for i, _ in chips] == c.transactions.usual_capture_categories("out")           # the service's order
    assert unescape(chips[0][1]) == "Food & Groceries"                                                       # the usual first
    assert "data-chip-other" in sheet and 'name="category_id"' in sheet                          # the field itself stays
    assert "decreases by" not in sheet and "balance owned by" not in sheet


def test_the_add_sheet_is_decluttered_amount_before_usual_and_shortcuts_are_quiet_links(month):
    """Owner, 2026-11-12: the segment alone on its row, the amount first, one Primary Save, Save and add another and the
    shortcuts as quiet links, and no placeholder that repeats its label."""
    c, accounts, _ = month
    sheet = _phone(c).get(f"/accounts/{accounts['cib'].id}/transaction/new").text
    top = sheet.split('class="phone-entry-top"')[1].split("</div>\n    </div>")[0]
    assert "phone-segment" in top and "phone-sms-paste" not in top and "phone-pay-bill" not in top  # nothing beside the segment
    assert sheet.index('id="popup-amount"') < sheet.index("data-account-chip")
    if "data-usual-entries" in sheet:
        assert sheet.index('id="popup-amount"') < sheet.index("data-usual-entries")
        assert "popup-usual-label" in sheet and 'phone-usual-row' in sheet
    bar = sheet.split('class="phone-save-bar"')[1]
    assert bar.count('class="btn primary phone-save"') == 1 and "btn phone-save-again" not in sheet
    assert 'name="again" value="1" class="phone-quiet phone-save-again"' in bar and "data-sms-paste" not in bar
    assert sheet.index("data-sms-paste") < sheet.index('class="phone-save-bar"')  # shortcuts end the form, above the bar
    assert 'class="phone-quiet phone-sms-paste"' in sheet and 'class="phone-chip phone-sms-paste"' not in sheet
    assert "Who you paid or who paid you" not in sheet.split('id="popup-counterparty"')[1].split(">")[0]


def test_add_on_an_account_page_chooses_that_account_and_the_chip_lists_the_rest(month):
    c, accounts, _ = month
    phone = _phone(c)
    page = phone.get(f"/accounts/{accounts['wallet'].id}").text
    assert f'class="phone-tab phone-add" href="/accounts/{accounts["wallet"].id}/transaction/new' in page
    sheet = phone.get(f"/accounts/{accounts['wallet'].id}/transaction/new").text
    assert re.search(rf'<option value="{accounts["wallet"].id}" selected>Wallet</option>', sheet)
    assert re.search(rf'<option value="{accounts["cib"].id}">CIB Current</option>', sheet)


def test_add_without_a_remembered_account_opens_a_sheet_not_a_list(month):
    c, accounts, _ = month
    phone = _phone(c)
    sheet = phone.get("/accounts/add-transaction").text
    assert "To which account?" not in sheet and f'action="/accounts/{accounts["cib"].id}/transaction/new"' in sheet
    assert "To which account?" in phone.get("/accounts/add-transaction?pick=1").text
    phone.cookies.set("lightning_last_account", str(accounts["wallet"].id))
    assert f'action="/accounts/{accounts["wallet"].id}/transaction/new"' in phone.get("/accounts/add-transaction").text


def test_the_sheet_can_be_opened_with_what_was_typed(month):
    """Changing the account chip, or a pasted SMS naming another account, opens the same sheet filled in."""
    c, accounts, cats = month
    fp = "a" * 32
    sheet = _phone(c).get(f"/accounts/{accounts['wallet'].id}/transaction/new", params={
        "kind": "in", "amount": "1,250", "date": "2026-09-30", "counterparty": "ACME Egypt", "sms_fp": fp,
        "sms_ending": "7351", "category_id": cats["EXP.WORK.SALARY"].id}).text
    assert re.search(r'name="kind" value="in" checked', sheet) and 'value="1,250"' in sheet and 'value="2026-09-30"' in sheet
    assert 'value="ACME Egypt"' in sheet and f'name="sms_fp" value="{fp}"' in sheet and 'name="sms_ending" value="7351"' in sheet
    junk = _phone(c).get(f"/accounts/{accounts['wallet'].id}/transaction/new", params={
        "kind": "sideways", "amount": "<b>", "date": "tomorrow", "sms_fp": "x", "sms_ending": "12"}).text
    assert re.search(r'name="kind" value="out" checked', junk) and "<b>" not in junk


def test_saving_from_the_sheet_remembers_the_account_and_says_saved_with_undo(month):
    c, accounts, cats = month
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{accounts['wallet'].id}/transaction/new").text
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    saved = phone.post(f"/accounts/{accounts['wallet'].id}/transaction/new", data={
        "__session": session, "kind": "out", "amount": "120", "category_id": str(cats["EXP.PERSONAL.FOOD"].id),
        "date": "2026-09-14", "return_to": "/"})
    assert saved.status_code == 200 and "Saved." in saved.text
    assert 'class="flash phone-flash"' in saved.text                                              # the toast above the tab bar
    assert phone.cookies.get("lightning_last_account") == str(accounts["wallet"].id)


# ---- a transaction's own sheet --------------------------------------------------------------------------------------

def test_a_row_opens_its_sheet_first_and_the_sheet_looks_before_it_edits(month):
    c, accounts, cats = month
    phone = _phone(c)
    c.budgets.set_budget(cats["EXP.PERSONAL.FOOD"].id, "2026-09", "5000", schedule=c.schedules.view())
    page = phone.get("/transactions?month=2026-09").text
    row = re.search(r'<a class="phone-txn" href="([^"]+)" data-txn="%d"' % _txn_id(c, "Seoudi"), page)
    assert row and unescape(row.group(1)).startswith(f"/transactions/{_txn_id(c, 'Seoudi')}/sheet?return_to=") and "data-popup-open" in page
    sheet = phone.get(f"/transactions/{_txn_id(c, 'Seoudi')}/sheet?return_to=/transactions").text
    body = re.sub(r"<[^>]+>", " ", sheet)
    assert "phone-txn-av is-out" in sheet                                           # the arrow chip
    assert ">−250</bdi>" in sheet and "−250.00" not in sheet                         # whole EGP, no .00
    assert "Seoudi" in body and "Food & Groceries" in unescape(body)
    left = D("5000") - D("1200") - D("300") - D("250")
    assert f"{left:,.0f} left of 5,000" in body                                          # Plan left, from BudgetService
    assert "Change category" in body and "Split" in body and "/edit-popup" in sheet  # the foot; Edit opens the form
    assert "<form" not in sheet.split("phone-sheet-actions")[0].split("phone-txn-sheet\">")[1]       # nothing to type yet
    assert c.budgets.plan_left(cats["EXP.PERSONAL.FOOD"].id, "2026-09", schedule=c.schedules.view())["left"] == left


def test_the_sheet_of_a_move_and_of_a_row_without_a_plan(month):
    c, accounts, cats = month
    phone = _phone(c)
    move = c.db.scalar("SELECT id FROM transactions WHERE type = 'TRF'")
    sheet = phone.get(f"/transactions/{move}/sheet").text
    assert "phone-txn-av is-move" in sheet and "2,000" in sheet and "+2,000" not in sheet and "−2,000" not in sheet
    assert "Plan left" not in sheet and "CIB Current → Wallet" in sheet
    software = phone.get(f"/transactions/{_txn_id(c, 'Figma')}/sheet").text
    assert "Plan left" not in software                                               # no limit covers it


def test_a_row_the_sheet_cannot_show_goes_to_its_page(month):
    c, accounts, _ = month
    opening = c.db.scalar("SELECT id FROM transactions WHERE type = 'OPN' ORDER BY id")
    reply = _phone(c).get(f"/transactions/{opening}/sheet", follow_redirects=False)
    assert reply.status_code == 303 and reply.headers["location"] == f"/transactions/{opening}"
    pc = TestClient(create_app(c))
    seoudi = _txn_id(c, "Seoudi")
    assert pc.get(f"/transactions/{seoudi}/sheet", follow_redirects=False).headers["location"] == f"/transactions/{seoudi}"


def test_change_category_offers_the_usual_ones_as_chips_and_one_tap_files_the_row(month):
    c, accounts, cats = month
    phone = _phone(c)
    seoudi = _txn_id(c, "Seoudi")
    sheet = phone.get(f"/transactions/{seoudi}/sheet?change=1&return_to=/transactions").text
    ids = [int(i) for i in re.findall(r'name="category_id" value="(\d+)"><button type="submit" class="phone-chip', sheet)]
    assert ids and ids[0] == cats["EXP.PERSONAL.FOOD"].id and cats["EXP.WORK.SOFTWARE"].id in ids
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    done = phone.post(f"/transactions/{seoudi}/category", data={
        "__session": session, "category_id": str(cats["EXP.WORK.SOFTWARE"].id), "return_to": "/transactions"})
    assert done.status_code == 200 and done.url.path == "/transactions" and "is now the category of 1 row" in done.text
    assert c.transactions.get(seoudi).lines[0].category_id == cats["EXP.WORK.SOFTWARE"].id
    refused = phone.post(f"/transactions/{seoudi}/category", data={
        "__session": session, "category_id": str(cats["EXP.WORK.SALARY"].id), "return_to": "/transactions"})
    assert refused.status_code == 400 and "does not fit" in refused.text


def test_a_row_to_sort_leads_with_chips_and_one_tap_opens_the_next(month):
    """J5 in three taps: To sort, the row, a category chip; the next unsorted row opens by itself."""
    c, accounts, cats = month
    phone = _phone(c)
    ids = [_txn_id(c, name) for name in ("Stall", "Someone")]            # newest first: Stall (09-08), Someone (09-07), Kiosk (09-06)
    assert c.reporting.unsorted_in_order(None, "2026-09-01", "2026-09-30")[:2] == ids      # newest first
    page = phone.get("/transactions?month=2026-09&kind=unsorted").text
    link = unescape(re.search(r'href="(/transactions/%d/sheet\?[^"]+)"' % ids[0], page).group(1))
    assert "sort=1" in link and "sf=2026-09-01" in link and "st=2026-09-30" in link
    sheet = phone.get(link).text
    assert "Which category?" in sheet and 'data-popup-return="popup"' in sheet and "Not sorted yet" not in sheet
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    form = {"__session": session, "category_id": str(cats["EXP.PERSONAL.FOOD"].id), "return_to": "/transactions?month=2026-09&kind=unsorted",
            "sort": "1", "sa": "", "sf": "2026-09-01", "st": "2026-09-30"}
    nxt = phone.post(f"/transactions/{ids[0]}/category", data=form)
    assert nxt.url.path.endswith("/sheet") and "Which category?" in nxt.text                 # the next one is open
    assert c.transactions.get(ids[0]).lines[0].category_id == cats["EXP.PERSONAL.FOOD"].id
    remaining = c.reporting.unsorted_in_order(None, "2026-09-01", "2026-09-30")
    assert str(remaining[0]) in nxt.url.path and ids[0] not in remaining
    for txn_id in list(remaining):
        last = phone.post(f"/transactions/{txn_id}/category", data=form | {
            "category_id": str(cats["EXP.PERSONAL.FOOD"].id if c.transactions.get(txn_id).type.value == "OUT" else cats["EXP.WORK.SALARY"].id)})
    assert last.url.path == "/transactions/sorted" and "All sorted" in last.text and "data-popup-close" in last.text
    assert c.reporting.unsorted_in_order(None, "2026-09-01", "2026-09-30") == []


# ---- the page's other edges ---------------------------------------------------------------------------------------

def test_the_phone_has_the_capture_script_and_the_pc_does_not(month):
    c, _, _ = month
    assert "/static/phone-capture.js" in _phone(c).get("/").text
    assert "phone-capture.js" not in TestClient(create_app(c)).get("/").text


# ---- on the sample household, in a profile app ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample_phone(tmp_path_factory):
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Credentials
    from test_profile_app import create, token
    folder = tmp_path_factory.mktemp("capture")
    cfg = Credentials("http://127.0.0.1:9871")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        browser.session_token = token(browser.get("/").text, "__session")
        browser.post("/demo", data={"__session": browser.session_token})
        yield browser


def test_the_toast_after_a_save_carries_undo_and_undo_stays_where_you_were(sample_phone):
    phone = sample_phone
    sheet = phone.get("/accounts/1/transaction/new").text
    category = re.search(r'<option value="(\d+)" data-movement="OUTFLOW"', sheet).group(1)
    saved = phone.post("/accounts/1/transaction/new", data={
        "__session": phone.session_token, "kind": "out", "amount": "33", "category_id": category,
        "counterparty": "Toast kiosk", "date": "2026-10-06", "return_to": "/transactions"})
    assert saved.url.path == "/transactions" and "Saved." in saved.text
    undo = re.search(r'<form class="history-form" method="post" action="/history/undo">(.*?)</form>', saved.text, re.S)
    assert undo and 'name="back" value="/transactions' in undo.group(1)         # Undo returns to this page, not to the top
    group = re.search(r'name="group_id" value="([^"]+)"', undo.group(1)).group(1)
    back = re.search(r'name="back" value="([^"]+)"', undo.group(1)).group(1)
    undone = phone.post("/history/undo", data={"__session": phone.session_token, "group_id": group, "back": unescape(back)})
    assert undone.url.path == "/transactions" and "Toast kiosk" not in undone.text


def test_a_buy_reads_as_a_move_with_no_sign_and_the_day_agrees(sample_phone):
    """3AN8 on the sample's money market buy: azure arrow, 3,000 with no minus, and the day's net leaves it out."""
    page = sample_phone.get("/transactions?preset=all_time").text
    rows = re.findall(r'(?s)<a class="phone-txn" href="[^"]*"[^>]*>(.*?)</a>', page)
    buy = next(row for row in rows if "Money market" in row and "Buy" in row)
    assert "phone-txn-av is-invest" in buy
    amount = re.search(r'<span class="phone-txn-amount">(.*?)</span>', buy, re.S).group(1)
    assert "3,000" in amount and not re.search(r"[−+-]", re.sub(r"<[^>]+>", "", amount))
    days = re.split(r'<div class="phone-day"', page)
    day = next(chunk for chunk in days if "Money market" in chunk and "Buy" in chunk)
    shown = re.search(r'<span class="phone-day-net"><bdi class="fig">([^<]+)</bdi>', day)
    figures = re.findall(r'<b(?: class="(?:pos)?")?><bdi class="fig">([^<]+)</bdi>', day.split('<div class="phone-day-rows">')[1])
    number = lambda text: D(text.replace(",", "").replace("−", "-").replace("+", ""))  # noqa: E731
    money = [number(v) for v in figures if v[0] in "+−"]                  # the rows that moved money in or out carry a sign
    assert len(money) < len(figures)                                          # the buy has none
    assert shown is None or abs(number(shown.group(1)) - sum(money)) < 1   # the buy is in no sum (a day's net is whole EGP)
