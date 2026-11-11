"""Milestone 3: bank SMS read into the reviewed bank import (`lightning/sms_imports.py`).

Every sample in tests/fixtures/bank_sms.json is read and checked: inflow or outflow, kind, amount, the account's
ending, the date and time, and who or where. Then a batch goes through the bank import's review like a CSV."""
from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from lightning.sms_imports import SALARY_ENDING, parse_sms

SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "bank_sms.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", SAMPLES["samples"], ids=lambda s: f"{s['bank']}-{s['kind']}-{s['received']}")
def test_every_sample_reads_as_labelled(sample):
    found = parse_sms(sample["text"], sender=sample["sender"], received=datetime.fromisoformat(sample["received"]))
    assert found is not None, sample["text"]
    assert found.kind == sample["kind"] and found.bank == sample["bank"]
    assert found.inflow == (sample["direction"] == "inflow")
    for key, value in sample["expect"].items():
        got = getattr(found, key)
        assert (got == Decimal(value)) if key in ("amount", "balance") else (got == value), (key, got, value)


@pytest.mark.parametrize("text", SAMPLES["not_money"])
def test_codes_declines_and_offers_are_not_transactions(text):
    assert parse_sms(text) is None


def test_messages_go_to_review_once_and_each_ending_is_asked_once(c, setup):
    accounts, _ = setup
    picked = [s for s in SAMPLES["samples"] if s["bank"] == "NBE"]
    messages = [(s["sender"], s["text"], datetime.fromisoformat(s["received"])) for s in picked]
    first = c.sms_imports.read(messages)
    assert first["staged"] == {} and first["waiting"] == len(picked)  # endings unknown: nothing guessed
    endings = {group["ending"] for group in c.sms_imports.waiting()}
    assert endings == {"2093", "6628"}
    batch = c.sms_imports.assign("6628", accounts["cib"].id)
    _, rows = c.bank_imports.preview(batch)
    assert sorted(Decimal(r["Amount"]) for r in rows) == [Decimal("-10000.00"), Decimal("30.00"),
                                                          Decimal("700.00"), Decimal("4000.00")]
    assert {r["Reference"] for r in rows} >= {"517703926481"}
    again = c.sms_imports.read(messages)  # the inbox read again: nothing new
    assert again["staged"] == {} and again["skipped"] == len(picked)
    later = picked[0] | {"text": picked[0]["text"].replace("147.87", "99.10"), "received": "2026-10-07T08:00"}
    assert c.sms_imports.read([(later["sender"], later["text"], datetime(2026, 10, 7, 8))])["waiting"] == 8  # still asks for 2093


def test_cash_withdrawal_is_a_transfer_and_salary_has_its_own_choice(c, setup):
    accounts, _ = setup
    cib = [s for s in SAMPLES["samples"] if s["bank"] == "CIB"]
    c.sms_imports.read([(s["sender"], s["text"], datetime.fromisoformat(s["received"])) for s in cib])
    assert {g["ending"] for g in c.sms_imports.waiting()} == {"7351", "4410", SALARY_ENDING}
    _, rows = c.bank_imports.preview(c.sms_imports.assign("7351", accounts["cib"].id))
    assert rows[0]["Category"] == "Transfer" and "transfer to Wallet" in rows[0]["Notes"]
    _, rows = c.bank_imports.preview(c.sms_imports.assign(SALARY_ENDING, accounts["cib"].id))
    assert rows[0]["Amount"] == "19584.66" and rows[0]["Category"] == "Salary"


def test_paste_then_say_the_account_then_review(c, setup, tmp_path):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c))
    nbe = [s["text"] for s in SAMPLES["samples"] if s["bank"] == "NBE" and s["kind"] == "purchase"][:2]
    page = client.post("/sms/paste", data={"messages": "\n\n".join(nbe)})
    assert "2 need their account" in page.text and "Card ending 2093" in page.text
    review = client.post("/sms/assign", data={"ending": "2093", "account_id": str(accounts["cib"].id)})
    assert "/import/" in str(review.url) and "Uber" in review.text


