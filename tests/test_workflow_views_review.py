from __future__ import annotations

import csv
from datetime import date
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import NotFoundError, ValidationError
from lightning.desktop.window import _origin, _safe_reminder_href
from lightning.ui.web import create_app
from lightning.workflows.reminders import ReminderService
from lightning.workflows.weekly import WeeklyReview
from lightning.workflows.review import ReviewInbox


def test_saved_view_date_presets_are_live_and_cover_boundaries(c):
    view = c.saved_views.normalize({"preset": "this_month"})
    assert c.saved_views.dates(view, date(2026, 1, 1)) == ("2026-01-01", "2026-01-31")
    assert c.saved_views.dates(view, date(2026, 12, 31)) == ("2026-12-01", "2026-12-31")
    assert c.saved_views.dates({"preset": "last_month"}, date(2026, 1, 1)) == ("2025-12-01", "2025-12-31")
    assert c.saved_views.dates({"preset": "year_to_date"}, date(2026, 12, 31)) == ("2026-01-01", "2026-12-31")
    custom = c.saved_views.normalize({"preset": "custom", "date_from": "2026-02-01", "date_to": "2026-02-28"})
    assert c.saved_views.dates(custom) == ("2026-02-01", "2026-02-28")


def test_saved_view_scope_filter_summary_and_csv_share_the_same_rows(c, setup):
    accounts, cats = setup
    cib, wallet = accounts["cib"].id, accounts["wallet"].id
    food = cats["EXP.PERSONAL.FOOD"].id
    first = c.transactions.record_outflow("2026-12-05", cib, "20", food, counterparty="Corner Shop",
                                          notes="Holiday #Trip")
    c.transactions.record_outflow("2026-11-05", cib, "30", food, counterparty="Corner Shop",
                                  notes="Holiday #trip")
    c.transactions.record_outflow("2026-12-06", cib, "40", food, counterparty="Corner Shop",
                                  notes="Holiday #other")
    c.transactions.record_outflow("2026-12-07", wallet, "50", food, counterparty="Corner Shop",
                                  notes="Holiday #trip")

    view_id = c.saved_views.save("December trip", {"preset": "custom", "date_from": "2026-12-01",
                                                     "date_to": "2026-12-31", "q": "Corner Shop",
                                                     "tag": "#TRIP", "category_id": str(food)}, cib)
    view = c.saved_views.get(view_id, cib)
    report = c.saved_views.report(view)
    assert [row.txn_id for row in report["rows"]] == [first.id]
    assert report["count"] == 1 and report["money_out"] == 20
    assert c.saved_views.rows(view) == report["rows"]
    with pytest.raises(NotFoundError):
        c.saved_views.get(view_id, wallet)
    with pytest.raises(NotFoundError):
        c.saved_views.get(view_id, None)

    client = TestClient(create_app(c))
    csv_response = client.get(f"/exports/views/{view_id}?account_id={cib}")
    assert csv_response.status_code == 200
    rows = list(csv.DictReader(StringIO(csv_response.text)))
    assert len(rows) == 1
    # User text is formula-safe; numeric cells remain usable as numbers.
    assert rows[0]["reference"] == first.ref and rows[0]["amount"] == "-20.00"
    assert client.get(f"/exports/views/{view_id}?account_id={wallet}").status_code == 404


