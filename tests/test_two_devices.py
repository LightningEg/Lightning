"""Mohab with a phone and a PC: how a normal user moves between them, through the screens only.

Each device is a real profile app with its own folders (the phone in the phone frame, guideline Part C), and Mohab
only clicks, types and reads. The other sync tests prove the protocol; this file proves the journey:

1. He started on the PC, then moves the profile to the phone; every row and figure comes with it, and the PC
   cannot open its old copy for writing.
2. On the bus he fixes a wrong amount and adds a ride on the phone; at his desk the PC borrows the ledger and shows
   exactly the phone's edits; he edits and deletes on the PC while the phone only reads; Hand back returns it.
3. A form left open on one device never saves over the other's work; a save on a lent phone answers a phone page
   that names the PC and leads to Devices, and an open page shows the hand-over by itself.
4. He forgets to hand back and goes home: the PC keeps his edits sealed; the next morning they reach the phone.
5. The PC is out of reach for good: the phone takes the ledger back, and the PC says so and borrows again.
6. The phone is locked when the PC hands back: the changes wait and go in when he unlocks it; meanwhile a tap
   shows One moment, never the profile chooser.
7. A second PC at home cannot borrow while the office PC has it; a wrong password borrows nothing.

After every hand-over both devices show the same figures. A gap found here is a strict expected failure until fixed.
"""
from __future__ import annotations

import re
import socket
import time

import pytest
from fastapi.testclient import TestClient

import screens
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from test_mohab_phone import PhoneBrowser, PhoneMohab
from test_mohab_year import Mohab
from test_profile_app import PASSWORD, create

