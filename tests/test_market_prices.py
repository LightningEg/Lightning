"""Filling a profile's prices from the price packs it follows: matching holdings to instruments, what is
left for the user, choosing packs, the delta download, a hand-imported market.zip, and the desktop upload
limits for it."""

import gzip
import re
import hashlib
import json
import threading
from datetime import date, timedelta
from decimal import Decimal as D
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from lightning.market import update as market_update
from lightning.market.bundle import Close, Instrument, MarketFile, MarketFileError, pack, write
from lightning.market.packs import MarketSet, chosen, pack_release, read_zip, write_index
from lightning.runtime import app as runtime_app
from lightning.runtime.http import MARKET_IMPORT_PATH, MAX_MARKET_IMPORT_BODY, request_body_limit
from lightning.ui.web import create_app
from lightning.workflows import market_prices
from lightning.workflows.market_prices import MarketPrices, current_set, pack_files, pack_rows
from tests.screens import said

COMI = Instrument("EG:COMI", "Commercial International Bank", "STOCK", "EGP", isin="EGS60121C018", mic="XCAI",
                  ticker="COMI", country="EG", unit="share")
AZS = Instrument("EG:FUND:4104", "AZ Savings Fund", "FUND.FIXED_INCOME", "EGP", country="EG", unit="unit",
                 aliases=("FND:AZS",))
AAPL = Instrument("US:AAPL", "Apple", "STOCK", "USD", isin="US0378331005", mic="XNAS", ticker="AAPL", country="US")
USD = Instrument("USD/EGP", "US dollar", "CURRENCY", "EGP", unit="USD")


def _daily(key, first, last, price):
    day, end, out = date.fromisoformat(first), date.fromisoformat(last), []
    while day <= end:
        out.append(Close(day.isoformat(), key, D(price)))
        day += timedelta(days=1)
    return out


def publish(root, created_at="2026-12-31T22:30:00Z", december="88"):
    """Three packs as the collector writes them: CIB daily except November in egx, a weekly fund NAV in
    eg-funds, the dollar rate in fx; and Apple, in dollars, in us."""
    root.mkdir(parents=True, exist_ok=True)
    cib = _daily("EG:COMI", "2026-09-01", "2026-10-31", "80") + _daily("EG:COMI", "2026-12-01", "2026-12-31", december)
    write(root / "egx", [COMI], cib, created_at, pack="egx")
    write(root / "eg-funds", [AZS], [Close(d, "EG:FUND:4104", D(p)) for d, p in (
        ("2026-09-24", "31.25"), ("2026-10-29", "31.6"), ("2026-11-26", "31.9"), ("2026-12-24", "32.2"))], created_at, pack="eg-funds")
    write(root / "fx", [USD], _daily("USD/EGP", "2026-09-01", "2026-12-31", "48.5"), created_at, pack="fx")
    write(root / "us", [AAPL], _daily("US:AAPL", "2026-09-01", "2026-12-31", "230"), created_at, pack="us")
    write_index(root, created_at)
    return root


def everything(root):
    return MarketSet({p: MarketFile.open(root / p) for p in ("egx", "eg-funds", "fx", "us")})


@pytest.fixture(autouse=True)
def no_bundled_file(monkeypatch, tmp_path):
    monkeypatch.setattr(market_prices, "BUNDLED", tmp_path / "absent" / "market.zip")


@pytest.fixture
def holdings(c, setup):
    accounts, _ = setup
    c.transactions.record_transfer("2026-09-01", accounts["cib"].id, accounts["thndr"].id, "40000")
    made = {"cib": c.assets.create_investment("CIB", "STOCK", "CIB", isin="EGS60121C018"),  # ISIN finds EG:COMI
            "azs": c.assets.create_investment("AZ Savings", "FUND.FIXED_INCOME", "AZS"),      # its alias FND:AZS
            "apple": c.assets.create_investment("Apple", "STOCK", "AAPL", mic="XNAS"),        # priced in pounds here
            "nope": c.assets.create_investment("Nope fund", "FUND.EQUITY", "NOPE")}
    # A US listing is created in USD now; this one stands for an older holding kept in pounds.
    c.db.execute("UPDATE financial_assets SET currency='EGP' WHERE id=?", (made["apple"].id,))
    for asset in made.values():
        c.investments.buy("2026-09-02", accounts["thndr"].id, asset.id, "10", "50")
    return made