def test_every_ending_is_asked_in_one_form_with_its_likely_account_chosen(c, setup):
    """IV-3AU S1: one question for every card ending, one Primary; the bank that sent a message picks its account
    when it has only one there, and an ending another bank's card has is never guessed."""
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c))
    picked = [s for s in SAMPLES["samples"] if s["bank"] == "NBE"]
    c.sms_imports.read([(s["sender"], s["text"], datetime.fromisoformat(s["received"])) for s in picked])
    page = client.get("/sms").text
    assert page.count('action="/sms/assign"') == 1 and page.count("btn primary") == 2  # Review N, and Read them
    assert "Save and review" in page  # an ending with no likely account: the button promises no count
    assert all(g["guess"] is None for g in [g | {"guess": c.sms_imports.guess(g["ending"], g["banks"])}
                                            for g in c.sms_imports.waiting()])  # NBE messages, only a CIB account
    cib = [s for s in SAMPLES["samples"] if s["bank"] == "CIB"][:1]
    c.sms_imports.read([(s["sender"], s["text"], datetime.fromisoformat(s["received"])) for s in cib])
    ending = parse_sms(cib[0]["text"], sender=cib[0]["sender"]).ending
    assert c.sms_imports.guess(ending, ["CIB"]) == accounts["cib"].id
    assert f'value="{accounts["cib"].id}" selected' in client.get("/sms").text
    answer = {f"account_{g['ending']}": str(accounts["cib"].id) for g in c.sms_imports.waiting()}
    review = client.post("/sms/assign", data=answer)
    assert "/import/" in str(review.url) and c.sms_imports.waiting() == []  # all of them, in one review


def test_an_ending_whose_last_four_are_saved_on_the_account_is_chosen(c, setup):
    accounts, _ = setup
    c.db.execute("UPDATE accounts SET last4='7351' WHERE id=?", (accounts["cib"].id,))
    assert c.sms_imports.guess("7351", []) == accounts["cib"].id


def test_an_atm_withdrawal_goes_to_the_wallet_cash_usually_goes_to(c, setup):
    """IV-3AU S3: with two wallets the withdrawal used to reach review with no account and a red error."""
    accounts, _ = setup
    f = c.account_flows
    f.open_account("Vodafone Cash", "CASH", "2026-09-01", "0")
    c.db.execute("UPDATE accounts SET last4='7351' WHERE id=?", (accounts["cib"].id,))
    assert c.sms_imports._cash_account_name() == ""  # nothing says yet: the review asks
    c.transactions.record_transfer("2026-09-05", accounts["cib"].id, accounts["wallet"].id, "1000")
    assert c.sms_imports._cash_account_name() == "Wallet"
    atm = next(s for s in SAMPLES["samples"] if s["kind"] == "withdrawal")
    c.sms_imports.read([(atm["sender"], atm["text"], datetime.fromisoformat(atm["received"]))])
    batch = c.sms_imports.assign(parse_sms(atm["text"], sender=atm["sender"]).ending, accounts["cib"].id)
    _, rows = c.bank_imports.preview(batch)
    assert rows[0]["_transfer_target"] == "Wallet" and not rows[0]["_needs_account"]


@pytest.mark.parametrize("sample", SAMPLES["reworded"], ids=lambda s: s["why"])
def test_a_reworded_message_is_still_read_and_flagged_to_check(sample):
    found = parse_sms(sample["text"], received=datetime(2026, 10, 7, 13))
    assert found is not None and found.inflow == (sample["direction"] == "inflow")
    for key, value in sample["expect"].items():
        got = getattr(found, key)
        assert (got == Decimal(value)) if key == "amount" else (got == value), (key, got, value)


