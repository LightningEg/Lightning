"""J6a: generic exact row effects replace the cash-only effect schema."""
import pytest

from test_journal_finance import devices, groups
from lightning.sync.journal.codec import JournalError, unpack


def effect_of(home, wire):
    from lightning.sync.journal.codec import origin_id
    commit = unpack(home.home.decision(origin_id(unpack(wire)["body"]["origin"])))["body"]
    return commit["effects"][0]["domain"]


def test_effects_are_typed_rows_with_uuid_references_and_replay_exactly(devices):
    hd, pc = devices
    wire = pc.save(groups(pc, "-25.00", transfer=True))
    pc.sync_with(hd.home)
    domain = effect_of(hd, wire)
    assert domain["schema"] == 2
    tables = sorted(row["table"] for row in domain["rows"])
    assert tables == ["ledger_entries", "ledger_entries", "transactions"]
    line = next(row for row in domain["rows"] if row["table"] == "ledger_entries")
    assert "id" not in line["values"] and len(line["values"]["account_id"]) == 36
    # The replica's accounts have different local ids, yet balances agree.
    assert {item["name"]: item["balance"] for item in pc.balances()} == {"Bank": 975, "Wallet": 125}
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def test_a_rewrite_keeps_row_identities_and_a_void_sends_one_row(devices):
    hd, pc = devices
    wire = pc.save(groups(pc))
    record = unpack(wire)["body"]["record"]
    pc.sync_with(hd.home)
    first = {row["key"] for row in effect_of(hd, wire)["rows"]}
    edit = pc.save({"money": groups(pc, "-40.00")["money"]}, record=record)
    pc.sync_with(hd.home)
    second = effect_of(hd, edit)
    assert {row["key"] for row in second["rows"]} <= first
    assert all(row["values"] is not None for row in second["rows"])
    delete = pc.save({}, record=record, delete=True)
    pc.sync_with(hd.home)
    void = effect_of(hd, delete)["rows"]
    assert [(row["table"], row["values"]["status"]) for row in void] == [("transactions", "VOID")]
    assert next(item for item in pc.balances() if item["name"] == "Bank")["balance"] == 1000
    assert hd.store.fingerprint() == pc.store.fingerprint()


@pytest.mark.parametrize("change", ["table", "column", "type", "reference"])
def test_a_replica_refuses_rows_outside_its_schema_before_writing(devices, change):
    hd, pc = devices
    wire = hd.save(groups(hd))
    domain = effect_of(hd, wire)
    row = next(item for item in domain["rows"] if item["table"] == "ledger_entries")
    if change == "table":
        row["table"] = "settings"
    elif change == "column":
        row["values"]["sneaky"] = 1
    elif change == "type":
        row["values"]["amount_e6"] = "1"
    else:
        row["values"]["account_id"] = "not-a-uuid"
    before = pc.store.fingerprint()
    with pytest.raises(JournalError):
        with pc.store.db.transaction():
            pc.adapter.apply(domain)
    assert pc.store.fingerprint() == before


def test_writes_outside_the_synchronized_tables_are_refused_by_confirmation(devices, monkeypatch):
    hd, pc = devices
    real = hd.c.transactions.record_in_account
    def leaky(**values):
        result = real(**values)
        hd.c.db.execute("DELETE FROM profile_identity WHERE 0")  # Identity metadata is outside synchronized financial tables.
        return result
    monkeypatch.setattr(hd.c.transactions, "record_in_account", leaky)
    wire = pc.save(groups(pc))
    pc.sync_with(hd.home)
    from lightning.sync.journal.codec import origin_id
    assert hd.home.status(origin_id(unpack(wire)["body"]["origin"])) == dict(status="rejected", reason="financial-validation")