def test_filling_matches_each_holding_and_leaves_the_rest_for_you(c, holdings, tmp_path):
    c.assets.set_price(holdings["cib"].id, "2026-10-31", "99")  # typed: wins over the file on that day
    report = MarketPrices(c.assets, c.reporting).fill(everything(publish(tmp_path / "m")), date(2026, 12, 31))
    assert report.matched == ["CIB", "AZ Savings"] and report.unmatched == ["Nope fund"]
    assert report.other_currency == ["Apple"]  # a dollar price is never silently converted
    assert report.missing == [("CIB", "2026-11-30")]  # no CIB close within ten days of it
    assert report.added == 3 + 4  # CIB Sep, Oct, Dec (Dec 31 is also its latest); the fund's four month-ends
    assert c.assets.get_asset(holdings["cib"].id).market_key == "EG:COMI"
    assert c.assets.get_asset(holdings["azs"].id).market_key == "EG:FUND:4104"
    september = c.reporting.value_of(holdings["cib"].id, D(1), "2026-09-30")
    assert (september.price, september.source) == (D("80"), "MARKET")
    october = c.reporting.value_of(holdings["cib"].id, D(1), "2026-10-31")
    assert (october.price, october.source) == (D("99"), "MANUAL")
    fund = c.reporting.value_of(holdings["azs"].id, D(1), "2026-11-30")
    assert (fund.price, fund.price_date) == (D("31.9"), "2026-11-26")
    text = report.summary()
    assert text.startswith("Filled 7 prices for 2 investments from the price files of 2026-12-31.")
    assert "1 still missing: CIB 2026-11-30." in text and "Not in the packs you follow: Nope fund." in text and "Apple" in text


class Server:
    """Serves a published market folder over HTTP, gzipped when asked, and logs what was fetched."""

    def __init__(self, root, damage=""):
        self.root, self.damage, self.fetched = root, damage, []
        server = self

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                name = self.path.lstrip("/")
                server.fetched.append(name)
                path = server.root / name
                if not path.is_file():
                    self.send_error(404)
                    return
                data = b"damaged" if name == server.damage else path.read_bytes()
                self.send_response(200)
                if "gzip" in self.headers.get("Accept-Encoding", ""):
                    data = gzip.compress(data)
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(autouse=True)
def local_server_without_proxy(monkeypatch):
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")


def test_updating_downloads_only_what_changed_and_never_keeps_a_damaged_file(tmp_path):
    published, local = publish(tmp_path / "published") / "egx", tmp_path / "profile" / "market" / "egx"
    with Server(published) as server:
        changed = market_update.update_folder(local, server.url)
        assert changed == sorted(json.loads((published / "manifest.json").read_text())["files"])
        assert MarketFile.open(local).latest("EG:COMI") == Close("2026-12-31", "EG:COMI", D("88"))
        server.fetched.clear()
        assert market_update.update_folder(local, server.url) == [] and server.fetched == ["manifest.json"]

        publish(published.parent, "2027-01-01T22:30:00Z", december="90")  # only December and the year's month-ends change
        server.damage = "daily/2026-12.csv"
        with pytest.raises(MarketFileError, match="arrived damaged"):
            market_update.update_folder(local, server.url)
        assert MarketFile.open(local).created_at == "2026-12-31T22:30:00Z"  # the previous file is untouched
        server.damage, server.fetched[:] = "", []
        assert market_update.update_folder(local, server.url) == ["daily/2026-12.csv", "monthly/2026.csv"]
        assert MarketFile.open(local).latest("EG:COMI").close == D("90")


def test_only_followed_packs_are_downloaded(tmp_path):
    published, root = publish(tmp_path / "published"), tmp_path / "profile" / "market"
    with Server(published) as server:
        changed, missing = market_update.update_packs(root, ["egx", "gcc"], server.url)
    assert list(changed) == ["egx"] and missing == ["gcc"]  # the Gulf pack is not published here
    assert sorted(p.name for p in root.iterdir()) == ["egx", "index.json"]
    assert chosen("") == ["egx", "eg-funds", "fx"] and chosen("none") == [] and chosen("us,../x") == ["us"]


def test_a_published_manifest_cannot_name_a_file_outside_the_folder(tmp_path):
    published = publish(tmp_path / "published") / "egx"
    manifest = json.loads((published / "manifest.json").read_text())
    manifest["files"]["../outside.csv"] = {"sha256": hashlib.sha256(b"x").hexdigest()}
    (published / "manifest.json").write_text(json.dumps(manifest))
    with Server(published) as server, pytest.raises(MarketFileError, match="may not hold"):
        market_update.update_folder(tmp_path / "profile" / "market" / "egx", server.url)
    assert not (tmp_path / "profile").exists()


