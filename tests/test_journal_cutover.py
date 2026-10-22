from types import SimpleNamespace

import pytest

from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.cutover import _normalize_legacy_references, begin
from test_journal_finance import devices


class LegacyDatabase:
    def has_table(self, name):
        return False


def test_cutover_requires_explicit_decision_for_an_active_legacy_lend():
    with pytest.raises(JournalError, match="stranded copy"):
        begin(SimpleNamespace(db=LegacyDatabase()), None, None, legacy_state="LENT")


def test_upgrade_barrier_blocks_new_proposals_and_confirmation(devices):
    from test_journal_finance import groups

    home, pc = devices
    wire = pc.save(groups(pc))
    with home.store.db.transaction():
        home.store.db.execute("INSERT INTO journal_local VALUES('upgrade_barrier','{}')")
    with pytest.raises(JournalError, match="upgrade"):
        home.home.receive(wire)
    with pytest.raises(JournalError, match="upgrade"):
        home.home.process()


@pytest.mark.parametrize("state", ["RETURN_RECEIVED", "NEEDS_REPAIR", "damaged"])
def test_cutover_refuses_unfinished_or_uncertain_legacy_state(state):
    with pytest.raises(JournalError, match="finish or be explicitly retained"):
        begin(SimpleNamespace(db=LegacyDatabase()), None, None, legacy_state=state,
              retain_stranded=True)


def test_cutover_portabilizes_legacy_budget_category_settings(c, setup):
    import json
    from lightning.sync.journal.areas.workflows import JournalWorkflowService

    _, categories = setup
    category = categories["EXP.PERSONAL.FOOD"]
    c.budgets.set_budget(category.id, "2026-10", "100")
    c.settings.set("budget_tracked_categories", json.dumps([category.id]))
    c.settings.set("budget_income_categories", json.dumps([categories["EXP.WORK.SALARY"].id]))
    c.settings.set("budget_one_off_exclusions", json.dumps([category.id]))
    c.settings.set("budget_suppressed_categories", json.dumps({str(category.id): "2026-10"}))
    c.settings.set("budget_bulk_undo", json.dumps({
        "token": "legacy-undo", "month": "2026-10", "category_ids": [category.id],
        "rows": [{"id": 99, "category_id": category.id, "month": "2026-10", "one_off": 1,
                  "amount_e6": 25_000_000, "created_at": "created", "updated_at": "updated",
                  "average_months": 3, "income_percent_e6": None}],
    }))

    assert _normalize_legacy_references(c.db)
    assert json.loads(c.settings.get("budget_tracked_categories")) == [category.code]
    assert json.loads(c.settings.get("budget_income_categories")) == [categories["EXP.WORK.SALARY"].code]
    assert json.loads(c.settings.get("budget_one_off_exclusions")) == [category.code]
    assert json.loads(c.settings.get("budget_suppressed_categories")) == {category.code: "2026-10"}
    undo = json.loads(c.settings.get("budget_bulk_undo"))
    assert undo["category_codes"] == [category.code]
    assert "category_ids" not in undo and "id" not in undo["rows"][0]
    assert undo["rows"][0]["category_code"] == category.code
    assert undo["after_fingerprint"] == JournalWorkflowService(c).bulk_budget_fingerprint([category.id])