def test_money_no_rule_reads_is_kept_for_the_owner_never_dropped(c, setup):
    text = SAMPLES["unreadable"][0]
    assert parse_sms(text) is None
    result = c.sms_imports.read([("NBE", text, datetime(2026, 10, 7, 13))])
    assert result["unread"] == 1 and c.sms_imports.unread()[0]["text"] == text
    c.sms_imports.dismiss(c.sms_imports.unread()[0]["id"])
    assert c.sms_imports.unread() == []


def test_from_sms_shows_what_it_could_not_read(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    page = client.post("/sms/paste", data={"messages": SAMPLES["unreadable"][0]})
    assert "1 kept for you" in page.text and "Messages kept for you" in page.text
    enter = c.sms_imports.unread()[0]
    from lightning.sms_imports import prefill
    assert prefill(enter["text"])["amount"] == "900.00" and prefill(enter["text"])["kind"] == "out"
    assert "amount=900.00" in page.text and "sms_fp=" in page.text  # Enter it opens Add filled from the message
    c.sms_imports.mark_seen(enter["id"].split("@")[0])  # saving that entry takes it off From SMS
    assert c.sms_imports.unread() == []


class FakeSource:
    """The phone's inbox, as lightning_android.AndroidSms gives it."""

    def __init__(self, inbox, permission="granted"):
        self.inbox, self.state, self.asked, self.shared = inbox, permission, 0, []

    def permission(self):
        return self.state

    def request(self):
        self.asked += 1

    def since(self, after_ms):
        return [m for m in self.inbox if m[2] > after_ms]

    def take_shared(self):
        texts, self.shared = self.shared, []
        return texts


def _ms(text):
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def test_the_phone_inbox_is_read_once_and_people_are_never_read(c, setup):
    nbe = [s for s in SAMPLES["samples"] if s["bank"] == "NBE"]
    inbox = [("NBE", s["text"], _ms(s["received"])) for s in nbe]
    inbox.append(("+201001234567", nbe[0]["text"].replace("147.87", "60.00"), _ms("2026-10-06T12:00")))  # a person
    source = FakeSource(inbox)
    first = c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 9))
    assert first["waiting"] == len(nbe)  # within 30 days, people's numbers skipped
    assert c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 10)) is None  # nothing new since
    source.inbox.append(("NBE", nbe[0]["text"].replace("147.87", "77.00"), _ms("2026-10-07T09:30")))
    source.shared.append(SAMPLES["samples"][0]["text"])
    later = c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 11))
    assert later["waiting"] == len(nbe) + 2


def test_without_permission_only_shared_messages_are_read(c, setup):
    source = FakeSource([("NBE", SAMPLES["samples"][6]["text"], _ms("2026-10-06T11:14"))], permission="not_granted")
    assert c.sms_imports.read_source(source) is None
    source.shared.append(SAMPLES["samples"][6]["text"])
    assert c.sms_imports.read_source(source)["waiting"] == 1


def test_the_phone_app_asks_then_reads_in_to_review(tmp_path):
    from fastapi.testclient import TestClient
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Credentials
    from test_profile_app import create, token
    nbe = [s for s in SAMPLES["samples"] if s["bank"] == "NBE"][:3]
    source = FakeSource([("NBE", s["text"], int(datetime.now().timestamp() * 1000) - i) for i, s in enumerate(nbe)],
                        permission="not_granted")
    cfg = Credentials("http://127.0.0.1:9851")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True, sms=source)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as phone:
        phone.get("/__launch", params={"code": cfg.launch_code})
        create(phone)
        from test_devices_app import add_account
        add_account(phone, "NBE current")
        page = phone.get("/sms").text
        assert "Allow reading SMS" in page and "never from people" in page
        main = page[page.index("<main"):] if "<main" in page else page
        # NF-11B2 (Play's SMS policy): the disclosure and its Allow come before anything else on the page.
        assert main.index("never from people") < main.index("Allow reading SMS") < main.index('name="messages"')
        phone.post("/sms/allow", data={"__session": token(page, "__session")})
        assert source.asked == 1
        source.state = "granted"
        phone.get("/")   # opening Home reads what arrived (3AY6); the waiting message is then a To review card (3AY8)
        review = phone.get("/activity?tab=review").text
        assert "Bank SMS need their account" in review