def test_a_release_zip_holds_several_packs_and_a_pack_zip_names_its_own(tmp_path):
    root = publish(tmp_path / "published")
    release = read_zip(pack_release(root, tmp_path / "market.zip", ["egx", "fx"]).read_bytes())
    assert sorted(release) == ["egx", "fx"] and release["fx"].latest("USD/EGP").close == D("48.5")
    single = read_zip(pack(root / "us", tmp_path / "us.zip").read_bytes())
    assert list(single) == ["us"]
    write(tmp_path / "loose", [USD], [], "2026-12-31")
    with pytest.raises(MarketFileError, match="does not say which pack"):
        read_zip(pack(tmp_path / "loose", tmp_path / "loose.zip").read_bytes())


def test_the_prices_page_follows_markets_updates_imports_and_fills(c, holdings, tmp_path):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/investments/prices").text
    assert "Egyptian stocks" in page and "Not downloaded yet" in page and "Fill from price files" not in page
    assert "No price files yet" in client.post("/investments/prices/market/fill").text

    older = pack_release(publish(tmp_path / "old", "2026-11-01T22:30:00Z"), tmp_path / "old.zip", ["egx", "eg-funds"])
    newer = pack_release(publish(tmp_path / "new"), tmp_path / "new.zip", ["egx", "eg-funds"])
    done = client.post("/investments/prices/market/import", files={"file": ("market.zip", newer.read_bytes(), "application/zip")})
    assert "Imported Egyptian funds, Egyptian stocks. Filled 7 prices for 2 investments" in done.text
    assert pack_files(c.data_dir)["egx"] == {"created_at": "2026-12-31", "origin": "downloaded", "last_date": "2026-12-31",
                                             "instruments": 1}
    page = client.get("/investments/prices").text
    assert "Fill from price files" in page and said("2026-12-31, downloaded") in page and "price file" in page
    refused = client.post("/investments/prices/market/import", files={"file": ("market.zip", older.read_bytes(), "application/zip")})
    assert "Nothing was imported. Kept your newer Egyptian funds, Egyptian stocks." in refused.text
    junk = client.post("/investments/prices/market/import", files={"file": ("market.zip", b"not a zip", "application/zip")})
    assert "not a Lightning market file" in junk.text

    settings = client.get("/investments/prices/markets").text
    assert "Gulf stocks" in settings and "Saudi Exchange" in settings and "European stocks and ETFs" in settings
    assert 'value="egx" checked' in settings and 'value="gcc" ' in settings and 'value="gcc" checked' not in settings
    saved = client.post("/investments/prices/markets", data={"pack": ["egx", "us"]})
    assert "Saved." in saved.text and c.settings.get("market_packs") == "egx,us"
    # A fund is held, so Egyptian funds stays followed and its file stays (audit 2026-10-15).
    assert (c.data_dir / "market" / "eg-funds").exists()
    publish(tmp_path / "published", "2027-01-01T22:30:00Z", december="90")
    c.settings.set("market_url", "http://127.0.0.1:1/")  # nothing listens there
    assert "Could not reach the price file" in client.post("/investments/prices/market/update").text
    assert current_set(c.data_dir, ["egx"]).created_at == "2026-12-31T22:30:00Z"
    with Server(tmp_path / "published") as server:
        c.settings.set("market_url", server.url)
        updated = client.post("/investments/prices/markets", data={"pack": ["egx", "us", "gcc"], "update": "1"}).text
    assert "Updated Egyptian stocks, US stocks and ETFs. Not published yet: Gulf stocks. Filled" in updated
    assert c.reporting.value_of(holdings["cib"].id, D(1), "2026-12-31").price == D("90")
    rows = {r["id"]: r for r in pack_rows(c.data_dir, chosen(c.settings.get("market_packs")))}
    assert rows["us"]["on"] and rows["us"]["bytes"] > 0 and rows["us"]["have"]["origin"] == "downloaded"
    assert client.post("/investments/prices/markets", data={}).status_code == 200 and chosen(c.settings.get("market_packs")) == []
    # Unticking everything still follows the markets of what is held (stocks on EGX, an Egyptian fund).
    assert "You follow no markets" not in client.get("/investments/prices").text


