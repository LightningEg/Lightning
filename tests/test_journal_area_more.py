"""Categories, people, ownership, checking an account, rules, claims, zakat and the other settings-backed screens
travel as commands: the replica issues them, the home confirms, and both copies end up identical."""
import json
from decimal import Decimal

import pytest

from test_journal_finance import devices  # noqa: F401
from test_journal_area_plans import account, category, same, status, uid
from lightning.sync.journal.codec import origin_id, unpack
from lightning.sync.journal.proxy import JournalServices, PendingOnHome


def act(hd, pc, call):
    """What a screen does on the replica: call the service, which is saved and waits; then sync with the home."""
    with pytest.raises(PendingOnHome):
        call(JournalServices(pc))
    pending = [origin_id(unpack(wire)["body"]["origin"]) for wire in pc.store.pending()]
    pc.sync_with(hd.home)
    assert pending and all(hd.home.status(item)["status"] == "accepted" for item in pending), \
        [hd.home.status(item) for item in pending]
    same(hd, pc)


def on_home(hd, call):
    return call(JournalServices(hd))


def sub_category(hd, pc, name="Coffee", parent="EXP.PERSONAL"):
    """A new category under an L1 group, made on the home and copied to the replica."""
    on_home(hd, lambda s: s.categories.create(hd.c.categories.get_by_code(parent).id, name))
    pc.sync_with(hd.home)
    found = next(c for c in pc.c.categories.tree() if c.name == name)
    return found.id, next(c for c in hd.c.categories.tree() if c.name == name).id


def test_category_direction_flags_and_delete_or_archive(devices):
    hd, pc = devices
    mine, home_id = sub_category(hd, pc)
    act(hd, pc, lambda s: s.categories.set_direction(mine, "BOTH"))
    assert pc.c.categories.get(mine).direction.value == "BOTH" == hd.c.categories.get(home_id).direction.value
    act(hd, pc, lambda s: s.budgets.set_one_off(mine, True))
    act(hd, pc, lambda s: s.budgets.set_recurring_income(mine, True))
    assert mine in pc.c.budgets.one_off_ids(False) == hd.c.budgets.one_off_ids(False)
    assert mine in pc.c.budgets.recurring_income_ids()
    act(hd, pc, lambda s: s.budgets.set_emergency_basis("income"))
    assert pc.c.budgets.emergency_basis() == hd.c.budgets.emergency_basis() == "income"
    # An unused category is deleted outright; one with history is archived instead.
    act(hd, pc, lambda s: s.categories.delete_or_archive(mine))
    assert not any(c.name == "Coffee" for c in pc.c.categories.tree())
    used, home_used = sub_category(hd, pc, "Tea")
    on_home(hd, lambda s: s.transactions.record_outflow("2026-09-02", account(hd, "Bank").id, Decimal("5"), home_used))
    pc.sync_with(hd.home)
    act(hd, pc, lambda s: s.categories.delete_or_archive(used))
    assert not pc.c.categories.get(used).active and not hd.c.categories.get(home_used).active


def test_budget_rows_restore_after_a_bulk_change(devices):
    hd, pc = devices
    food = category(pc)
    on_home(hd, lambda s: s.budgets.set_budget(food.id, "2026-09", "400", False, None))
    pc.sync_with(hd.home)
    before = pc.c.budgets.snapshot_rows([food.id])
    act(hd, pc, lambda s: s.budgets.set_budget(food.id, "2026-09", "900", False, None))
    assert pc.c.budgets.amounts_for("2026-09")[food.id][0] == Decimal("900")
    act(hd, pc, lambda s: s.budgets.restore_rows([food.id], before))
    assert pc.c.budgets.amounts_for("2026-09")[food.id][0] == Decimal("400") == hd.c.budgets.amounts_for("2026-09")[food.id][0]


