"""The price collector (tools/market): each adapter on a sample in its source's answer format, the checks,
and whole runs of several packs against a fake network, including a source that fails."""

import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from lightning.market.bundle import Close, MarketFile, write
from tools.market import checks
from tools.market.alarm import alarms
from tools.market.collect import _settle_keys, backfill, collect
from lightning.market.model import Quote, SourceError, SourceResult
from lightning.market.sources import banque_misr, cbe, mubasher, tradingview, yahoo
from lightning.market.iso import VENUE_CURRENCY

SAMPLES = Path(__file__).parent / "fixtures" / "market"


def sample(name):
    text = (SAMPLES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


# -- adapters, on recorded samples -----------------------------------------------------------------
def test_tradingview_lists_egx_and_us_with_iso_venues():
    egx = tradingview.parse(sample("tradingview_egx.json"), tradingview.BOARDS["egx"][0], "2026-10-05", "tradingview-egx")
    assert [(i.key, i.mic, i.country, i.currency) for i in egx.instruments] == [
        ("EG:COMI", "XCAI", "EG", "EGP"), ("EG:ETEL", "XCAI", "EG", "EGP")]  # no close, not EGX: skipped
    assert egx.quotes[0] == Quote("EG:COMI", "2026-10-05", D("85.25"), "tradingview-egx")
    us = tradingview.parse(sample("tradingview_us.json"), tradingview.BOARDS["us"][0], "2026-10-05", "tradingview-us")
    assert [(i.key, i.mic, i.category) for i in us.instruments] == [
        ("US:AAPL", "XNAS", "STOCK"), ("US:BRK.B", "XNYS", "STOCK"), ("US:SPY", "ARCX", "FUND.OTHER")]
    with pytest.raises(SourceError, match="data list"):
        tradingview.parse({"error": "blocked"}, tradingview.BOARDS["egx"][0], "2026-10-05", "tradingview-egx")


def test_gulf_and_european_boards_use_iso_venues_and_whole_currency_units():
    uae = tradingview.parse(sample("tradingview_uae.json"), tradingview.BOARDS["gcc"][1], "2026-10-05", "tradingview-gcc")
    assert [(i.key, i.mic, i.country) for i in uae.instruments] == [
        ("AE:EMAAR", "XDFM", "AE"), ("AE:ALDAR", "XADS", "AE"), ("AE:EMAAR", "XADS", "AE")]  # a bad ticker is left out
    _settle_keys(uae, {})  # one ticker on two Emirates exchanges: the second is published as KEY-MIC
    assert [i.key for i in uae.instruments] == ["AE:EMAAR", "AE:ALDAR", "AE:EMAAR-XADS"]
    assert [(q.key, q.close) for q in uae.quotes] == [
        ("AE:EMAAR", D("14.35")), ("AE:ALDAR", D("8.12")), ("AE:EMAAR-XADS", D("14.4"))]
    london = tradingview.parse(sample("tradingview_uk.json"), tradingview.BOARDS["europe"][0], "2026-10-05", "tradingview-europe")
    assert [(i.key, i.mic, i.currency, i.category) for i in london.instruments] == [
        ("GB:VOD", "XLON", "GBP", "STOCK"), ("GB:VWRA", "XLON", "USD", "FUND.OTHER")]  # Xetra is another board
    assert london.quotes[0].close == D("0.7182")  # 71.82 pence is published as pounds
    kuwait = tradingview.parse({"data": [{"s": "KSE:NBK", "d": ["NBK", "National Bank of Kuwait", 912, "KWF", "stock",
                                                                "common", "KSE"]}]},
                               tradingview.BOARDS["gcc"][3], "2026-10-05", "tradingview-gcc")
    assert (kuwait.instruments[0].key, kuwait.instruments[0].mic, kuwait.instruments[0].currency,
            kuwait.quotes[0].close) == ("KW:NBK", "XKUW", "KWD", D("0.912"))  # fils as dinars
    published = {"AE:EMAAR": uae.instruments[0]}
    later = SourceResult("tradingview-gcc", [replace(uae.instruments[0], mic="XADS")],
                         [Quote("AE:EMAAR", "2026-10-06", D("14.5"), "tradingview-gcc")])
    _settle_keys(later, published)  # a published key keeps its venue across runs
    assert later.instruments[0].key == later.quotes[0].key == "AE:EMAAR-XADS"


def test_mubasher_funds_and_their_history():
    funds = mubasher.parse_funds(sample("mubasher_funds.json"), {4104: "FUND.FIXED_INCOME"})
    assert [(i.key, i.name, i.currency, i.category) for i in funds.instruments][:2] == [
        ("EG:FUND:4104", "AZ Savings Fund", "EGP", "FUND.FIXED_INCOME"),
        ("EG:FUND:2207", "Beltone Fixed Income Fund Issuance 1 USD", "USD", "FUND.OTHER")]
    assert [(q.key, q.date, q.close) for q in funds.quotes] == [
        ("EG:FUND:4104", "2026-09-24", D("31.254321")), ("EG:FUND:2207", "2026-09-20", D("1.0412"))]
    history = mubasher.parse_history(sample("mubasher_history.csv"), "EG:FUND:4104")
    assert [(q.date, q.close) for q in history] == [("2022-12-18", D("10.01437")), ("2022-12-19", D("10.02"))]
    with pytest.raises(SourceError, match="paging|pages"):
        mubasher.parse_funds({"numberOfPages": 2, "rows": []})


def test_cbe_publishes_the_mid_rate_per_one_unit():
    rates = cbe.parse(sample("cbe_rates.html"), "2026-10-05")
    found = {q.key: q for q in rates.quotes}
    assert found["USD/EGP"] == Quote("USD/EGP", "2026-10-05", D("52.4315"), "cbe")  # (52.3624 + 52.5006) / 2
    assert found["JPY/EGP"].close == D("0.351508")  # quoted per 100 yen, published per yen
    assert set(found) == {"USD/EGP", "EUR/EGP", "JPY/EGP", "SAR/EGP", "GBP/EGP"}
    with pytest.raises(SourceError, match="no US dollar"):
        cbe.parse("<table><tr><td>Euro</td><td>1</td><td>2</td></tr></table>", "2026-10-05")


def test_banque_misr_uses_dated_transfer_quotes_and_rejects_block_pages():
    rates = banque_misr.parse(sample("banque_misr_rates.html"), "2026-10-07")
    found = {q.key: q for q in rates.quotes}
    assert len(found) == 10
    assert found["USD/EGP"] == Quote("USD/EGP", "2026-10-07", D("52.39"), "banque-misr")
    assert found["CNY/EGP"].close == D("7.810035")  # banknotes are zero; use transfer quotes
    assert found["JPY/EGP"].close == D("0.331017")  # page quotes 100 yen
    with pytest.raises(SourceError, match="dated timestamp"):
        banque_misr.parse("<title>Request Rejected</title>", "2026-10-07")


def test_replacing_an_fx_source_clears_its_old_failure(tmp_path):
    root = tmp_path / "market"
    collect(root, FakeNet(), "2026-10-01", "2026-10-01T15:00:00Z", ("fx",))
    health_file = root / "fx" / "health.json"
    health = json.loads(health_file.read_text(encoding="utf-8"))
    health["cbe"] = {"ok": False, "error": "old source blocked", "failures_in_a_row": 8}
    market = MarketFile.open(root / "fx")
    write(root / "fx", list(market.instruments().values()), market.daily_closes(), "2026-10-01T15:30:00Z",
          health, pack="fx", source="Banque Misr")

    report = collect(root, FakeNet(), "2026-10-01", "2026-10-01T16:00:00Z", ("fx",))
    assert "cbe" not in report["fx"]
    assert report["fx"]["banque-misr"]["ok"]
    assert "cbe" not in json.loads(health_file.read_text(encoding="utf-8"))


def test_yahoo_history_is_put_back_to_the_prices_that_traded():
    quotes = yahoo.parse(sample("yahoo_chart.json"), "EG:COMI")
    assert [(q.date, q.close) for q in quotes] == [  # a 2:1 split on the 26th: earlier closes doubled back
        ("2025-09-24", D("80")), ("2025-09-25", D("82")), ("2025-09-26", D("42.5"))]
    assert yahoo.symbol_for("EG:COMI") == "COMI.CA" and yahoo.symbol_for("US:BRK.B") == "BRK-B"
    assert yahoo.symbol_for("EG:FUND:4104") is None and yahoo.symbol_for("USD/EGP") == "EGP=X"


# -- checks -----------------------------------------------------------------------------------------
def _q(key, day, close, source):
    return Quote(key, day, D(close), source)


def test_checks_hold_back_a_jump_unless_a_second_source_or_the_official_one_says_so():
    published = {"EG:COMI": [Close("2026-10-01", "EG:COMI", D("80"))], "USD/EGP": [Close("2026-10-01", "USD/EGP", D("48"))],
                 "EG:FUND:1": [Close("2026-10-01", "EG:FUND:1", D("400"))]}
    categories = {"EG:COMI": "STOCK", "EG:ETEL": "STOCK", "USD/EGP": "CURRENCY", "EG:FUND:1": "FUND.EQUITY"}
    accepted, problems = checks.accept([
        _q("EG:COMI", "2026-10-02", "120", "tradingview-egx"),     # +50%, alone: held back
        _q("USD/EGP", "2026-10-02", "70", "cbe"),                  # +46%, official: used
        _q("EG:FUND:1", "2026-10-02", "10", "mubasher-funds"),     # 1:40 unit split: used, reported
        _q("EG:ETEL", "2026-10-02", "41.9", "tradingview-egx"),    # nothing published yet: used
        _q("EG:ETEL", "2026-10-02", "43.0", "yahoo-latest"),       # disagrees by 2.6%: reported
        _q("EG:COMI", "2027-01-01", "80", "tradingview-egx"),      # in the future: refused
    ], published, categories, "2026-10-02")
    assert sorted((q.key, q.close) for q in accepted) == [
        ("EG:ETEL", D("41.9")), ("EG:FUND:1", D("10")), ("USD/EGP", D("70"))]
    text = "\n".join(problems)
    assert "EG:COMI 2026-10-02 held back" in text and "unit split" in text and "in the future" in text
    assert "tradingview-egx says 41.9, yahoo-latest says 43.0" in text

    confirmed, _ = checks.accept([_q("EG:COMI", "2026-10-02", "120", "tradingview-egx"),
                                  _q("EG:COMI", "2026-10-02", "120.5", "yahoo-latest")], published, categories, "2026-10-02")
    assert confirmed == [_q("EG:COMI", "2026-10-02", "120", "tradingview-egx")]  # a second source agrees


# -- whole runs against a fake network --------------------------------------------------------------
class FakeNet:
    """Answers each source's URL with made-up rows in its format; `failing` names sources that are down."""

    def __init__(self, failing=(), egx_close="85.25"):
        self.failing, self.egx_close = set(failing), egx_close

    def _fail(self, name):
        if name in self.failing:
            raise SourceError(f"{name} answered HTTP 403")

    def post_json(self, url, payload):
        screener = url.split("/")[-2]
        if screener == "egypt":
            self._fail("tradingview-egx")
            rows = [{"s": f"EGX:T{i:03d}", "d": [f"T{i:03d}", f"Company {i}", 10 + i, "EGP", "stock", "common", "EGX"]}
                    for i in range(160)]
            rows.append({"s": "EGX:COMI", "d": ["COMI", "CIB", float(self.egx_close), "EGP", "stock", "common", "EGX"]})
            return {"data": rows}
        board_pack = next(((pack, board) for pack in ("gcc", "europe") for board in tradingview.BOARDS[pack]
                           if board.screener == screener), None)
        if board_pack:
            pack, board = board_pack
            self._fail(f"tradingview-{pack}")
            exchange = sorted(board.venues)[0]
            mic = board.venues[exchange]
            currency = VENUE_CURRENCY[mic]
            is_fund = any(f.get("right") == "fund" for f in payload.get("filter", []))
            kind, subtype = ("fund", "etf") if is_fund else ("stock", "common")
            wanted = board.etfs if is_fund else board.stocks
            count = min(70, wanted)
            rows = []
            for i in range(count):
                ticker = f"{screener[:2].upper()}{'F' if is_fund else 'S'}{i:03d}"
                rows.append({"s": f"{exchange}:{ticker}", "d": [ticker, f"{screener} {kind} {i}",
                              20 + i, currency, kind, subtype, exchange]})
            return {"data": rows}
        self._fail("tradingview-us")
        kind = "fund" if payload["filter"][1]["right"] == "fund" else "stock"
        count = 100 if kind == "fund" else 420
        return {"data": [{"s": f"NASDAQ:{kind[0].upper()}{i:03d}", "d": [f"{kind[0].upper()}{i:03d}", f"{kind} {i}",
                                                                         50 + i, "USD", kind, "etf" if kind == "fund" else "common",
                                                                         "NASDAQ"]} for i in range(count)]}

    def get_json(self, url, params=None):
        if "mubasher" in url:
            self._fail("mubasher-funds")
            return {"numberOfPages": 1, "rows": [{"fundId": i, "name": f"Fund {i}", "price": 10 + i, "date": "1 October 2026"}
                                                 for i in range(1, 111)]}
        self._fail("yahoo")
        return sample("yahoo_chart.json")

    def get_text(self, url, params=None):
        if "banquemisr.com" in url:
            self._fail("banque-misr")
            return sample("banque_misr_rates.html").replace("07-10-2026", "01-10-2026")
        self._fail("mubasher-history")
        return sample("mubasher_history.csv")


PACKS = ("egx", "eg-funds", "fx", "us", "gcc", "europe")


def test_a_run_writes_one_folder_per_pack_and_a_failing_source_keeps_its_last_prices(tmp_path):
    root = tmp_path / "market"
    report = collect(root, FakeNet(), "2026-10-01", "2026-10-01T22:30:00Z", PACKS)  # a Thursday: every pack trades
    assert all(report[pack][name]["ok"] for pack, name in (("egx", "tradingview-egx"), ("eg-funds", "mubasher-funds"),
                                                            ("fx", "banque-misr"), ("us", "tradingview-us"),
                                                            ("gcc", "tradingview-gcc"), ("europe", "tradingview-europe")))
    counts = {pack: len(MarketFile.open(root / pack).instruments()) for pack in PACKS}
    assert counts == {"egx": 161, "eg-funds": 110, "fx": 10, "us": 520, "gcc": 350, "europe": 850}
    assert MarketFile.open(root / "egx").close_on("EG:COMI", "2026-10-01").close == D("85.25")
    assert MarketFile.open(root / "fx").close_on("USD/EGP", "2026-10-01").close == D("52.39")
    assert MarketFile.open(root / "gcc").manifest["pack"] == "gcc"
    gcc_market = MarketFile.open(root / "gcc")
    assert not any(i.mic == "XMUS" for i in gcc_market.instruments().values())  # no Oman board: TradingView has none
    europe_market = MarketFile.open(root / "europe")
    assert {i.mic for i in europe_market.instruments().values()} >= {"XSTO", "XCSE", "XHEL", "XICE"}
    assert {(i.mic, i.currency) for i in europe_market.instruments().values()} >= {
        ("XSTO", "SEK"), ("XCSE", "DKK"), ("XHEL", "EUR"), ("XICE", "ISK")}
    index = json.loads((root / "index.json").read_text())
    assert sorted(index["packs"]) == sorted(PACKS) and index["packs"]["gcc"]["name"] == "Gulf stocks"
    assert index["packs"]["egx"]["instruments"] == 161 and index["packs"]["egx"]["bytes"] > 0

    # Friday: EGX, Egyptian funds and Banque Misr do not trade, the Gulf does; nothing is lost.
    report = collect(root, FakeNet(), "2026-10-02", "2026-10-02T22:30:00Z", PACKS)
    assert report["egx"]["tradingview-egx"]["checked_at"] == "2026-10-01T22:30:00Z"  # skipped, unchanged
    assert report["gcc"]["tradingview-gcc"]["checked_at"] == "2026-10-02T22:30:00Z"
    assert MarketFile.open(root / "fx").close_on("USD/EGP", "2026-10-04").close == D("52.39")  # the last rate stays

    # Sunday: the bank page is down and a 60% jump in CIB from one source is held back; both are reported.
    report = collect(root, FakeNet(failing={"banque-misr"}, egx_close="136.4"), "2026-10-04", "2026-10-04T22:30:00Z", PACKS)
    assert MarketFile.open(root / "egx").latest("EG:COMI") == Close("2026-10-01", "EG:COMI", D("85.25"))
    assert any("EG:COMI 2026-10-04 held back" in p for p in report["egx"]["_run"]["problems"])
    bank_health = report["fx"]["banque-misr"]
    assert bank_health["ok"] is False and bank_health["failures_in_a_row"] == 1 and "403" in bank_health["error"]
    assert bank_health["last_ok"] == "2026-10-01T22:30:00Z"
    assert MarketFile.open(root / "fx").latest("USD/EGP").date == "2026-10-01"
    assert alarms(root)["failing"] == []  # one failure is not yet an issue

    collect(root, FakeNet(failing={"banque-misr"}), "2026-10-05", "2026-10-05T22:30:00Z", ("fx",))
    assert [a["name"] for a in alarms(root)["failing"]] == ["fx/banque-misr"] and alarms(root)["failing"][0]["failures"] == 2
    collect(root, FakeNet(), "2026-10-06", "2026-10-06T22:30:00Z", ("fx",))
    assert alarms(root)["failing"] == [] and "fx/banque-misr" in alarms(root)["ok"]  # recovered


def test_a_source_that_answers_too_little_counts_as_failing(tmp_path):
    class Thin(FakeNet):
        def get_json(self, url, params=None):
            return {"numberOfPages": 1, "rows": [{"fundId": 1, "name": "One fund", "price": 10, "date": "1 October 2026"}]}

    report = collect(tmp_path / "m", Thin(), "2026-10-01", "2026-10-01T22:30:00Z", packs=("eg-funds",))
    assert report["eg-funds"]["mubasher-funds"]["ok"] is False
    assert "fewer than the 100 expected" in report["eg-funds"]["mubasher-funds"]["error"]


def test_backfill_brings_whole_histories_into_the_pack_that_lists_them(tmp_path):
    root = tmp_path / "market"
    collect(root, FakeNet(), "2026-10-01", "2026-10-01T22:30:00Z", ("egx", "eg-funds"))
    report = backfill(root, FakeNet(), ["EG:COMI", "EG:FUND:4", "EG:NOPE"], "2026-10-01", "2026-10-01T23:00:00Z")
    assert MarketFile.open(root / "egx").close_on("EG:COMI", "2025-09-25") == Close("2025-09-25", "EG:COMI", D("82"))
    assert MarketFile.open(root / "eg-funds").close_on("EG:FUND:4", "2022-12-19") == Close("2022-12-19", "EG:FUND:4", D("10.02"))
    assert any("EG:NOPE: not in the instrument list" in p for p in report["_run"]["problems"])


def test_the_schedules_run_each_pack_after_its_market_closes():
    import re

    from lightning.market.packs import PACKS as REGISTRY

    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "market-data.yml").read_text(encoding="utf-8")
    crons = re.findall(r"- cron: '([^']+)'", workflow)  # no YAML library: the locked test set has none
    routed = dict(re.findall(r'"([0-9*, -]+)"\) packs=([a-z,-]+) ;;', workflow))
    assert sorted(routed) == sorted(crons)
    for pack in REGISTRY.values():
        cron = next(c for c, packs in routed.items() if pack.id in packs.split(","))
        minute, hour, _, _, weekdays = cron.split()
        assert f"{int(hour):02d}:{int(minute):02d}" == pack.final_utc, pack.id
        first, last = (int(d) for d in weekdays.split("-"))
        assert {(day + 1) % 7 for day in pack.days} <= set(range(first, last + 1)), pack.id  # cron counts from Sunday