def test_the_desktop_window_takes_one_bounded_market_file():
    assert request_body_limit(MARKET_IMPORT_PATH) == MAX_MARKET_IMPORT_BODY == 40 * 1024 * 1024
    assert runtime_app._form_file_limit(MARKET_IMPORT_PATH) == 1 and runtime_app._form_part_limit(MARKET_IMPORT_PATH) == MAX_MARKET_IMPORT_BODY
    assert runtime_app._form_file_limit("/investments/prices") == 0


# ------------------------------------------------------------------ filling without being asked
def _bundle(tmp_path, monkeypatch, created_at="2026-12-31T22:30:00Z"):
    """The default packs as a release carries them (lightning/market/market.zip)."""
    root = publish(tmp_path / f"published-{created_at[:10]}", created_at)
    path = tmp_path / f"market-{created_at[:10]}.zip"
    pack_release(root, path, ["egx", "eg-funds", "fx"])
    monkeypatch.setattr(market_prices, "BUNDLED", path)
    return path


def test_the_app_fills_from_its_own_files_once_per_file_and_month(c, holdings, tmp_path, monkeypatch):
    from lightning.workflows.market_prices import fill_if_due
    assert fill_if_due(c, date(2026, 12, 31)) is None  # no price files at all: nothing happens
    _bundle(tmp_path, monkeypatch)
    first = fill_if_due(c, date(2026, 12, 31))  # first run
    assert first is not None and first.matched == ["CIB", "AZ Savings"]
    assert c.reporting.value_of(holdings["cib"].id, D(1), "2026-09-30").source == "MARKET"
    assert fill_if_due(c, date(2026, 12, 31)) is None  # same file, same month: quiet
    assert fill_if_due(c, date(2027, 1, 1)) is not None  # a new month fills again
    _bundle(tmp_path, monkeypatch, "2027-01-02T13:30:00Z")
    assert fill_if_due(c, date(2027, 1, 3)) is not None  # a newer file fills again


def test_needs_you_lists_missing_month_ends_until_they_are_typed(c, holdings, tmp_path, monkeypatch):
    from lightning.workflows.market_prices import fill_followed
    from lightning.workflows.review import ReviewInbox
    _bundle(tmp_path, monkeypatch)
    fill_followed(c, date(2026, 12, 31))
    item = next(i for i in ReviewInbox(c).items(date(2026, 12, 31)) if "missing" in i["label"])
    assert item["label"] == "1 price missing" and item["detail"] == "CIB, November 2026."
    assert (item["href"], item["action"]) == ("/investments/prices#missing", "Get prices")
    c.assets.set_price(holdings["cib"].id, "2026-11-30", "85")
    assert not any("missing" in i["label"] for i in ReviewInbox(c).items(date(2026, 12, 31)))


def test_a_read_only_copy_never_fills(tmp_path, monkeypatch):
    from lightning.bootstrap import build
    from lightning.workflows.market_prices import fill_followed, fill_if_due
    _bundle(tmp_path, monkeypatch)
    path = tmp_path / "copy.db"
    build(path).db.close()
    reader = build(path, read_only=True)
    assert fill_if_due(reader, date(2026, 12, 31)) is None and fill_followed(reader, date(2026, 12, 31)) is None
    reader.db.close()


def test_opening_a_profile_fills_but_a_reader_does_not(tmp_path, monkeypatch):
    from lightning.runtime.roles import SessionRole
    from lightning.runtime.session import ProfileSession
    calls = []
    monkeypatch.setattr(market_prices, "fill_if_due", lambda c, on: calls.append(c.db.read_only))
    session = ProfileSession(tmp_path / "Documents" / "Lightning")
    session.prepare("Home", "pw", "pw", "Which school?", "El Orman")
    session.confirm(session.pending.recovery)
    path = str(session.paths.db_path)
    session.close()
    session.unlock(path, "pw", role=SessionRole.READER)
    session.close()
    session.unlock(path, "pw")
    session.close()
    assert calls == [False, False]  # first run and the later unlock; never the read-only copy