def test_a_duplicate_waiting_in_another_review_is_flagged(c, setup):
    accounts, _ = setup
    uber = SAMPLES["samples"][6]
    c.bank_imports.stage(accounts["cib"].id, "statement.csv",
                         b"Date,Counterparty,Amount\n2026-10-06,Uber,-147.87\n")
    c.sms_imports.read([(uber["sender"], uber["text"], datetime.fromisoformat(uber["received"]))])
    _, rows = c.bank_imports.preview(c.sms_imports.assign("2093", accounts["cib"].id))
    assert rows[0]["_pending_elsewhere"] == "statement.csv" and rows[0]["_default_match"] == "skip"


def test_a_transfer_between_your_banks_goes_to_review_once(c, setup):
    accounts, _ = setup
    nbe = c.account_flows.open_account("NBE Current", "BANK", "2026-09-01", "0", institution="NBE")
    c.sms_imports.assign("4410", accounts["cib"].id)
    c.sms_imports.assign("6628", nbe.id)
    sent = [s for s in SAMPLES["samples"] if s["bank"] == "CIB" and s["kind"] == "transfer_out"][0]
    arrived = ("تم إضافة تحويل لحظي لحسابكم رقم 6628 بمبلغ 2000.00 جم من MOHAB رقم مرجعي 4411 يوم 10-01 "
               "الساعة 11:06 للمزيد اتصل بـ 19623")
    result = c.sms_imports.read([("CIB", sent["text"], datetime(2026, 10, 1, 11, 6)),
                                 ("NBE", arrived, datetime(2026, 10, 1, 11, 7))])
    assert list(result["staged"]) == [accounts["cib"].id]  # one review row, not income on NBE as well
    _, rows = c.bank_imports.preview(result["staged"][accounts["cib"].id])
    assert rows[0]["Category"] == "Transfer" and rows[0]["_transfer_target"] == "NBE Current"
    kept = c.sms_imports.unread()
    assert len(kept) == 1 and "other side of the transfer from CIB Current" in kept[0]["reason"]


# --- safety of a read (task 21): crash, equal messages, overlap ------------------------------------------------

NBE_BUY = next(s for s in SAMPLES["samples"] if s["bank"] == "NBE" and s["kind"] == "purchase")["text"]


def _rows(c) -> int:
    return c.db.scalar("SELECT COUNT(*) FROM bank_import_rows")


def _known(c, setup, ending="2093"):
    from lightning.sms_imports import ENDINGS_KEY
    c.settings.set(ENDINGS_KEY, json.dumps({ending: setup[0]["cib"].id}))


def test_a_crash_after_staging_leaves_nothing_half_written(c, setup, monkeypatch):
    _known(c, setup)
    messages = [("NBE", NBE_BUY.replace("147.87", f"{n}.00"), datetime(2026, 10, 6, 11, n)) for n in (10, 20)]
    real = c.sms_imports._stage
    state = {"hit": False}

    def stage_then_crash(*args, **kwargs):
        result = real(*args, **kwargs)
        state["hit"] = True
        raise RuntimeError("power cut")

    monkeypatch.setattr(c.sms_imports, "_stage", stage_then_crash)
    with pytest.raises(RuntimeError):
        c.sms_imports.read(messages)
    assert state["hit"] and _rows(c) == 0 and not c.settings.get("sms_seen")  # staged rows rolled back too
    monkeypatch.undo()
    assert c.sms_imports.read(messages)["staged"]
    assert _rows(c) == 2
    assert c.sms_imports.read(messages)["staged"] == {} and _rows(c) == 2