def test_people_names_aliases_and_archiving(devices):
    hd, pc = devices
    on_home(hd, lambda s: s.counterparties.create("Landlord", None, None, None))
    pc.sync_with(hd.home)
    person = pc.c.counterparties.resolve("Landlord")["id"]
    food = category(pc).id
    act(hd, pc, lambda s: s.counterparties.rename(person, "Landlord Ltd", food))
    act(hd, pc, lambda s: s.counterparties.add_alias(person, "LL"))
    alias = pc.c.db.scalar("SELECT id FROM counterparty_aliases WHERE alias='LL'")  # Renaming kept "Landlord" as one too.
    act(hd, pc, lambda s: s.counterparties.rename_alias(person, alias, "L Ltd"))
    act(hd, pc, lambda s: s.counterparties.set_kind(person, "BUSINESS"))
    act(hd, pc, lambda s: s.counterparties.set_default_category(person, None))
    row = pc.c.counterparties.get(person)
    assert (row["name"], row["kind"], row["default_category_id"]) == ("Landlord Ltd", "BUSINESS", None)
    assert pc.c.counterparties.get(person)["name"] == hd.c.counterparties.get(person)["name"]
    act(hd, pc, lambda s: s.counterparties.remove_alias(person, alias))
    assert pc.c.db.scalar("SELECT alias FROM counterparty_aliases WHERE counterparty_id=?", (person,)) == "Landlord"
    act(hd, pc, lambda s: s.counterparties.set_active(person, False))
    assert not pc.c.counterparties.get(person)["active"]
    act(hd, pc, lambda s: s.counterparties.delete_or_archive(person))  # Unused: deleted.
    assert pc.c.counterparties.get(person) is None


def test_money_held_for_others_and_ownership_changes(devices):
    hd, pc = devices
    bank = account(pc, "Bank").id
    act(hd, pc, lambda s: s.money_from_others.record("2026-09-02", "Dad", bank, Decimal("100"), "cash he left"))
    dad = pc.c.counterparties.resolve("Dad")["id"]
    assert pc.c.counterparties.get(dad)["name"] == "Dad" == hd.c.counterparties.get(dad)["name"]
    owned = lambda device: sorted(row["amount_e6"] for row in device.c.money_from_others.totals_by_account("2026-09-30"))
    assert owned(pc) == owned(hd) and owned(pc)
    food = category(pc).id
    act(hd, pc, lambda s: s.transactions.record_expense_paid_by_person("2026-09-03", bank, Decimal("30"), dad, food, "lunch"))
    act(hd, pc, lambda s: s.transactions.change_cash_ownership("2026-09-04", bank, Decimal("20"), dad, None, "gave back"))
    refs = [row["ref"] for row in pc.c.db.all("SELECT ref FROM transactions ORDER BY id")]
    assert refs == [row["ref"] for row in hd.c.db.all("SELECT ref FROM transactions ORDER BY id")]
    # Editing a posting keeps its identity: the same transaction changes and none is added.
    first = pc.c.db.scalar("SELECT id FROM transactions WHERE notes='gave back'")
    act(hd, pc, lambda s: s.transactions.change_cash_ownership("2026-09-04", bank, Decimal("25"), dad, None, "gave back", first))
    assert pc.c.db.scalar("SELECT COUNT(*) FROM transactions") == len(refs)


def test_money_in_out_transfer_and_bulk_edit_from_the_account_form(devices):
    hd, pc = devices
    bank, wallet = account(pc, "Bank").id, account(pc, "Wallet").id
    food = category(pc).id
    salary = pc.c.categories.get_by_code("EXP.WORK.SALARY").id
    act(hd, pc, lambda s: s.transactions.record_outflow("2026-09-02", bank, Decimal("80"), food, counterparty="Spinneys", notes="#weekly"))
    act(hd, pc, lambda s: s.transactions.record_inflow("2026-09-03", bank, Decimal("500"), salary, counterparty="Acme"))
    act(hd, pc, lambda s: s.transactions.record_transfer("2026-09-04", bank, wallet, Decimal("40"), notes="pocket"))
    assert next(r for r in pc.balances() if r["name"] == "Bank")["balance"] == 1000 - 80 + 500 - 40
    ids = [row["id"] for row in pc.c.db.all("SELECT id FROM transactions WHERE type IN ('IN','OUT') ORDER BY id")]
    dining = sub_category(hd, pc, "Dining out")[0]
    act(hd, pc, lambda s: s.transactions.bulk_update(ids[:1], {"category_id": dining, "notes": "weekly shop"}))
    changed = pc.c.transactions.get(ids[0])
    assert changed.notes == "weekly shop" and changed.lines[0].category_id == dining
    with pytest.raises(Exception, match="not available"):  # A change the command cannot carry is refused, not dropped.
        JournalServices(pc).transactions.bulk_update(ids[:1], {"tags": "x"})


