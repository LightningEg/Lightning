"""IV-12AA5: with three or more late payments Cash planning offers one Catch up: each late bill in turn, paid (the
pay page, a matching payment first) or not yet, then a summary with Undo. The ledger and Due before payday move by
exactly the paid ones (its "already late" part: a late payment is not in the figure itself)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal as D
from urllib.parse import unquote

from fastapi.testclient import TestClient

from lightning.planning.bill_state import late_payments
from lightning.ui.web import create_app

DAY = date(2026, 9, 30)


def _bank(c, account):
    return c.reporting.account_balance(account.id, DAY)


def test_three_late_bills_walk_through_and_move_by_the_paid_ones(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    accounts, cats = setup
    bank = accounts["cib"]
    bills = str(next(cat for code, cat in cats.items() if code.startswith("EXP")).id)
    c.planning.create(kind="INCOME", name="Salary", amount="20000", frequency="MONTHLY", start_date="2026-10-25",
                      account_id=str(bank.id))
    for name, amount, start in (("Electricity", "480", "2026-09-20"), ("Internet", "350", "2026-09-22"),
                                ("Water", "120", "2026-09-24")):
        c.planning.create(kind="BILL", name=name, amount=amount, frequency="MONTHLY", start_date=start,
                          account_id=str(bank.id), category_id=bills)
    with TestClient(create_app(c)) as client:
        _walk(c, client, bank)


def _walk(c, client, bank):
    plan = client.get("/plan").text
    needs = plan.split('<section class="needs"', 1)[1].split("</section>", 1)[0]
    assert "3 payments are late" in needs and 'href="/plan/catch-up"' in needs and "Mark paid" not in needs
    before_bank, before_due = _bank(c, bank), c.forecaster.forecast(DAY).payments_before_income_total
    late_before = c.planning.still_owed_in_base(late_payments(c.planning, DAY), DAY)

    page = client.get("/plan/catch-up")
    assert page.status_code == 200 and "Late payment 1 of 3" in page.text and "Electricity" in page.text
    for amount, paid in (("480", True), ("350", False), ("120", True)):
        step = page.text
        if paid:
            pay = unquote(re.search(r'class="btn primary" href="([^"]+)"', step).group(1)).replace("&amp;", "&")
            item_id, due = re.search(r"/plan/items/(\d+)/pay\?due=([\d-]+)", pay).groups()
            back = pay.split("back=", 1)[1]
            done = client.post(f"/plan/items/{item_id}/pay", data={
                "due": due, "back": back, "outcome": "record", "date_paid": "2026-09-30", "amount": amount,
                "account_id": str(bank.id)})
            page = done
        else:
            later = re.search(r'class="btn" href="([^"]+)">Not yet', step).group(1).replace("&amp;", "&")
            page = client.get(later)
        assert page.status_code == 200
    summary = page.text.split('id="catch-up-summary"', 1)[1]
    assert "Marked paid · 600" in summary and "Internet" in summary.split("Not paid yet", 1)[1]
    assert _bank(c, bank) == before_bank - D("600")
    # Due before payday's "already late" part moves by exactly the paid ones; payments not yet due stay as they were
    assert c.planning.still_owed_in_base(late_payments(c.planning, DAY), DAY) == late_before - D("600") == D("350")
    assert c.forecaster.forecast(DAY).payments_before_income_total == before_due
    undo = re.search(r'action="/history/undo">.*?name="group_id" value="([^"]+)"', summary, re.S)
    assert undo
    client.post("/history/undo", data={"group_id": undo.group(1)})
    assert _bank(c, bank) == before_bank - D("480")                    # Undo takes back the last one (Water 120)


def test_two_late_bills_keep_their_own_rows(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    accounts, _ = setup
    for name, start in (("Electricity", "2026-09-20"), ("Internet", "2026-09-22")):
        c.planning.create(kind="BILL", name=name, amount="100", frequency="MONTHLY", start_date=start,
                          account_id=str(accounts["cib"].id))
    plan = TestClient(create_app(c)).get("/plan").text
    needs = plan.split('<section class="needs"', 1)[1].split("</section>", 1)[0]
    assert "Electricity is late" in needs and "/plan/catch-up" not in needs


def test_the_catch_up_pages_are_arabic(c, setup, monkeypatch):
    from tests.test_arabic_no_english import _english
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    accounts, cats = setup
    bills = str(cats["EXP.PERSONAL.FOOD"].id)
    for name, start in (("Electricity", "2026-09-20"), ("Internet", "2026-09-22"), ("Water", "2026-09-24")):
        c.planning.create(kind="BILL", name=name, amount="100", frequency="MONTHLY", start_date=start,
                          account_id=str(accounts["cib"].id), category_id=bills)
    with TestClient(create_app(c)) as client:
        client.post("/settings/locale", data={"locale": "ar"})
        names = {"Electricity", "Internet", "Water", "CIB Current", "EGP"}
        step = client.get("/plan/catch-up")
        main = step.text.split("<main", 1)[1].split("</main>", 1)[0]
        assert not _english("<main" + main, names)
        assert "/plan/catch-up" in client.get("/plan").text
        later = step.url.query.decode() if isinstance(step.url.query, bytes) else step.url.query
        start = re.search(r"start=([^&]+)", later).group(1)
        done = client.get(f"/plan/catch-up?start={start}&later={start}")
        main = done.text.split("<main", 1)[1].split("</main>", 1)[0]
        assert "catch-up-summary" in main and not _english("<main" + main, names)


def test_the_phone_sends_it_to_its_own_catch_up(c, setup, monkeypatch):
    from lightning.ui.phone.router import mount_phone
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    app = create_app(c)
    mount_phone(app)

    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    response = TestClient(phone_app).get("/plan/catch-up", follow_redirects=False)
    assert response.status_code in (302, 303) and response.headers["location"].startswith("/catch-up")