def test_assign_stages_and_leaves_the_waiting_list_together(c, setup, monkeypatch):
    c.sms_imports.read([("NBE", NBE_BUY, datetime(2026, 10, 6, 11, 14))])
    assert c.sms_imports.waiting()
    monkeypatch.setattr(c.settings, "set", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("power cut")))
    with pytest.raises(RuntimeError):
        c.sms_imports.assign("2093", setup[0]["cib"].id)
    monkeypatch.undo()
    assert _rows(c) == 0 and c.sms_imports.waiting()
    assert c.sms_imports.assign("2093", setup[0]["cib"].id) and _rows(c) == 1


def test_two_equal_purchases_in_the_inbox_are_both_read_but_a_repeat_is_not(c, setup):
    _known(c, setup)
    source = FakeSource([("NBE", NBE_BUY, _ms("2026-10-06T11:14")), ("NBE", NBE_BUY, _ms("2026-10-06T15:02"))])
    assert c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 9))["staged"]
    assert _rows(c) == 2
    source.inbox.append(("NBE", NBE_BUY, _ms("2026-10-06T15:02")))  # the same message again
    c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 10))
    assert _rows(c) == 2


def test_the_overlap_rereads_without_staging_twice_and_catches_a_late_message(c, setup):
    from lightning.sms_imports import LAST_READ_KEY
    _known(c, setup)
    first = _ms("2026-10-06T11:14")
    source = FakeSource([("NBE", NBE_BUY, first)])
    c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 9))
    assert c.settings.get(LAST_READ_KEY) == str(first) and _rows(c) == 1
    late = ("NBE", NBE_BUY.replace("147.87", "88.00"), first - 4 * 60 * 1000)  # delivered late, stamped earlier
    source.inbox.append(late)
    assert c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 10)) is not None
    assert _rows(c) == 2 and c.settings.get(LAST_READ_KEY) == str(first)  # cursor never moves back
    assert c.sms_imports.read_source(source, now=datetime(2026, 10, 7, 11))["staged"] == {} and _rows(c) == 2  # overlap, all seen


def test_a_pasted_message_and_the_same_one_from_the_inbox_are_read_once(c, setup):
    _known(c, setup)
    c.sms_imports.read([("", NBE_BUY, datetime(2026, 10, 6, 11, 14))])
    assert _rows(c) == 1
    c.sms_imports.read([("NBE", NBE_BUY, datetime(2026, 10, 6, 11, 14), _ms("2026-10-06T11:14"))])
    assert _rows(c) == 1
    other = NBE_BUY.replace("147.87", "9.00")  # inbox first, then pasted
    c.sms_imports.read([("NBE", other, datetime(2026, 10, 6, 12), _ms("2026-10-06T12:00"))])
    c.sms_imports.read([("", other, datetime(2026, 10, 7))])
    assert _rows(c) == 2


def test_an_old_format_seen_list_still_counts_as_text_read(c, setup):
    from lightning.sms_imports import SEEN_KEY, fingerprint
    _known(c, setup)
    c.settings.set(SEEN_KEY, json.dumps([fingerprint(NBE_BUY)]))
    result = c.sms_imports.read([("NBE", NBE_BUY, datetime(2026, 10, 6, 11, 14), _ms("2026-10-06T11:14"))])
    assert result["staged"] == {} and result["skipped"] == 1 and _rows(c) == 0


def test_egp_sms_cannot_be_assigned_or_staged_as_dollars(c, setup):
    from lightning.core.errors import ValidationError
    from lightning.sms_imports import ENDINGS_KEY
    c.currencies.register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    usd = c.account_flows.open_account("Dollar bank", "BANK", "2026-09-01", "0", currency="USD")
    c.sms_imports.read([("NBE", NBE_BUY, datetime(2026, 10, 6, 11, 14))])
    with pytest.raises(ValidationError, match="EGP account"):
        c.sms_imports.assign("2093", usd.id)
    assert _rows(c) == 0 and c.sms_imports.waiting()
    # An existing mapping from an older build is held for reassignment, preserving its native currency.
    c.settings.set(ENDINGS_KEY, json.dumps({"2093": usd.id}))
    later = NBE_BUY.replace("147.87", "99.10")
    result = c.sms_imports.read([("NBE", later, datetime(2026, 10, 7, 11, 14))])
    assert not result["staged"] and result["waiting"] == 2 and _rows(c) == 0
    assert c.sms_imports.assign("2093", setup[0]["cib"].id)
    assert _rows(c) == 2


