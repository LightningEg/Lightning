"""Write coverage of the app's screens on a journal profile: an honest inventory, and graceful refusals."""
import json
import sys
from pathlib import Path

import pytest

from test_journal_finance import devices  # noqa: F401
from test_journal_screens import screens  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import journal_coverage  # noqa: E402


def test_the_inventory_reports_the_account_edit_route_as_covered():
    rows = journal_coverage.inventory()
    state = {row["path"]: row["state"] for row in rows}
    assert state["/accounts/{account_id:int}/edit"] == "covered"
    assert state["/sms/assign"] == "covered" and state["/sms/paste"] == "covered"
    assert state["/activity/{transaction_id:int}/apply"] == "covered"
    assert state["/setup/salary"] == "covered"
    assert state["/accounts/{account_id:int}/value"] == "covered"
    assert state["/plan/purchases/new"] == "covered"
    assert state["/plan/items/{item_id:int}/early-payment"] == "covered"
    assert state["/history/{operation}"] == "covered"
    assert state["/investments/prices/online"] == "covered"
    assert state["/investments/prices/market/fill"] == "covered"
    assert state["/investments/prices/market/update"] == "covered"
    assert state["/settings/backup"] == state["/settings/fresh"] == "local-only"
    assert state["/settings/locale"] == "covered"
    assert {"covered", "local-only", "read-only"} <= set(state.values())
    assert not ({"partial", "uncovered"} & set(state.values()))
    assert journal_coverage.regressions(rows) == []
    assert "Summary:" in journal_coverage.report(rows)


def test_sms_assignment_is_a_portable_command(screens):
    (hd, pc), clients = screens
    bank_h = next(a for a in hd.c.accounts.list() if a.name == "Bank")
    bank_p = next(a for a in pc.c.accounts.list() if a.name == "Bank")
    samples = json.loads((Path(__file__).parent / "fixtures" / "bank_sms.json").read_text(encoding="utf-8"))
    sample = next(s for s in samples["samples"] if s["bank"] == "NBE" and s["kind"] == "purchase")
    message, ending = sample["text"], sample["expect"]["ending"]
    pasted = clients[1].post("/sms/paste", data={"messages": message}, headers={"referer": "http://testserver/sms"})
    assert pasted.status_code == 303 and "Saved+on+this+device" in pasted.headers["location"]
    pc.sync_with(hd.home)
    response = clients[1].post("/sms/assign", data={"ending": ending, "account_id": str(bank_p.id)},
                               headers={"referer": "http://testserver/sms"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    assert hd.c.sms_imports.endings()[ending] == bank_h.id
    assert pc.c.sms_imports.endings()[ending] == bank_p.id
    assert json.loads(hd.c.settings.get("sms_account_endings"))[ending] == bank_h.code
    assert json.loads(pc.c.settings.get("sms_account_endings"))[ending] == bank_h.code
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows") == 1
    assert hd.c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE status='REVIEW'") == 1


def test_answering_several_endings_at_once_is_a_portable_command(screens):
    """IV-3AU: From SMS answers every waiting ending in one form; a paired device sends account UUIDs, not its ids."""
    (hd, pc), clients = screens
    bank_h = next(a for a in hd.c.accounts.list() if a.name == "Bank")
    bank_p = next(a for a in pc.c.accounts.list() if a.name == "Bank")
    samples = json.loads((Path(__file__).parent / "fixtures" / "bank_sms.json").read_text(encoding="utf-8"))
    picked = [s for s in samples["samples"] if s["bank"] == "NBE"]
    endings = sorted({s["expect"]["ending"] for s in picked if "ending" in s["expect"]})
    assert len(endings) >= 2
    pasted = clients[1].post("/sms/paste", data={"messages": "\n\n".join(s["text"] for s in picked)},
                             headers={"referer": "http://testserver/sms"})
    assert pasted.status_code == 303
    pc.sync_with(hd.home)
    response = clients[1].post("/sms/assign", data={f"account_{e}": str(bank_p.id) for e in endings},
                               headers={"referer": "http://testserver/sms"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    assert all(hd.c.sms_imports.endings()[e] == bank_h.id for e in endings)
    assert hd.c.sms_imports.waiting() == [] and hd.c.db.scalar("SELECT COUNT(DISTINCT batch_id) FROM bank_import_rows") == 1


def test_other_asset_value_route_preserves_the_portable_action(screens):
    from decimal import Decimal
    from lightning.sync.journal.codec import unpack
    from lightning.sync.journal.proxy import JournalServices

    (hd, pc), (_, replica) = screens
    JournalServices(hd).account_flows.open_account("Flat", "OTHER_ASSET", "2026-01-01", "0")
    pc.sync_with(hd.home)
    flat = next(a for a in pc.c.accounts.list() if a.name == "Flat")
    response = replica.post(f"/accounts/{flat.id}/value", data={
        "date": "2026-09-01", "value": "1250000", "notes": "Estimate"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert pc.c.accounts.manual_value(flat.id, "2026-09-01") is None
    body = unpack(pc.store.pending()[0])["body"]
    assert body["kind"] == "command.reporting.other_asset_values.save"
    pc.sync_with(hd.home)
    home_flat = next(a for a in hd.c.accounts.list() if a.name == "Flat")
    for device, account in ((hd, home_flat), (pc, flat)):
        value = device.c.accounts.manual_value(account.id, "2026-09-01")
        assert value["value"] == Decimal("1250000") and value["notes"] == "Estimate"
    assert pc.store.fingerprint() == hd.store.fingerprint()


def test_registered_command_names_fit_the_wire_format():
    from lightning.sync.journal.codec import COMMAND
    from lightning.sync.journal.commands import KINDS

    assert all(COMMAND.fullmatch(kind) for kind in KINDS)
    assert not COMMAND.fullmatch("command.accounts.save.extra.unregistered")


def test_replica_history_action_stays_on_the_home(screens):
    (hd, pc), clients = screens
    response = clients[1].post("/history/undo", data={"group_id": "1"},
                               headers={"referer": "http://testserver/history"})
    assert response.status_code == 303
    from urllib.parse import unquote_plus
    assert "journal home" in unquote_plus(response.headers["location"])
    assert not pc.store.pending()


def test_other_database_errors_are_not_hidden(screens, monkeypatch):
    (hd, pc), (home, replica) = screens
    storage_error = hd.c.db.driver.DatabaseError

    from functools import wraps

    @wraps(hd.c.sms_imports.assign)
    def broken(*args, **kwargs):
        raise storage_error("disk image is malformed")
    monkeypatch.setattr(hd.c.sms_imports, "assign", broken)
    with pytest.raises(storage_error, match="malformed"):
        home.post("/sms/assign", data={"ending": "1234", "account_id": str(next(a.id for a in hd.c.accounts.list() if a.name == "Bank"))})