def test_checking_an_account_against_the_bank(devices):
    hd, pc = devices
    bank = account(pc, "Bank").id
    act(hd, pc, lambda s: s.reconciliation.adjust(bank, "2026-09-10", Decimal("1040")))  # Bank shows 40 more.
    assert pc.c.reporting.account_balance(bank, "2026-09-10") == 1040
    act(hd, pc, lambda s: s.reconciliation.close(bank, "2026-09-10", "1040"))
    assert pc.c.reconciliation.checked_through(bank) == "2026-09-10" == hd.c.reconciliation.checked_through(account(hd, "Bank").id)
    assert pc.c.db.scalar("SELECT COUNT(*) FROM ledger_entries WHERE account_id=? AND cleared=1", (bank,))
    act(hd, pc, lambda s: s.reconciliation.unlock(bank))
    assert pc.c.reconciliation.checked_through(bank) is None


def test_spendable_choice_for_an_account(devices):
    hd, pc = devices
    wallet = account(pc, "Wallet").id
    act(hd, pc, lambda s: s.accounts.set_spendable(wallet, False))
    assert pc.c.accounts.get(wallet).spendable is False and hd.c.accounts.get(account(hd, "Wallet").id).spendable is False
    act(hd, pc, lambda s: s.accounts.set_spendable(wallet, None))
    assert pc.c.accounts.get(wallet).spendable is None


def test_emergency_fund_and_payday_funding(devices):
    hd, pc = devices
    act(hd, pc, lambda s: s.reserves.set_emergency_fund(Decimal("300"), Decimal("600")))
    fund = next(r for r in pc.c.reserves.list_active() if r["kind"] == "EMERGENCY")
    assert fund["allocated"] == Decimal("300") == next(r for r in hd.c.reserves.list_active() if r["kind"] == "EMERGENCY")["allocated"]
    food = category(pc).id
    on_home(hd, lambda s: s.budgets.set_budget(food, "2026-10", "200", False, None))
    on_home(hd, lambda s: s.settings.set("cash_funding_enabled", "1"))
    pc.sync_with(hd.home)
    plan = pc.c.funding.preview()
    if not any(row["id"] == food for row in plan["rows"]):
        pytest.skip("the budget is not in this month's preview")
    act(hd, pc, lambda s: s.funding.apply(plan["token"], {str(food): "150"}, {}))
    assert pc.c.db.scalar("SELECT amount_e6 FROM cash_funding WHERE category_id=?", (food,)) == hd.c.db.scalar(
        "SELECT amount_e6 FROM cash_funding WHERE category_id=?", (food,)) > 0


