"""Backend roadmap B1-B5 (phone performance): the phone's Overview and pages skip what they never show, the
category look-up reads once for every name, and Quick Add saves one entry however often it is tapped."""
import re

from fastapi.testclient import TestClient

import lightning.ui.web as web
from lightning.samples import load_mohab_2026
from lightning.ui.routes.register import counterparty_category_map
from test_reporting_performance import _years_of_history


def _as_phone(app):
    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        return await app(scope, receive, send)
    return phone_app


def _reads(c, monkeypatch, call):
    statements = []
    original = type(c.db).conn.fget

    def traced(db):
        conn = original(db)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(type(c.db), "conn", property(traced))
    try:
        result = call()
    finally:
        monkeypatch.setattr(type(c.db), "conn", property(original))
        c.db.conn.set_trace_callback(None)
    return result, sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)


def _history(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    _years_of_history(c, 2)


def test_the_phone_home_reads_far_less_than_the_pc_overview(c, monkeypatch):
    """The phone's own Home asks only for what it shows (IV-3AY: "each screen asks only for what it shows"). The older
    phone Overview, which skipped work inside the PC route, is no longer the phone's first page (3AY11)."""
    from lightning.ui.phone.router import mount_phone
    _history(c, monkeypatch)
    app, phone_app = web.create_app(c), web.create_app(c)
    mount_phone(phone_app)
    with TestClient(app) as pc, TestClient(_as_phone(phone_app)) as phone:
        pc.get("/"), phone.get("/")  # settle first-visit work
        pc_page, pc_reads = _reads(c, monkeypatch, lambda: pc.get("/"))
        phone_page, phone_reads = _reads(c, monkeypatch, lambda: phone.get("/"))
    assert pc_page.status_code == 200 and phone_page.status_code == 200
    assert 'class="phone-tabbar"' in phone_page.text and "phone-home-hero" in phone_page.text
    assert phone_reads <= PHONE_HOME_BUDGET, f"phone Home ran {phone_reads} SELECT statements"
    assert phone_reads < pc_reads * 0.8


# The budget the older phone Overview met after B1 (244 reads, measured 2026-10-28); Home stays under it.
PHONE_HOME_BUDGET = 260


def test_the_category_look_up_reads_once_for_every_name(c, monkeypatch):
    _history(c, monkeypatch)
    names = c.counterparties.search_names()
    assert len(names) >= 3
    expected = {}
    for name in names:  # the old name-by-name answer
        expected[name] = counterparty_category_map(c, [name])[name]
    found, reads = _reads(c, monkeypatch, lambda: counterparty_category_map(c, names))
    assert found == expected
    assert reads <= 12, f"{reads} reads for {len(names)} names"


def test_quick_add_saves_once_however_often_it_is_sent(c, monkeypatch):
    _history(c, monkeypatch)
    app = web.create_app(c)
    wallet = next(a for a in c.accounts.list() if a.name == "Cash wallet")
    with TestClient(_as_phone(app)) as phone:
        form = {"account_id": str(wallet.id), "amount": "85", "counterparty": "Kiosk",
                "date": "2026-10-02", "submission": "a"*32}
        first = phone.post("/accounts/quick-add", data=form)
        again = phone.post("/accounts/quick-add", data=form)
        remembered = phone.post("/accounts/quick-add", data={"amount": "20", "counterparty": "Kiosk", "submission": "b"*32})
        refused = phone.post("/accounts/quick-add", data={"account_id": str(wallet.id), "amount": "0",
                                                          "submission": "c"*32})
    assert first.status_code == 200 and first.json()["ok"] and not first.json()["repeat"]
    assert again.json()["id"] == first.json()["id"] and again.json()["repeat"]
    assert remembered.json().get("account_id") == wallet.id, remembered.json()  # no account sent: the last one used
    assert refused.status_code == 422 and not refused.json()["ok"]


def test_an_overview_period_link_reads_money_s_report(c, monkeypatch):
    """3AY10: the older phone Overview and its folds are gone. A period link to / goes to Money's report."""
    _history(c, monkeypatch)
    from lightning.ui.phone.router import mount_phone
    app = web.create_app(c)
    mount_phone(app)
    with TestClient(_as_phone(app)) as phone:
        moved = phone.get("/?period=ytd", follow_redirects=False)
        fold = phone.get("/overview/fold/trend")
    assert moved.status_code in (302, 303) and moved.headers["location"] == "/money/report?period=ytd"
    assert fold.status_code == 404


def test_swipe_delete_hears_a_refusal_instead_of_following_the_redirect(c):
    """The phone's swipe posts with X-Requested-With: fetch; a refused delete is a 409 with the reason, not a 200 page."""
    bank = c.account_flows.open_account("CIB", "BANK", "2026-01-01", "1000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    spent = c.transactions.record_outflow("2026-02-01", bank.id, "100", food.id, counterparty="Carrefour")
    opening = next(r["id"] for r in c.db.all("SELECT id FROM transactions WHERE id != ? ORDER BY id", (spent.id,)))
    client = TestClient(web.create_app(c))
    client.get("/")
    fetch = {"X-Requested-With": "fetch"}
    refused = client.post(f"/transactions/{opening}/delete", headers=fetch)
    assert refused.status_code == 409 and refused.text
    deleted = client.post(f"/transactions/{spent.id}/delete", headers=fetch)
    assert deleted.status_code == 200 and deleted.text == "Deleted."
    assert client.post(f"/transactions/{spent.id}/restore", headers=fetch).status_code == 200


def test_pasted_sms_with_an_impossible_clock_is_no_amount_not_an_error(c, monkeypatch):
    import lightning.ui.routes.sms as sms

    def bad_clock(text):
        raise ValueError("hour must be in 0..23")  # what a bank's "الساعه 29:13" gives the parser
    monkeypatch.setattr(sms, "parse_sms", bad_clock)
    client = TestClient(web.create_app(c))
    client.get("/")
    assert client.post("/sms/read-one", data={"text": "x"}).status_code == 422