@pytest.mark.parametrize("text", SAMPLES["offers"])
def test_offers_and_bundles_are_never_kept_as_bank_messages(c, setup, text):
    """Owner, 2026-11-01: Nawy and Vodafone offers were kept as "Messages kept for you"."""
    assert parse_sms(text) is None
    result = c.sms_imports.read([("Vodafone365", text, datetime(2026, 10, 23, 18))])
    assert result["unread"] == 0 and c.sms_imports.unread() == []


def test_a_wallet_receipt_and_a_payment_at_a_shop_named_maarad_are_still_kept():
    from lightning.sms_imports import looks_like_money
    assert looks_like_money("تم استلام مبلغ 500 جنيه من رقم 01000000000 في محفظتك. رصيدك الحالي 1200 جنيه")
    assert parse_sms("تم سداد مبلغ 320.50 جم باستخدام بطاقتكم رقم 2093 لدى معرض النور يوم 07/10/26") is not None


def test_offers_kept_before_the_filter_leave_the_list(c, setup):
    import json as _json
    from lightning.sms_imports import UNREAD_KEY
    kept = [{"id": "old", "sender": "Nawy Shares", "text": SAMPLES["offers"][0], "received": "2026-10-31T14:22"},
            {"id": "bank", "sender": "NBE", "text": SAMPLES["unreadable"][0], "received": "2026-10-07T13:00"}]
    c.settings.set(UNREAD_KEY, _json.dumps(kept))
    assert [m["id"] for m in c.sms_imports.unread()] == ["bank"]