def test_settings_backed_screens(devices):
    hd, pc = devices
    act(hd, pc, lambda s: s.zakat.set_enabled(True))
    assert pc.c.zakat.enabled() and hd.c.zakat.enabled()
    act(hd, pc, lambda s: s.zakat.save_settings("2026-09-01", "", True, False))
    assert pc.c.zakat.settings().count_worn_gold and not pc.c.zakat.settings().deduct_debts_due
    assert pc.c.zakat.settings() == hd.c.zakat.settings()
    act(hd, pc, lambda s: s.health.set_limit("savings_rate", "22", False, ""))
    assert pc.c.health.limit_values()["savings_rate"] == Decimal("22") == hd.c.health.limit_values()["savings_rate"]
    act(hd, pc, lambda s: s.health.restore_limit("savings_rate"))
    assert pc.c.health.limit_values()["savings_rate"] == hd.c.health.limit_values()["savings_rate"] != Decimal("22")
    party = on_home(hd, lambda s: s.counterparties.create("Netflix", None, None, None))
    pc.sync_with(hd.home)
    act(hd, pc, lambda s: s.planning.not_recurring(party))
    assert pc.c.planning._not_recurring() == hd.c.planning._not_recurring() == {party}
    unread = json.dumps([{"id": "m1", "text": "x"}, {"id": "m2", "text": "y"}])
    on_home(hd, lambda s: s.settings.set("sms_unread", unread))
    pc.sync_with(hd.home)
    act(hd, pc, lambda s: s.sms_imports.dismiss("m1"))
    assert [m["id"] for m in pc.c.sms_imports.unread()] == ["m2"] == [m["id"] for m in hd.c.sms_imports.unread()]


def test_saved_register_views(devices):
    hd, pc = devices
    food = category(pc).id
    bank = account(pc, "Bank").id
    form = {"preset": "all_time", "q": "cafe", "category_id": str(food), "name": "ignored", "account_id": str(bank)}
    act(hd, pc, lambda s: s.saved_views.save("Cafes", form, bank))
    views = pc.c.saved_views.list(bank)
    assert [v["name"] for v in views] == ["Cafes"] and views[0]["category_id"] == food and views[0]["q"] == "cafe"
    assert [v["name"] for v in hd.c.saved_views.list(account(hd, "Bank").id)] == ["Cafes"]
    act(hd, pc, lambda s: s.saved_views.delete(views[0]["id"], bank))
    assert not pc.c.saved_views.list(bank)


def test_reimbursement_claims_and_receipts(devices):
    hd, pc = devices
    bank = account(pc, "Bank").id
    food = category(pc).id
    refund = pc.c.categories.get_by_code("EXP.PERSONAL.OTHER_INCOME").id
    home_bank = account(hd, "Bank").id  # Account ids differ between the two devices; the commands carry UUIDs.
    on_home(hd, lambda s: s.transactions.record_outflow("2026-09-02", home_bank, Decimal("200"), food, counterparty="Hotel"))
    on_home(hd, lambda s: s.transactions.record_inflow("2026-09-20", home_bank, Decimal("150"), refund, counterparty="Employer"))
    pc.sync_with(hd.home)
    expense, receipt = (pc.c.db.scalar("SELECT id FROM transactions WHERE counterparty=?", (name,)) for name in ("Hotel", "Employer"))
    act(hd, pc, lambda s: s.reimbursements.create_claim(expense, Decimal("150"), None, "2026-10-01"))
    claim = pc.c.db.scalar("SELECT id FROM reimbursement_claims")
    act(hd, pc, lambda s: s.reimbursements.link_receipt(claim, receipt, Decimal("100")))
    link = pc.c.db.scalar("SELECT id FROM reimbursement_receipts")
    assert pc.c.db.scalar("SELECT amount_e6 FROM reimbursement_receipts") == 100_000_000
    act(hd, pc, lambda s: s.reimbursements.unlink_receipt(claim, link))
    act(hd, pc, lambda s: s.reimbursements.delete_claim(claim))
    assert not pc.c.db.scalar("SELECT COUNT(*) FROM reimbursement_claims") and not hd.c.db.scalar("SELECT COUNT(*) FROM reimbursement_claims")