def test_a_brokerage_statement_import_fills_prices(c, setup, monkeypatch):
    from lightning.ui.routes import bank_imports as route
    from tests.test_bank_imports import _upload_and_map
    accounts, cats = setup
    calls = []
    monkeypatch.setattr(route, "fill_followed", lambda c, on: calls.append(on))
    client = TestClient(create_app(c))
    for account in ("thndr", "cib"):
        account_id = accounts[account].id
        upload = _upload_and_map(client, account_id, f"{account}.csv", f"Date,Counterparty,Amount\n2026-09-22,Fee {account},-14\n".encode(),
                                 {"Date": "Date", "Amount": "Amount", "Counterparty": "Counterparty"})
        batch_id = int(upload.headers["location"].rsplit("/", 1)[-1])
        row_id = c.bank_imports.preview(batch_id)[1][0]["_import_row_id"]
        posted = client.post(f"/accounts/{account_id}/import/{batch_id}/confirm", data={
            f"counterparty_{row_id}": f"Fee {account}", f"counterparty_choice_{row_id}": "new",
            f"category_{row_id}": str(cats["EXP.PERSONAL.FOOD"].id), f"date_{row_id}": "2026-09-22",
            f"amount_{row_id}": "-14"})
        assert "Import complete: 1 posted" in posted.text, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", posted.text))[:1500]
    assert len(calls) == 1  # the brokerage statement, not the bank one


def test_a_release_carries_the_default_packs_downloaded_and_checked(tmp_path, capsys):
    from tools.market.__main__ import main as market_cli
    root = publish(tmp_path / "published")
    out = tmp_path / "app" / "market.zip"
    with Server(root) as server:
        assert market_cli(["release", "--out", str(out), "--url", server.url, "--required"]) == 0
    assert sorted(read_zip(out.read_bytes())) == ["fx"]  # only default packs we may republish
    assert "fx of 2026-12-31" in capsys.readouterr().out
    out.unlink()
    with Server(tmp_path / "nothing-published") as server:
        assert market_cli(["release", "--out", str(out), "--url", server.url]) == 0  # a test build warns
        assert market_cli(["release", "--out", str(out), "--url", server.url, "--required"]) == 1
    assert not out.exists()


def test_a_tagged_release_build_refuses_to_ship_without_price_files(tmp_path):
    from tests.test_profile_packaging import _packager
    package_app = _packager()
    bundle = tmp_path / "Lightning"
    (bundle / "_internal" / "lightning" / "market").mkdir(parents=True)
    assert package_app.price_files(bundle) == "none"
    pack_release(publish(tmp_path / "published"), bundle / "_internal" / "lightning" / "market" / "market.zip",
                 ["egx", "fx"])
    assert package_app.price_files(bundle) == "egx of 2026-12-31, fx of 2026-12-31"
    workflow = (package_app.ROOT / ".github" / "workflows" / "desktop-probe.yml").read_text(encoding="utf-8")
    assert workflow.index("python -m tools.market release") < workflow.index("pyinstaller --clean")
    assert "github.ref_type == 'tag' && '--required'" in workflow


def test_only_sources_that_allow_it_are_published_and_each_is_cited(tmp_path):
    from lightning.market.packs import PACKS, publishable
    assert publishable(PACKS) == ["fx"]  # public bank rates; stock and fund sources still are not published
    assert all(p.source for p in PACKS.values())
    assert json.loads((publish(tmp_path / "m") / "index.json").read_text())["packs"]["fx"]["source"] \
        == "Banque Misr (banquemisr.com; transfer buy/sell midpoint)"
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "market-data.yml").read_text(encoding="utf-8")
    assert '--root market-data --packs "$PUBLIC"' in text and 'publishable(' in text


def test_the_pages_cite_the_source_of_the_prices(c, holdings, tmp_path, monkeypatch):
    _bundle(tmp_path, monkeypatch)
    client = TestClient(create_app(c))
    text = client.get("/investments/prices").text
    assert "Source: " in text and "Banque Misr (banquemisr.com; transfer buy/sell midpoint)." in text
    page = client.get("/investments/prices/markets").text
    assert "Source: Banque Misr (banquemisr.com; transfer buy/sell midpoint)" in page and "Source: TradingView" in page


def test_a_pack_without_prices_is_never_offered_or_shipped(tmp_path):
    from lightning.market.bundle import write
    from lightning.market.packs import write_index
    from tools.market.__main__ import main as market_cli
    root = tmp_path / "published"
    write(root / "fx", [], [], "2026-12-31T22:30:00Z", health={"cbe": {"ok": False}}, pack="fx")
    assert write_index(root, "2026-12-31T22:30:00Z")["packs"] == {}  # its source failed: nothing to offer
    with Server(root) as server:
        assert market_cli(["release", "--out", str(tmp_path / "m.zip"), "--url", server.url, "--required"]) == 1


def test_the_collector_asks_like_a_browser_and_names_itself():
    from lightning.market.http import HEADERS, USER_AGENT
    assert USER_AGENT.startswith("Mozilla/5.0 (compatible; Lightning-market-collector")
    assert {"Accept", "Accept-Language"} <= set(HEADERS)
