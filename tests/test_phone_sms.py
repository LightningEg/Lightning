"""From SMS on the phone (IV-3AN, 3AN5): Paste SMS in the Add sheet asks for no account; the page has a back, one line of help
and its Primary; More lists places, not actions. The sheet itself is in test_phone_capture.py."""
from __future__ import annotations

import re

from test_phone_capture import _phone, month  # noqa: F401  (the fixture and the phone client)
from lightning.database.currencies import CurrencyRegistry
from lightning.sms_imports import fingerprint


def test_a_sheet_filled_from_an_sms_remembers_the_ending_and_marks_the_message_read(month):
    c, accounts, cats = month
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{accounts['cib'].id}/transaction/new").text
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    message = ("تم سحب مبلغ  EGP 5000.00  من بطاقة الخصم المباشر المنتهية بـ **7351 من CIB KZ IRAN ZAMALEK "
               "في 04/10/26 19:28 ، الرصيد المتاح EGP 12904.50")
    read = phone.post("/sms/read-one", data={"__session": session, "text": message}).json()
    assert read["ending"] == "7351" and read["account_id"] is None                  # an ending not seen before: asked once
    assert read["fingerprint"] == fingerprint(message) and read["amount"] == "5000.00"
    phone.post(f"/accounts/{accounts['cib'].id}/transaction/new", data={
        "__session": session, "kind": "out", "amount": "5000", "category_id": str(cats["EXP.PERSONAL.FOOD"].id),
        "counterparty": read["counterparty"], "date": "2026-10-04", "return_to": "/",
        "sms_ending": "7351", "sms_fp": read["fingerprint"]})
    again = phone.post("/sms/read-one", data={"__session": session, "text": message}).json()
    assert again["account_id"] == accounts["cib"].id                                # said once, remembered
    assert fingerprint(message) in c.sms_imports._json("sms_seen", [])               # the phone's inbox will not offer it again


def test_an_sms_for_a_foreign_account_is_not_remembered(month):
    """Bank SMS are EGP: an ending is never tied to an account in another currency."""
    c, accounts, _ = month
    CurrencyRegistry(c.db).register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    usd = c.account_flows.open_account("USD savings", "BANK", "2026-09-01", "100", currency="USD")
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{usd.id}/transaction/new").text
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    category = re.search(r'<option value="(\d+)" data-movement="OUTFLOW"', sheet).group(1)
    saved = phone.post(f"/accounts/{usd.id}/transaction/new", data={
        "__session": session, "kind": "out", "amount": "5", "category_id": category, "date": "2026-09-14",
        "return_to": "/", "sms_ending": "4242"})
    assert saved.status_code == 200 and "Saved OUT" in saved.text
    assert c.sms_imports.account_for("4242") is None




def test_from_sms_has_a_back_one_line_of_help_and_its_primary_on_the_page(month):
    c, _, _ = month
    page = _phone(c).get("/sms").text
    assert 'class="phone-back" href="/more"' in page and "card phone-card" not in page
    assert 'class="btn primary phone-save"' in page and "Paste one or more, a blank line between each." in page
    assert "CIB and NBE are read today" not in page


def test_more_lists_places_not_actions(month):
    c, _, _ = month
    page = _phone(c).get("/more").text
    assert 'href="/sms"' not in page and 'href="/needs-you"' not in page          # From SMS lives in Add; Needs you on Overview
    assert 'href="/settings"' in page and 'href="/rules"' in page