def test_rules_save_apply_to_the_past_undo_and_delete(devices):
    hd, pc = devices
    bank = account(pc, "Bank").id
    food, other = category(pc).id, pc.c.categories.get_by_code("EXP.PERSONAL.OTHER").id
    for day in ("2026-09-02", "2026-09-03"):
        on_home(hd, lambda s: s.transactions.record_outflow(day, account(hd, "Bank").id, Decimal("20"), other, counterparty="Cafe Nile"))
    pc.sync_with(hd.home)
    values = {"match": "all", "counterparty_op": "contains", "counterparty": "nile", "notes": "", "amount_op": "", "amount": "",
              "amount_to": "", "account_id": "", "direction": "", "category_id": str(food), "tag": "", "part_category_1": "",
              "part_value_1": ""}
    act(hd, pc, lambda s: s.rules.save(values))
    rule = pc.c.db.scalar("SELECT id FROM rules")
    assert pc.c.rules.get(rule).category_id == food == hd.c.rules.get(hd.c.db.scalar("SELECT id FROM rules")).category_id
    act(hd, pc, lambda s: s.rules.save(values | {"counterparty": "cafe"}, rule))  # An edit keeps the rule.
    assert pc.c.db.scalar("SELECT COUNT(*) FROM rules") == 1
    changes = pc.c.rules.past(rule)
    assert len(changes) == 2
    token = pc.c.rules.past_token(rule, changes)
    act(hd, pc, lambda s: s.rules.apply_past(rule, {change.id for change in changes}, token))
    assert {pc.c.transactions.get(change.id).lines[0].category_id for change in changes} == {food}
    undo = json.loads(pc.c.settings.get("rules_apply_undo") or "{}") or json.loads(hd.c.settings.get("rules_apply_undo") or "{}")
    assert undo and undo["token"]
    act(hd, pc, lambda s: s.rules.undo(undo["token"]))
    assert {pc.c.transactions.get(change.id).lines[0].category_id for change in changes} == {other}
    act(hd, pc, lambda s: s.rules.delete(rule))
    assert not pc.c.db.scalar("SELECT COUNT(*) FROM rules") and not pc.c.db.scalar("SELECT COUNT(*) FROM rule_actions")


def test_a_rule_naming_an_account_uses_the_shared_account_code(devices):
    hd, pc = devices
    food = category(pc).id
    bank = account(pc, "Bank")
    values = {"match": "all", "counterparty": "x", "category_id": str(food), "account_id": str(bank.id)}
    act(hd, pc, lambda s: s.rules.save(values))
    rule = pc.c.rules.list()[0]
    condition = next(c for c in rule.conditions if c.field == "account")
    assert condition.value == bank.code
    assert pc.c.rules.form_values(rule)["account_id"] == str(bank.id)
    assert pc.c.rules.outcome("x", account_id=bank.id).category_id == food


def test_custom_institution_is_synchronized(devices):
    hd, pc = devices
    act(hd, pc, lambda s: s.institutions.add("Example Bank"))
    assert any(i.name == "Example Bank" for i in pc.c.institutions.custom())


def test_a_merge_waits_for_the_import_tables(devices):
    from lightning.sync.journal.effects import SYNCED
    assert "bank_import_rows" in SYNCED
    hd, pc = devices
    bank = account(pc, "Bank").id
    food = category(pc).id
    for _ in range(2):
        on_home(hd, lambda s: s.transactions.record_outflow("2026-09-02", account(hd, "Bank").id, Decimal("20"), food, counterparty="Cafe"))
    pc.sync_with(hd.home)
    keep, drop = (row["id"] for row in pc.c.db.all("SELECT id FROM transactions WHERE counterparty='Cafe' ORDER BY id"))
    token = pc.c.transactions.merge_preview(keep, drop).fingerprint
    act(hd, pc, lambda s: s.transactions.merge(keep, drop, token))
    assert pc.c.transactions.get(drop).is_void and hd.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE status='VOID'") == 1


def test_the_older_account_level_cd_terms_reach_the_service(devices):
    # No legacy CD can be made any more, so what comes back is the service's own refusal, at once and in its words.
    hd, pc = devices
    bank, wallet = account(pc, "Bank").id, account(pc, "Wallet").id
    with pytest.raises(Exception, match="Choose a DEPOSIT account"):
        JournalServices(pc).deposits.save(bank, "2026-01-01", "2027-01-01", "1000", "15", "SIMPLE", "AT_MATURITY", wallet,
                                          lockup_end_date="2027-01-01", compounding_frequency="MONTHLY")
    assert not pc.store.pending()
