"""Bank-statement import travels as commands: stage, confirm (one action, chunked effects), discard."""
import pytest

from test_journal_finance import devices, groups  # noqa: F401
from test_journal_screens import Screen
from lightning.sync.journal.proxy import JournalServices, PendingOnHome


def same(hd, pc):
    assert hd.store.fingerprint() == pc.store.fingerprint() == pc.adapter.fingerprint(full=True)


def bank(device):
    return next(a for a in device.c.accounts.list() if a.name == "Bank")


NAMES = ("Carrefour", "Vodafone", "Pharmacy Seif", "Uber", "Starbucks")


def statement(rows=2):
    lines = ["Date,Amount,Counterparty,Category,Notes,Reference"]
    lines += [f"2026-03-{day % 28 + 1:02d},-{day + 10}.00,{NAMES[day % 5]},,Item {day},R{day}" for day in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def upload(screen, device, data, name="march.csv"):
    return screen.post(f"/accounts/{bank(device).id}/import", files={"file": (name, data, "text/csv")})


def batch(device):
    return device.c.db.one("SELECT * FROM bank_import_batches ORDER BY id DESC")


def decisions(device, category):
    _, rows = device.c.bank_imports.preview(batch(device)["id"])
    return {row["_import_row_id"]: dict(
        category_id=str(category), force_uncategorized=False, skip=False, match="", date=row["Date"],
        counterparty=row["Counterparty"], alias_text=row["Counterparty"], amount=row["Amount"], notes=row["Notes"],
        whom="", owner_choice="", counterparty_choice="typed", remember_category=False, transfer_account_id="")
        for row in rows}


def balance(device):
    return device.c.db.scalar("SELECT SUM(quantity_e6) FROM ledger_entries WHERE account_id=?", (bank(device).id,))


def settle(hd, pc):
    pc.sync_with(hd.home)
    pc.sync_with(hd.home)


def test_a_replica_stages_and_both_devices_confirm_the_same_rows(devices):
    hd, pc = devices
    response = upload(Screen(pc), pc, statement())
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert not pc.c.db.one("SELECT * FROM bank_import_batches")  # Pending until the home stages it.
    settle(hd, pc)
    assert batch(hd)["file_name"] == "march.csv" and batch(pc)["status"] == "REVIEW"
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows") == pc.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows") == 2
    same(hd, pc)
    food = pc.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    with pytest.raises(PendingOnHome):
        JournalServices(pc).bank_imports.confirm(batch(pc)["id"], decisions(pc, food))
    settle(hd, pc)
    assert batch(hd)["status"] == batch(pc)["status"] == "POSTED"
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE status='POSTED'") == 2
    assert balance(hd) == balance(pc) == hd.c.db.scalar(
        "SELECT SUM(quantity_e6) FROM ledger_entries WHERE account_id=?", (bank(hd).id,))
    assert hd.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE source='IMPORT'") == 2
    same(hd, pc)


def test_the_home_confirms_its_own_statement_and_a_replica_follows(devices):
    hd, pc = devices
    response = upload(Screen(hd), hd, statement())
    assert response.status_code == 303 and "/import/" in response.headers["location"]
    food = hd.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    result = JournalServices(hd).bank_imports.confirm(batch(hd)["id"], decisions(hd, food))
    assert result["posted"] == 2
    settle(hd, pc)
    assert balance(hd) == balance(pc) and batch(pc)["status"] == "POSTED"
    same(hd, pc)


def test_a_forty_row_statement_is_one_confirmation(devices):
    hd, pc = devices
    upload(Screen(pc), pc, statement(40))
    settle(hd, pc)
    food = pc.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    with pytest.raises(PendingOnHome):
        JournalServices(pc).bank_imports.confirm(batch(pc)["id"], decisions(pc, food))
    before = hd.store.cursor()["revision"]
    settle(hd, pc)
    assert hd.store.cursor()["revision"] == before + 1  # One action, however many chunks carry it.
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE status='POSTED'") == 40
    assert balance(hd) == balance(pc)
    same(hd, pc)


def test_a_three_hundred_row_statement_uses_bounded_chunked_commands(devices):
    hd, pc = devices
    data = statement(300)
    assert len(data) < 40 * 1024
    response = upload(Screen(pc), pc, data)
    assert response.status_code == 303
    settle(hd, pc)
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows") == 300

    food = hd.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    chosen = decisions(hd, food)
    for decision in chosen.values():
        decision["skip"] = True
    first_row = min(chosen, key=int)
    chosen[first_row]["skip"] = False
    chosen[first_row]["date"] = "not-a-date"
    result = JournalServices(hd).bank_imports.confirm(batch(hd)["id"], chosen)
    # The bad row holds the entire confirmation for review; the 299 skip changes roll back with it.
    assert result["posted"] == result["skipped"] == 0
    assert first_row in result["errors"] or int(first_row) in result["errors"]
    assert hd.c.db.scalar("SELECT COUNT(*) FROM transactions WHERE source='IMPORT'") == 0
    settle(hd, pc)
    same(hd, pc)


def test_discard_removes_the_staged_statement_everywhere(devices):
    hd, pc = devices
    upload(Screen(pc), pc, statement())
    settle(hd, pc)
    with pytest.raises(PendingOnHome):
        JournalServices(pc).bank_imports.discard(batch(pc)["id"])
    settle(hd, pc)
    for device in (hd, pc):
        assert device.c.db.scalar("SELECT COUNT(*) FROM bank_import_batches") == 0
    same(hd, pc)


def test_a_file_over_forty_kib_is_refused_with_a_clear_message(devices):
    hd, pc = devices
    big = statement(1200)
    assert len(big) > 40 * 1024
    for device in (hd, pc):
        response = upload(Screen(device), device, big)
        assert response.status_code == 400 and "too large to synchronize" in response.text
        assert not device.store.pending()



def test_replica_saves_every_selected_file_before_returning_pending(devices):
    home, replica = devices
    bank = next(a.id for a in replica.c.accounts.list() if a.name == "Bank")
    files = [("file", (f"part-{index}.csv",
              f"Date,Amount,Counterparty\n2026-09-02,-10,Shop {index}\n".encode(), "text/csv"))
             for index in (1, 2)]
    response = Screen(replica).post(f"/accounts/{bank}/import", files=files)
    assert response.status_code == 303
    assert len(replica.store.pending()) == 2
    settle(home, replica)
    assert home.c.db.scalar("SELECT COUNT(*) FROM bank_import_batches") == 2
    same(home, replica)