def test_saved_view_all_time_scope_and_validation_limits(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    food = cats["EXP.PERSONAL.FOOD"].id
    old = c.transactions.record_outflow("2026-09-10", cib, "8", food)
    current = c.transactions.record_outflow("2026-12-10", cib, "9", food)
    view_id = c.saved_views.save("All activity", {"preset": "all_time"}, cib)
    result = c.saved_views.report(c.saved_views.get(view_id, cib))
    assert {row.txn_id for row in result["rows"]} >= {old.id, current.id}
    with pytest.raises(ValidationError):
        c.saved_views.save("bad", {"preset": "custom", "date_from": "2026-12-02", "date_to": "2026-12-01"})
    with pytest.raises(ValidationError):
        c.saved_views.save("x" * 65, {"preset": "all_time"})
    with pytest.raises(ValidationError):
        c.saved_views.get("0")


def test_weekly_completion_records_progress_without_dismissing_inbox(c, setup):
    accounts, _ = setup
    uncategorized = c.categories.get_by_code("EXP.UNACCOUNTED")
    c.transactions.record_outflow("2026-12-20", accounts["cib"].id, "14", uncategorized.id,
                                  allow_system_category=True)
    review = WeeklyReview(c)
    snapshot = review.snapshot()
    pending = [item for item in ReviewInbox(c).items(date(2026, 12, 31))
               if "no category" in item["label"]]
    assert pending
    review.complete(snapshot["token"])
    assert c.settings.get("weekly_review_at")
    assert [item["label"] for item in ReviewInbox(c).items(date(2026, 12, 31)) if "no category" in item["label"]]
    with pytest.raises(ValidationError, match="review changed"):
        review.complete("stale")


def test_weekly_rule_offers_need_repeated_same_corrections(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"].id
    utilities = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    ids = []
    for day in ("10", "11", "12"):
        txn = c.transactions.record_outflow(f"2026-12-{day}", accounts["cib"].id, "30", food,
                                            counterparty="Waterworks")
        ids.append(txn.id)
        c.transactions.update_money(txn.id, txn.date, accounts["cib"].id, "30", utilities,
                                    counterparty="Waterworks")
    offers = WeeklyReview(c).rule_offers()
    offer = next(item for item in offers if item["name"] == "Waterworks")
    assert offer["count"] == 3 and offer["category"] == c.categories.get(utilities).name


def test_rule_past_preview_applies_only_selected_rows_and_rejects_stale_fingerprint(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    food = cats["EXP.PERSONAL.FOOD"].id
    utilities = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    transactions = [c.transactions.record_outflow(f"2026-12-{day}", cib, "30", food,
                                                   counterparty="Waterworks")
                    for day in ("20", "21", "22")]
    rule_id = c.rules.save({"counterparty": "Waterworks", "counterparty_op": "is", "account_id": str(cib),
                            "direction": "out", "category_id": str(utilities)})
    changes = c.rules.past(rule_id)
    assert {change.id for change in changes} == {txn.id for txn in transactions}
    fingerprint = c.rules.past_token(rule_id, changes)
    changed, token = c.rules.apply_past(rule_id, [transactions[0].id], fingerprint)
    assert changed == 1 and token and c.transactions.get(transactions[0].id).lines[0].category_id == utilities
    assert all(c.transactions.get(txn.id).lines[0].category_id == food for txn in transactions[1:])

    with pytest.raises(ValidationError, match="preview changed"):
        c.rules.apply_past(rule_id, [transactions[1].id], fingerprint)


def test_reminders_are_opt_in_stable_and_read_only_safe(c):
    service = ReminderService(c)
    assert not service.enabled and service.due() == []
    c.settings.set("reminders_enabled", "1")
    assert service.enabled
    first, second = service.due(), service.due()
    assert first == second
    assert len({item["id"] for item in first}) == len(first)
    assert all(len(item["id"]) == 32 and item["href"].startswith("/") for item in first)
    c.db.read_only = True
    assert not service.enabled and service.due() == []
    c.db.read_only = False
    c.db._closed = True
    assert not service.enabled and service.due() == []
    c.db._closed = False


def test_reminder_ids_are_scoped_to_profile_and_local_day(c, monkeypatch):
    c.settings.set("reminders_enabled", "1")
    profile_a = "11111111-1111-4111-8111-111111111111"
    profile_b = "22222222-2222-4222-8222-222222222222"
    c.db.execute("INSERT OR REPLACE INTO profile_identity(singleton,profile_id) VALUES(1,?)", (profile_a,))
    service = ReminderService(c)
    first = service.due()
    assert first and first == service.due()

    c.db.execute("UPDATE profile_identity SET profile_id=? WHERE singleton=1", (profile_b,))
    other_profile = service.due()
    assert other_profile and {item["id"] for item in first}.isdisjoint(item["id"] for item in other_profile)

    monkeypatch.setattr("lightning.workflows.reminders.today", lambda: date(2027, 1, 1))
    other_day = service.due()
    assert {item["id"] for item in other_profile}.isdisjoint(item["id"] for item in other_day)


@pytest.mark.parametrize("href", [
    "https://example.com/steal", "//example.com/steal", "/\\\\example.com/steal", "\\\\example.com",
    " /review", "javascript:alert(1)",
])
def test_desktop_notification_rejects_untrusted_href(href):
    origin = "http://127.0.0.1:9000"
    assert _safe_reminder_href(href, origin, _origin(origin)) is None


def test_desktop_notification_keeps_valid_click_links_on_exact_loopback_origin():
    origin = "http://127.0.0.1:9000"
    allowed = _origin(origin)
    assert _safe_reminder_href("/review?tab=week", origin, allowed) == "http://127.0.0.1:9000/review?tab=week"
    assert _safe_reminder_href("/%2F%2Fevil.example", origin, allowed) == \
        "http://127.0.0.1:9000/%2F%2Fevil.example"