def test_dismissing_two_from_a_sender_quiets_it_but_never_a_bank(c, setup):
    shop = "تم تنفيذ عملية بمبلغ {n}.00 جم على حسابكم"
    for n in (100, 200):
        c.sms_imports.read([("ShopPoints", shop.format(n=n), datetime(2026, 10, 7, 13, n // 100))])
    for message in c.sms_imports.unread():
        c.sms_imports.dismiss(message["id"])
    c.sms_imports.read([("ShopPoints", shop.format(n=300), datetime(2026, 10, 8, 9))])
    assert c.sms_imports.unread() == []  # quiet now
    # A sender that sent a message a rule read is a bank: dismissing its unreadable ones never quiets it.
    c.sms_imports.read([("NBE", SAMPLES["samples"][-1]["text"], datetime(2026, 10, 9, 9))])
    for n in (400, 500, 600):
        c.sms_imports.read([("NBE", shop.format(n=n), datetime(2026, 10, 9, 10, n // 100))])
        c.sms_imports.dismiss(c.sms_imports.unread()[0]["id"])
    c.sms_imports.read([("NBE", shop.format(n=700), datetime(2026, 10, 10, 9))])
    assert len(c.sms_imports.unread()) == 1


def test_pc_from_sms_links_back_to_accounts(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app

    page = TestClient(create_app(c)).get('/sms')
    assert page.status_code == 200
    assert '<a class="btn" href="/accounts">Accounts</a>' in page.text


def test_the_phone_asks_the_sms_provider_for_bank_senders_only():
    """NF-11B2: SmsBridge.since() filters people in the provider's query (Play's SMS policy), by the PERSON rule."""
    import sqlite3
    from lightning.sms_imports import PERSON
    java = (Path(__file__).resolve().parents[1]
            / "android/app/src/main/java/org/lightning/app/SmsBridge.java").read_text(encoding="utf-8")
    since = java[java.index("public static String since"):java.index("static void share")]
    assert '" > ? AND " + NOT_A_PERSON' in since
    def value(name, known):  # a Java constant made of "literals" + CONSTANTS, evaluated
        body = java[java.index(f"String {name} = ") + len(f"String {name} = "):]
        tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[A-Z_]+', body[:body.index(";")])
        return "".join(t[1:-1] if t.startswith('"') else known[t] for t in tokens)
    sql = value("NOT_A_PERSON", {"BARE": value("BARE", {})})
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE inbox (address TEXT)")
    senders = ["CIB", "NBE", "Banque Misr", "19623", "123456", "+201001234567", "01001234567", "+20 100 123 4567",
               "1234567", "", None, "QNB-AA", "+12", "12+34567890"]
    db.executemany("INSERT INTO inbox VALUES (?)", [(a,) for a in senders])
    kept = [row[0] for row in db.execute(f"SELECT address FROM inbox WHERE {sql}")]
    assert kept == [a for a in senders if not PERSON.match((a or "").replace(" ", ""))]


def test_arabic_decimal_and_thousands_marks_read_as_the_right_amount():
    """BT-7AI: ٫ is the decimal point and ٬ the thousands mark, not a separator that cuts the number."""
    from decimal import Decimal
    from lightning.sms_imports import parse_sms, prefill
    tx = parse_sms("تم خصم ١٤٧٫٨٧ جم من بطاقة الخصم المباشر رقم ١٢٣٤ عند كارفور يوم ٠٦/١١/٢٦")
    assert tx is not None and tx.amount == Decimal("147.87")
    assert prefill("تم خصم ١٬٢٥٠٫٥٠ جم من حسابك")["amount"] == "1250.50"


R = datetime(2026, 11, 9, 14, 0)
# Common English wordings (r31 S5-S8): dummy text, not verified bank messages, so they read but say "check it".
ENGLISH_DEBIT = ("Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26 at 21:15. "
                 "Available balance EGP 10,200.50")
ENGLISH_CREDIT = ("Your credit card ending 5678 was used for EGP 1,250.00 at AMAZON.EG on 08/11 20:01. "
                  "Available limit EGP 38,750.00")


def test_english_card_messages_read_with_shop_date_and_ending():
    """NF-7AK1."""
    debit = parse_sms(ENGLISH_DEBIT, sender="CIB", received=R)
    assert (debit.kind, debit.amount, debit.ending, debit.place, debit.when) == (
        "purchase", Decimal("250.00"), "1234", "TALABAT", "2026-11-08T21:15")
    assert debit.balance == Decimal("10200.50") and not debit.sure
    credit = parse_sms(ENGLISH_CREDIT, sender="CIB", received=R)
    assert (credit.amount, credit.ending, credit.place, credit.when) == (
        Decimal("1250.00"), "5678", "AMAZON.EG", "2026-11-08T20:01")
    assert credit.balance is None  # an available limit is not money held
    assert parse_sms("Your card ending 1234 was charged USD 12.99 at NETFLIX.COM on 03/11/26", received=R) is None


def test_a_wallet_payment_and_receipt_share_one_key_and_stage_in_the_wallet(c, setup):
    """NF-7AK2: a wallet names no ending; its sender is the key, asked once like an ending."""
    from lightning.sms_imports import WALLET_PREFIX
    out = "تم دفع 150 جنيه من محفظتك فودافون كاش الى التاجر Koshary El Tahrir. رصيدك الحالي 3000 جنيه"
    got = "تم استلام مبلغ 500 جنيه من رقم 01001234567 على محفظتك. رصيدك 3500 جنيه"
    paid, received = parse_sms(out, sender="VF-Cash", received=R), parse_sms(got, sender="VF-Cash", received=R)
    assert paid.ending == received.ending == WALLET_PREFIX + "vfcash"
    assert (paid.signed, paid.place, received.signed) == (Decimal("-150"), "Koshary El Tahrir", Decimal("500"))
    assert parse_sms(out, received=R).ending == WALLET_PREFIX + "vodafonecash"  # pasted: the brand names it
    accounts, _ = setup
    first = c.sms_imports.read([("VF-Cash", out, R), ("VF-Cash", got, R)])
    assert first["waiting"] == 2 and {g["ending"] for g in c.sms_imports.waiting()} == {WALLET_PREFIX + "vfcash"}
    batch = c.sms_imports.assign(WALLET_PREFIX + "vfcash", accounts["wallet"].id)
    _, rows = c.bank_imports.preview(batch)
    assert sorted(Decimal(r["Amount"]) for r in rows) == [Decimal("-150"), Decimal("500")]


def test_prefill_reads_date_shop_and_foreign_currency():
    """IV-7AJ: a message no pattern read still gives its amount, its own day and the shop after "at"; a dollar purchase
    is kept for the person (looks like money), never read as pounds."""
    from lightning.sms_imports import looks_like_money, prefill

    card = "Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26"
    got = prefill(card)
    assert (got["amount"], got["kind"], got["date"], got["counterparty"], got["currency"]) == \
        ("250.00", "out", "2026-11-08", "TALABAT", "")
    usd = "Purchase: charged USD 12.99 at NETFLIX.COM"
    assert looks_like_money(usd)
    got = prefill(usd)
    assert (got["amount"], got["currency"], got["counterparty"]) == ("12.99", "USD", "NETFLIX.COM")


def test_read_one_falls_back_to_prefill(c, setup):
    """IV-7AJ: Paste SMS on the phone says "Check the account and who" instead of "No amount found"."""
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    r = client.post("/sms/read-one", data={"text": "Purchase: charged USD 12.99 at NETFLIX.COM on 08/11/26"})
    assert r.status_code == 200
    body = r.json()
    assert body["amount"] == "12.99" and body["currency"] == "USD" and body["date"] == "2026-11-08"
    assert body["counterparty"] == "NETFLIX.COM" and body["note"] == "Check the account and who."
    nothing = client.post("/sms/read-one", data={"text": "Hello there"})
    assert nothing.status_code == 422


def test_stated_balance_gap_is_one_quiet_row_that_clears(c, setup):
    """NF-7AP: a bank message's stated balance is compared with the ledger; a gap is one To do row, never an adjustment."""
    import json
    from datetime import date
    from lightning.sms_imports import STATED_KEY
    from lightning.workflows.review import ReviewInbox
    accounts, _ = setup
    cib = accounts["cib"]
    c.sms_imports.assign("7351", cib.id)
    withdrawal = [s for s in SAMPLES["samples"] if s["bank"] == "CIB" and "12904.50" in s["text"]][0]
    c.sms_imports.read([(withdrawal["sender"], withdrawal["text"], datetime.fromisoformat(withdrawal["received"]))])
    stated = json.loads(c.settings.get(STATED_KEY))[str(cib.id)]
    assert stated["balance"] == "12904.50"
    assert c.sms_imports.balance_gaps() == []        # its own rows still wait in review: the gap may be those
    c.settings.set(STATED_KEY, json.dumps({str(cib.id): {"date": "2026-09-30", "balance": "49650.00"}}))
    c.bank_imports.db.execute("DELETE FROM bank_import_rows")  # nothing waits any more
    gaps = c.sms_imports.balance_gaps()
    assert [(g["account_id"], g["difference"]) for g in gaps] == [(cib.id, Decimal("-350"))]
    rows = [i for i in ReviewInbox(c).items(date(2026, 10, 5)) if "off the bank's balance" in i["label"]]
    assert len(rows) == 1 and "350" in rows[0]["label"] and str(cib.id) in rows[0]["href"]
    c.settings.set(STATED_KEY, json.dumps({str(cib.id): {"date": "2026-09-30", "balance": "50000.00"}}))  # a later message agrees
    assert c.sms_imports.balance_gaps() == []