CODE = re.compile(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Device:
    """One device in Mohab's hand: its app, its own folders, a browser window on it."""

    def __init__(self, tmp_path, name: str, port: int, phone: bool):
        self.name, self.phone = name, phone
        self.cfg = Credentials(f"http://127.0.0.1:{port}")
        # The phone listens on one fixed port, as on Wi-Fi (47513), so it answers again when it is back.
        self.devices = Devices(tmp_path / f"{name}-appdata", port=free_port() if phone else 0, host="127.0.0.1")
        self.app = profile_app(self.cfg, tmp_path / f"{name}-docs", devices=self.devices, phone=phone)
        self.open_app()

    # -------------------------------------------------------------- the app itself
    def open_app(self):
        """Start Lightning on this device (the window opens on the profile chooser)."""
        self.client = TestClient(self.app, base_url=self.cfg.origin, headers={"Origin": self.cfg.origin})
        self.client.__enter__()
        self.client.get("/__launch", params={"code": self.cfg.launch_code})
        self.b = PhoneBrowser(self.app) if self.phone else screens.Browser(self.app)
        self.b.client = self.client
        hand = (PhoneMohab if self.phone else Mohab).__new__(PhoneMohab if self.phone else Mohab)
        hand.b, hand.answers, hand.notes = self.b, {}, {}
        self.hand = hand

    def close_app(self):
        """Close the window: a borrowing PC hands back if the phone answers, else keeps its edits sealed."""
        self.client.__exit__(None, None, None)

    def restart(self):
        """The next morning: Lightning starts again on the same folders."""
        self.close_app()
        self.devices = Devices(self.devices.root, port=self.devices.port, host="127.0.0.1")
        self.cfg = Credentials(self.cfg.origin)
        self.app = profile_app(self.cfg, self.app.session.root, devices=self.devices, phone=self.phone)
        self.open_app()

    def wait_while_checking(self, seconds: float = 10.0):
        """He waits a moment while the phone checks a returned copy (meanwhile a tap shows One moment)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            page = self.client.get("/")
            if page.url.path == "/" and "Checking it" not in page.text:
                return
            assert page.url.path == "/" or "One moment" in page.text, page.url
            time.sleep(0.05)
        raise AssertionError("The phone kept checking the returned copy")

    def away(self):
        """The phone leaves the PC's Wi-Fi (Lightning stays open on it)."""
        self.devices.stop()

    def back(self):
        self.devices.ensure_listener()

    # -------------------------------------------------------------- what he does
    def unlock(self, password: str = PASSWORD) -> screens.Screen:
        """Profiles › the profile › password › Unlock profile."""
        chooser = self.b.open("/profiles")
        link = next(l for l in chooser.links if "/profiles/unlock" in l.href)
        self.b.click(link.text)
        return self.b.submit({"password": password}, button="Unlock profile")

    def lock(self) -> screens.Screen:
        """Profiles & lock (the phone: its profile page) › Lock profile."""
        self.b.go("Profiles & lock") if not self.phone else self.b.open("/profiles")
        return self.b.submit({}, button="Lock profile")

    def add_account(self, name: str) -> screens.Screen:
        return self.hand.account(name, "Cash", "1000", when="2026-10-01")

    def spend(self, account: str, when: str, party: str, amount: str) -> screens.Screen:
        return self.hand.enter(account, when, party, "Food & Groceries", f"-{amount}")

    def fix_amount(self, account: str, party: str, amount: str) -> screens.Screen:
        """A spending's new amount: the phone's sheet keeps Out; the PC's register row is signed."""
        return self.hand.fix_amount(account, party, amount if self.phone else f"-{amount}")

    def delete(self, account: str, party: str) -> screens.Screen:
        return self.hand.delete_newest(account, party)

    # -------------------------------------------------------------- what he reads
    def register(self, account: str) -> str:
        return self.b.go(account).text if not self.phone else self.b.go("Accounts", account).text

    def owns(self) -> str:
        """The Overview's What you own: the figure he glances at on both devices."""
        text = self.b.open("/").after("What you own", 60)
        text = re.sub(r"As of \d{4}-\d{2}-\d{2}|Excludes money held for others", "", text)  # the phone's hero puts its date first;
        return text.split()[0]  # the PC's Lead names what it leaves out (guideline 3.33)


def typed_address(shown: screens.Screen) -> str:
    """He types the address the phone shows; in this test the Wi-Fi is this machine, so its port on 127.0.0.1."""
    return "127.0.0.1:" + re.search(r"Phone address \S+:(\d+)", shown.text).group(1)


def pair_phone(phone: Device, pc: Device, pc_name: str) -> screens.Screen:
    """Phone: Devices › Show a pairing code. PC: Profiles › Connect to your phone › type it."""
    phone.b.open("/profiles/devices")
    shown = phone.b.submit({}, button="Show a pairing code")
    code = CODE.search(shown.text).group(0)
    phone.address = typed_address(shown)
    pc.b.open("/profiles")
    pc.b.click("Connect to your phone")
    return pc.b.submit({"address": phone.address, "code": code, "pc_name": pc_name}, button="Connect")


def borrow(pc: Device, password: str = PASSWORD, expect: int = 200) -> screens.Screen:
    """PC: Profiles › From your phone › Mohab › password › Borrow."""
    listing = pc.b.open("/profiles")
    link = next(l for l in listing.links if "/profiles/borrowed?id=" in l.href)
    pc.b.click(link.text)
    return pc.b.submit({"password": password}, expect=expect)


@pytest.fixture
def mohab(tmp_path):
    """Mohab started on the office PC, then moved the profile to his phone (scenario 1)."""
    phone = Device(tmp_path, "phone", 9701, phone=True)
    pc = Device(tmp_path, "office", 9702, phone=False)
    try:
        create(pc.client, "Mohab")
        pc.add_account("Wallet")
        pc.spend("Wallet", "2026-10-02", "Seoudi", "200")
        pc.spend("Wallet", "2026-10-03", "Talabat", "150")
        yield phone, pc
    finally:
        for device in (pc, phone):
            try:
                device.close_app()
            except Exception:  # noqa: BLE001 - a test may have closed it already
                pass


def move_to_phone(phone: Device, pc: Device) -> screens.Screen:
    phone.b.open("/profiles")
    phone.b.click("Bring a profile from your PC")
    shown = phone.b.submit({"phone_name": "My phone"}, button="Show a code")
    code = CODE.search(shown.text).group(0)
    phone.address = typed_address(shown)
    pc.b.go("Profiles & lock")
    return pc.b.submit({"address": phone.address, "code": code, "pc_name": "Office PC"}, button="Move to the phone")


def moved(phone: Device, pc: Device) -> None:
    """Scenario 1's end: the profile lives on the phone, unlocked there; the PC is paired and borrows it."""
    move_to_phone(phone, pc)
    phone.unlock()


def test_1_a_pc_profile_moves_to_the_phone_with_every_row_and_figure(mohab):
    phone, pc = mohab
    before = pc.owns()
    assert before == "650"  # 1,000 opening, less 200 and 150
    done = move_to_phone(phone, pc)
    digits = re.search(r"shows (\d{3} \d{3})", done.text).group(1)
    assert done.shows("Mohab now lives on My phone", "From your phone", "On My phone")
    # The PC's old copy is never offered to open: only the phone's, to borrow.
    assert not [l for l in done.links if "/profiles/unlock" in l.href]
    arrived = phone.b.open("/profiles/receive")
    assert arrived.shows("Mohab is here", "Office PC", digits)  # both screens show the same check digits

    phone.b.click("Unlock it")          # back to the chooser, where Mohab now waits
    phone.unlock()
    assert phone.owns() == before
    rows = phone.register("Wallet")
    assert "Seoudi" in rows and "Talabat" in rows
    assert phone.add_account("Vodafone Cash").shows("Vodafone Cash")  # the phone is home: it writes

    borrow(pc)
    assert pc.owns() == phone.owns()
    assert "Vodafone Cash" in pc.b.open("/accounts").text


def test_2_edits_on_the_phone_reach_the_pc_and_the_pcs_come_back(mohab):
    phone, pc = mohab
    moved(phone, pc)
    # On the bus: Talabat was 175, not 150; and an Uber ride.
    phone.fix_amount("Wallet", "Talabat", "175")
    phone.spend("Wallet", "2026-10-04", "Uber", "60")
    assert phone.owns() == "565"

    # At his desk the PC borrows the ledger and shows exactly the phone's edits.
    opened = borrow(pc)
    assert opened.path == "/" and opened.shows("Borrowed from My phone")
    rows = pc.register("Wallet")
    assert "175" in rows and "Uber" in rows and "150" not in rows
    assert pc.owns() == phone.owns() == "565"

    # While the PC has it the phone reads and says who has it (test_3b: what Save does there).
    lent = phone.b.open("/")
    assert lent.shows("Lent to Office PC") and lent.shows("read only"), lent.text[:400]

    # He edits on the PC: the phone's Uber was 65, Talabat was a duplicate, and a new row.
    pc.fix_amount("Wallet", "Uber", "65")
    pc.delete("Wallet", "Talabat")
    pc.spend("Wallet", "2026-10-05", "Carrefour", "300")
    assert pc.owns() == "435"

    # He leaves his desk: Profiles & lock › Hand back.
    pc.b.go("Profiles & lock")
    assert pc.b.submit({}, button="Hand back").shows("Mohab is back on My phone, with your changes.")
    rows = phone.register("Wallet")
    assert "Carrefour" in rows and "65" in rows and "Talabat" not in rows
    assert phone.owns() == "435"
    assert not phone.b.open("/").shows("Lent to")
    phone.spend("Wallet", "2026-10-06", "Kiosk", "15")   # the phone writes again
    assert phone.owns() == "420"


def test_3_a_form_left_open_never_saves_over_the_other_devices_work(mohab):
    phone, pc = mohab
    moved(phone, pc)
    # He opens Talabat's sheet on the phone to fix it, is called away, and the PC borrows meanwhile.
    sheet = phone.b.open(f"/transactions/{phone.hand.transaction_id('Wallet', 'Talabat')}/edit-popup?return_to=/")
    borrow(pc)
    pc.fix_amount("Wallet", "Talabat", "180")
    late = phone.b.submit({"amount": "175"}, action="edit-popup", page=sheet, expect=403)
    assert late.shows("Nothing was saved", "Office PC has the ledger now")

    # The PC's own row, open in its register when the ledger goes home (the 15-minute lock, or Hand back).
    txn = pc.hand.transaction_id("Wallet", "Seoudi")
    row = pc.b.open(next(l.href for l in pc.b.go("Wallet").links if f"edit={txn}" in l.href))
    pc.b.go("Profiles & lock")
    pc.b.submit({}, button="Hand back")
    stale = pc.b.submit({"amount": "-250"}, action=f"/register/{txn}", page=row)
    assert stale.path == "/profiles" and stale.shows("On My phone")   # back at the chooser; nothing saved

    rows = phone.register("Wallet")
    assert "180" in rows and "175" not in rows and "200" in rows and "250" not in rows
    assert phone.owns() == "620"


def test_3b_a_save_on_a_lent_phone_says_who_has_the_ledger_and_where_to_go(mohab):
    phone, pc = mohab
    moved(phone, pc)
    wallet = phone.b.go("Accounts", "Wallet")  # the sheet is open before the PC borrows
    add = next(l.href for l in wallet.links if l.attrs.get("aria-label") == "Add transaction")
    borrow(pc)
    assert not any(l.attrs.get("aria-label") == "Add transaction" for l in phone.b.go("Accounts", "Wallet").links)
    assert not any(l.attrs.get("aria-label") == "Add transaction" for l in phone.b.go("Accounts").links)
    phone.b.open(add)
    refused = phone.b.submit({"kind": "out", "date": "2026-10-04", "counterparty": "Cafe", "amount": "40",
                              "category_id": screens.Choose("Food & Groceries")}, button="Save", expect=403)
    assert 'class="phone-appbar"' in refused.html            # a phone page, not bare text
    assert refused.shows("Nothing was saved", "Office PC has the ledger now", "Hand it back on that PC")
    assert phone.b.click("Devices").shows("Office PC", "Has the ledger")
    # An inline save (no page to show) gets one line that says the same.
    inline = phone.client.post("/accounts/new", data={"__session": phone.app.session.token},
                               headers={"X-Requested-With": "fetch"})
    assert inline.status_code == 403 and inline.text == "Lent to Office PC · read only. Nothing was saved."
    assert "Cafe" not in phone.register("Wallet") and "Cafe" not in pc.register("Wallet")


def test_3c_while_a_returned_copy_goes_in_the_phone_says_one_moment(mohab):
    phone, pc = mohab
    moved(phone, pc)
    gate = phone.app.gate
    phone.client.portal.call(gate.set_mode, "closed")   # as sync does while it promotes a returned copy
    try:
        waiting = phone.b.open("/")
        assert waiting.path == "/profiles/checking" and waiting.shows("One moment", "by itself")
        assert phone.b.open("/profiles").path == "/profiles/checking"   # never the chooser
        assert phone.client.get("/profiles/health").json()["locked"] is False  # an open page stays and reloads
    finally:
        phone.client.portal.call(gate.set_mode, "home")
    assert phone.b.open("/profiles/checking").path == "/"


def test_4_he_forgets_to_hand_back_and_the_edits_reach_the_phone_next_morning(mohab):
    phone, pc = mohab
    moved(phone, pc)
    borrow(pc)
    pc.spend("Wallet", "2026-10-05", "Carrefour", "300")
    phone.away()          # he goes home with the phone; the office PC is shut down at night
    pc.close_app()

    # At home the phone reads, and says the PC still has it.
    assert phone.b.open("/").shows("Lent to Office PC")
    devices = phone.b.click("Devices")
    assert devices.shows("Office PC", "Has the ledger", "Only when the PC is lost or broken")

    # Next morning at the office: the PC opens Mohab where it stopped, then hands it back.
    phone.back()
    pc.restart()
    assert pc.b.open("/profiles").shows("On this PC, not handed back")
    assert borrow(pc).path == "/"
    assert "Carrefour" in pc.register("Wallet")
    pc.b.go("Profiles & lock")
    assert pc.b.submit({}, button="Hand back").shows("back on My phone")
    assert "Carrefour" in phone.register("Wallet") and phone.owns() == "350"


def test_5_the_phone_takes_the_ledger_back_from_a_pc_out_of_reach(mohab):
    phone, pc = mohab
    moved(phone, pc)
    borrow(pc)
    pc.spend("Wallet", "2026-10-05", "Office lunch", "120")
    phone.away()
    pc.close_app()        # sealed on the PC: the phone never got Office lunch

    # Travelling for a week, he needs the phone to write: Devices › Take back, ticking what he gives up.
    phone.b.open("/")
    phone.b.click("Devices")
    unticked = phone.b.submit({}, button="Take back", expect=400)
    assert unticked.shows("will not come back")
    taken = phone.b.submit({"confirm": "yes"}, button="Take back")
    assert taken.shows("The ledger is back on this phone")
    phone.spend("Wallet", "2026-10-06", "Kiosk", "15")
    assert phone.owns() == "635"

    # Back at the office, the PC says what happened, keeps its copy to read, and borrows again.
    phone.back()
    pc.restart()
    kept = borrow(pc)
    assert kept.shows("The phone took the ledger back. This copy is kept here, read only.")
    # He reads his lunch in the kept copy, which saves nothing...
    assert "Office lunch" in pc.register("Wallet")
    refused = pc.b.submit({"date": "2026-10-07", "counterparty": "Taxi", "category": "Food & Groceries",
                           "amount": "-30"}, button="Add", page=pc.b.go("Wallet"), expect=403)
    assert refused.shows("Nothing was saved", "Read only on this PC") and refused.link("Profiles & lock")
    # ...closes it and borrows the phone's ledger again, then types the lunch there.
    pc.b.go("Profiles & lock")
    assert pc.b.submit({}, button="Close this copy").shows("Taken back by the phone")
    listing = pc.b.open("/profiles")
    again = pc.b.click(next(l.text for l in listing.links if "/profiles/borrowed?id=" in l.href))
    assert again.shows("Edits made here since then did not go to the phone")
    assert pc.b.submit({"password": PASSWORD}, button="Borrow again").shows("You now edit the phone's ledger")
    pc.b.click("Open finance")
    rows = pc.register("Wallet")
    assert "Kiosk" in rows and "Office lunch" not in rows
    pc.spend("Wallet", "2026-10-05", "Office lunch", "120")
    pc.b.go("Profiles & lock")
    pc.b.submit({}, button="Hand back")
    assert phone.owns() == "515"


def test_6_a_hand_back_to_a_locked_phone_goes_in_when_he_unlocks_it(mohab):
    phone, pc = mohab
    moved(phone, pc)
    borrow(pc)
    pc.spend("Wallet", "2026-10-05", "Carrefour", "300")
    phone.lock()          # the phone locked itself in his pocket
    pc.b.go("Profiles & lock")
    waiting = pc.b.submit({}, button="Hand back")
    assert waiting.shows("My phone has your changes and takes them in when it is unlocked.")
    phone.unlock()        # "Office PC handed the ledger back. Checking it…" while the copy goes in
    phone.wait_while_checking()
    assert "Carrefour" in phone.register("Wallet") and phone.owns() == "350"
    assert not phone.b.open("/").shows("Lent to")
    phone.spend("Wallet", "2026-10-06", "Kiosk", "15")
    assert phone.owns() == "335"


def test_7_a_second_pc_waits_its_turn_and_a_wrong_password_borrows_nothing(mohab, tmp_path):
    phone, office = mohab
    moved(phone, office)
    borrow(office)
    home = Device(tmp_path, "home", 9703, phone=False)
    try:
        connected = pair_phone(phone, home, "Home laptop")
        digits = re.search(r"(\d{3} \d{3})", connected.text).group(1)
        assert connected.shows("Connected to My phone") and phone.b.open("/profiles/devices").shows(digits)
        wrong = borrow(home, password="not my password", expect=400)
        assert wrong.shows("The password is incorrect. It is the profile's password, the same as on the phone.")
        busy = borrow(home, expect=400)
        assert busy.shows("The ledger is lent to Office PC.")
        assert phone.b.open("/profiles/devices").shows("Office PC", "Has the ledger", "Home laptop")

        # The office PC hands back; that evening the home laptop borrows and has the office's edit.
        office.spend("Wallet", "2026-10-05", "Carrefour", "300")
        office.b.go("Profiles & lock")
        office.b.submit({}, button="Hand back")
        assert borrow(home).shows("Borrowed from My phone")
        assert "Carrefour" in home.register("Wallet") and home.owns() == phone.owns() == "350"
        assert phone.b.open("/").shows("Lent to Home laptop")
    finally:
        home.close_app()
