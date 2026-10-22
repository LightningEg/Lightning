"""J6f: the app's own screens on a two-device journal profile."""
import asyncio
import json

import httpx
import pytest

from test_journal_finance import devices
from lightning.sync.journal.proxy import JournalServices
from lightning.ui.web import create_app


class Screen:
    """The real app on one device, driven in the test's thread (the database is thread-bound)."""
    def __init__(self, device):
        self.app = create_app(JournalServices(device))

    def _call(self, method, path, **options):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver",
                                         headers={"origin": "http://testserver"}) as client:
                return await client.request(method, path, **options)
        return asyncio.run(run())

    def get(self, path, **options):
        return self._call("GET", path, **options)

    def post(self, path, **options):
        return self._call("POST", path, **options)


@pytest.fixture
def screens(devices):
    return devices, [Screen(device) for device in devices]


def test_pages_read_the_confirmed_copy_on_both_devices(screens):
    (hd, pc), (home, replica) = screens
    for client in (home, replica):
        for path in ("/", "/accounts", "/transactions", "/budget", "/plan", "/settings"):
            response = client.get(path)
            assert response.status_code in (200, 303), (path, response.status_code)


def test_a_replica_save_comes_back_saved_and_waiting(screens):
    (hd, pc), (home, replica) = screens
    wallet = next(a.id for a in pc.c.accounts.list() if a.name == "Wallet")
    form = dict(name="Pocket money", account_type="CASH", institution="", notes="", opening_balance_date="2026-01-01",
                owner_id="")
    response = replica.post(f"/accounts/{wallet}/edit", data=form, headers={"referer": f"http://testserver/accounts/{wallet}"})
    assert response.status_code == 303 and "msg=Saved+on+this+device" in response.headers["location"]
    assert next(a for a in pc.c.accounts.list() if a.id == wallet).name == "Wallet"  # Confirmed copy unchanged.
    pc.sync_with(hd.home)
    assert next(a for a in pc.c.accounts.list() if a.id == wallet).name == "Pocket money"
    assert hd.store.fingerprint() == pc.store.fingerprint()


def test_new_custom_institution_and_account_are_one_replica_command(screens):
    (hd, pc), (home, replica) = screens
    response = replica.post("/accounts/new", data={
        "name": "Travel account", "account_type": "BANK", "institution": "Cairo Travel Union",
        "last4": "4321", "notes": "", "opening_balance": "125", "opening_balance_date": "2026-10-01",
        "owner_id": "", "currency": "EGP",
    }, headers={"referer": "http://testserver/accounts/new"})

    assert response.status_code == 303
    assert "Saved+on+this+device" in response.headers["location"]
    pending = pc.store.pending()
    assert len(pending) == 1
    assert not pc.store.db.scalar("SELECT 1 FROM institutions WHERE name=?", ("Cairo Travel Union",))
    assert not pc.store.db.scalar("SELECT 1 FROM accounts WHERE name=?", ("Travel account",))

    pc.sync_with(hd.home)
    assert hd.store.db.scalar("SELECT 1 FROM institutions WHERE name=?", ("Cairo Travel Union",))
    assert hd.store.db.scalar("SELECT 1 FROM accounts WHERE name=?", ("Travel account",))
    assert pc.store.db.scalar("SELECT 1 FROM institutions WHERE name=?", ("Cairo Travel Union",))
    assert pc.store.db.scalar("SELECT 1 FROM accounts WHERE name=?", ("Travel account",))
    assert hd.store.fingerprint() == pc.store.fingerprint()


@pytest.mark.parametrize(("path", "data", "action"), [
    ("/budget/settings/full", {"income_months": "3", "manual_income": "", "carryover": "1",
      "income_from_recurring_shown": "1", "income_from_recurring": "0", "emergency_basis": "spending",
      "return_to": "/budget"}, "journal_workflows.save_budget_settings"),
    ("/setup/currency", {"currency": "EGP", "extra": ["USD"]}, "journal_workflows.setup_currencies"),
    ("/settings/fx-rate", {"currency": "USD", "date": "2026-10-01", "rate": "50.125"},
      "journal_workflows.save_fx_rate"),
])
def test_composite_settings_routes_stage_one_proposal(screens, path, data, action):
    (hd, pc), (_, replica) = screens
    if action == "journal_workflows.save_fx_rate":
        # FX rates can only be entered for registered currencies. Register USD
        # on the home first, then verify the rate itself remains one command.
        JournalServices(hd).currencies.register("USD")
        pc.sync_with(hd.home)
    response = replica.post(path, data=data)
    assert response.status_code == 303
    pending = pc.pending_commands()
    assert len(pending) == 1
    assert pending[0]["name"] == action


def test_create_plan_stages_one_portable_budget_command(screens):
    (_, pc), (_, replica) = screens
    category = next(item for item in pc.c.categories.pickable() if item.movement.value == "OUTFLOW")
    response = replica.post("/budget/setup?month=2026-09", data={f"suggest_{category.id}": "250"})
    assert response.status_code == 303
    pending = pc.pending_commands()
    assert len(pending) == 1 and pending[0]["name"] == "budgets.save_month"
    assert not pc.c.db.scalar("SELECT COUNT(*) FROM budgets WHERE category_id=?", (category.id,))


def test_pending_currency_setup_restores_replica_service_caches(screens, monkeypatch):
    (_, pc), (_, replica) = screens
    original_scalar = pc.c.db.scalar

    def scalar(sql, params=()):
        if "SELECT EXISTS(" in sql:
            return 0
        return original_scalar(sql, params)

    monkeypatch.setattr(pc.c.db, "scalar", scalar)
    monkeypatch.setattr(pc.c.accounts, "list", lambda *args, **kwargs: [])
    response = replica.post("/setup/currency", data={"currency": "USD"})

    assert response.status_code == 303
    assert "Saved+on+this+device" in response.headers["location"]
    assert pc.c.base_currency == "EGP"
    assert pc.c.assets.base_currency == "EGP"
    assert pc.c.accounts.base_currency == "EGP"
    assert pc.c.transactions.base_currency == "EGP"
    assert pc.c.reporting.base_currency == "EGP"
    assert pc.c.reporting.valuer.base == "EGP"
    assert pc.c.fx.profile_currency == "EGP"
    assert len(pc.pending_commands()) == 1


def test_bulk_budget_route_stages_one_reversible_command(screens):
    (_, pc), (_, replica) = screens
    category = next(item for item in pc.c.categories.pickable() if item.movement.value == "OUTFLOW")
    response = replica.post("/budget/bulk", data={"month": "2026-10", "category_id": [str(category.id)],
                                                    "action": "average3"})
    assert response.status_code == 303
    pending = pc.pending_commands()
    assert len(pending) == 1
    assert pending[0]["name"] == "journal_workflows.apply_bulk_budget"


def test_bulk_budget_undo_stages_one_command(screens):
    (hd, pc), (_, replica) = screens
    category = next(item for item in pc.c.categories.pickable() if item.movement.value == "OUTFLOW")
    home_category = next(item for item in hd.c.categories.pickable() if item.code == category.code)
    fingerprint = hd.c.journal_workflows.bulk_budget_fingerprint([home_category.id])
    snapshot = {"token": "test-undo", "month": "2026-10", "category_codes": [category.code],
                "rows": hd.c.journal_workflows._portable_budget_snapshot([home_category.id]),
                "after_fingerprint": fingerprint}
    encoded = json.dumps(snapshot)
    hd.command("settings.set", key="budget_bulk_undo", value=encoded)
    pc.sync_with(hd.home)
    response = replica.post("/budget/bulk/undo", data={"token": "test-undo"})
    assert response.status_code == 303
    pending = pc.pending_commands()
    assert len(pending) == 1
    assert pending[0]["name"] == "journal_workflows.undo_bulk_budget"


def test_a_refusal_shows_at_once_on_a_replica_and_nothing_is_queued(screens):
    (hd, pc), (home, replica) = screens
    wallet = next(a.id for a in pc.c.accounts.list() if a.name == "Wallet")
    response = replica.post(f"/accounts/{wallet}/deactivate")
    assert "still+holds" in response.headers["location"] or "still%20holds" in response.headers["location"]
    assert not pc.store.pending()


def test_service_action_status_shows_pending_and_terminal_refusal(devices):
    from lightning.ui.journal import command_status_rows

    home, pc = devices
    pc.command("accounts.open", currency=None, opening_balance_date=None, owner_id=None, name="Bank",
               account_type="BANK", opening_date="2026-02-01", opening_balance="0", institution="",
               last4=None, notes="")
    assert [(row["name"], row["state"]) for row in command_status_rows(pc)] == [("Open account", "Pending")]
    pc.sync_with(home.home)
    rows = command_status_rows(pc)
    assert rows[0]["name"] == "Open account"
    assert rows[0]["state"] == "Not taken"
    assert rows[0]["reason"] == "The home could not apply this action"


def test_native_journal_router_renders_command_and_device_pages(devices):
    import asyncio
    from types import SimpleNamespace
    import httpx
    from fastapi import FastAPI
    from lightning.runtime.journal_ui_routes import journal_ui_router

    home, _ = devices
    async def synchronize():
        return True
    session = SimpleNamespace(token="native-journal-session-" + "s" * 32,
                              journal=SimpleNamespace(device=home, pairing=None, synchronize=synchronize, trust=None))
    app = FastAPI()
    app.include_router(journal_ui_router(session))

    async def browse():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            home_page = await client.get("/journal")
            devices_page = await client.get("/journal/devices")
            return home_page, devices_page

    home_page, devices_page = asyncio.run(browse())
    assert home_page.status_code == devices_page.status_code == 200
    assert "Service actions" in home_page.text
    assert "Devices" in devices_page.text
    assert "Paired devices" in devices_page.text


def test_the_home_saves_through_the_journal_and_the_replica_follows(screens):
    (hd, pc), (home, replica) = screens
    bank = next(a.id for a in hd.c.accounts.list() if a.name == "Bank")
    form = dict(name="Main bank", account_type="BANK", institution="", notes="", opening_balance_date="2026-01-01",
                owner_id="")
    response = home.post(f"/accounts/{bank}/edit", data=form)
    assert response.status_code == 303 and "Account+saved" in response.headers["location"] or "Account%20saved" in response.headers["location"]
    assert hd.store.cursor()["revision"] == 1
    pc.sync_with(hd.home)
    assert any(a.name == "Main bank" for a in pc.c.accounts.list())


def test_lab_opens_the_apps_own_screens_and_a_pc_save_reaches_the_home(tmp_path, monkeypatch):
    import socket
    from lightning.runtime import journal_lab
    devices, secret = journal_lab.open_lab(tmp_path, "dummy-launcher-password")
    home, pc = devices
    links = []
    monkeypatch.setattr(journal_lab.webbrowser, "open", lambda url: links.append(url))
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    async def run():
        task = asyncio.create_task(journal_lab.serve(devices, secret, port, full_app=True))
        try:
            for _ in range(100):
                if len(links) == 2:
                    break
                await asyncio.sleep(0.05)
            origin = f"http://127.0.0.1:{port + 1}"
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as stranger:
                assert (await stranger.get(origin + "/accounts")).status_code == 401
            async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
                assert (await client.get(links[1])).status_code == 200
                wallet = next(a.id for a in pc.c.accounts.list() if a.name == "Wallet")
                response = await client.post(f"{origin}/accounts/{wallet}/edit", follow_redirects=False,
                    headers={"origin": origin, "referer": f"{origin}/accounts/{wallet}"},
                    data=dict(name="Pocket money", account_type="CASH", institution="", notes="",
                              opening_balance_date=pc.c.accounts.get(wallet).opening_date, owner_id=""))
                assert "Saved+on+this+device" in response.headers["location"]
                for _ in range(100):
                    if not pc.store.pending():
                        break
                    await asyncio.sleep(0.05)
                assert not pc.store.pending()
                assert any(a.name == "Pocket money" for a in home.c.accounts.list())
                assert pc.store.fingerprint() == home.store.fingerprint()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    try:
        asyncio.run(run())
    finally:
        for device in devices:
            device.store.close()
