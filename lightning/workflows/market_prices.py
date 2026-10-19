"""Fill a profile's investment prices from the price packs it follows (issues/6-market-data/6A-price-packs.md).

Each pack comes with the app (lightning/market/market.zip, the default packs) or is downloaded or imported
into the profile's market folder, one folder per pack; for each pack the newer one is used. Each holding is
matched to an instrument (ISIN, then its saved key, then an alias such as STK:COMI, then country and
ticker), and gets the close for every month-end it was held plus its latest close. Prices are saved with
source MARKET, so a price you typed on the same day still wins, and an instrument priced in another
currency is left for you (no silent conversion). What the packs lack is listed, never guessed."""
from __future__ import annotations

import calendar
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from lightning.core.dates import fmt_date
from lightning.fx import save_rate
from lightning.market.bundle import MarketFile, MarketFileError
from lightning.market.iso import venue_name
from lightning.market.packs import INDEX, PACK_ID, PACKS, MarketSet, chosen, read_zip

SOURCE = "MARKET"
BUNDLED = Path(__file__).resolve().parents[1] / "market" / "market.zip"
_bundled_cache: dict[tuple, dict[str, MarketFile]] = {}


@dataclass
class FillReport:
    file_date: str
    matched: list[str] = field(default_factory=list)
    added: int = 0
    missing: list[tuple[str, str]] = field(default_factory=list)     # (investment, month-end)
    missing_ids: list[tuple[int, str]] = field(default_factory=list)  # (asset id, month-end), for Needs you
    unmatched: list[str] = field(default_factory=list)
    other_currency: list[str] = field(default_factory=list)
    rates: int = 0                                                    # exchange rates filled from the fx file

    def summary(self) -> str:
        parts = [f"Filled {self.added} price{'s' if self.added != 1 else ''} for {len(self.matched)} "
                 f"investment{'s' if len(self.matched) != 1 else ''} from the price files of {self.file_date[:10]}."]
        if self.rates:
            parts.append(f"{self.rates} exchange rate{'s' if self.rates != 1 else ''} filled.")
        if self.missing:
            shown = ", ".join(f"{name} {day}" for name, day in self.missing[:3])
            parts.append(f"{len(self.missing)} still missing: {shown}{' and more' if len(self.missing) > 3 else ''}.")
        if self.unmatched:
            parts.append(f"Not in the packs you follow: {', '.join(self.unmatched[:3])}"
                         f"{' and more' if len(self.unmatched) > 3 else ''}.")
        if self.other_currency:
            parts.append(f"Priced in another currency, left for you: {', '.join(self.other_currency[:3])}.")
        return " ".join(parts)


def local_folder(data_dir: Path | None) -> Path | None:
    return Path(data_dir) / "market" if data_dir else None


def _bundled() -> dict[str, MarketFile]:
    """The packs that came with the app, read and checked once per file version."""
    try:
        stat = BUNDLED.stat()
    except OSError:
        return {}
    key = (str(BUNDLED), stat.st_mtime_ns, stat.st_size)
    if key not in _bundled_cache:
        try:
            _bundled_cache.clear()
            _bundled_cache[key] = read_zip(BUNDLED.read_bytes())
        except (OSError, MarketFileError):
            return {}
    return _bundled_cache[key]


def current_set(data_dir: Path | None, pack_ids) -> MarketSet | None:
    """The followed packs, each the newer of its downloaded or imported folder and the one the app came with."""
    root, bundled, found = local_folder(data_dir), _bundled(), {}
    for pack_id in pack_ids:
        options = [bundled[pack_id]] if pack_id in bundled else []
        if root and PACK_ID.fullmatch(pack_id) and (root / pack_id / "manifest.json").exists():
            try:
                options.append(MarketFile.open(root / pack_id))
            except MarketFileError:
                pass  # damaged or half-updated: the app's own copy, if any, is used meanwhile
        if options:
            found[pack_id] = max(options, key=lambda m: m.created_at)
    return MarketSet(found) if found else None


def _manifest_facts(manifest: dict, origin: str) -> dict:
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    return {"created_at": str(manifest.get("created_at", ""))[:10], "origin": origin,
            "last_date": max((str(e.get("last_date", "")) for e in files.values() if isinstance(e, dict)), default=""),
            "instruments": files.get("instruments.csv", {}).get("rows", 0)}


def pack_files(data_dir: Path | None) -> dict[str, dict]:
    """What each pack on this computer holds, read from manifests alone (no checks, so pages stay fast;
    filling checks every file): the newer of the downloaded and the app's own copy."""
    root, found = local_folder(data_dir), {}
    try:
        if BUNDLED.exists():
            with zipfile.ZipFile(BUNDLED) as archive:
                for name in archive.namelist():
                    pack_id, _, rest = name.partition("/")
                    if rest == "manifest.json" and PACK_ID.fullmatch(pack_id):
                        found[pack_id] = _manifest_facts(json.loads(archive.read(name)), "came with Lightning")
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    for path in sorted(root.glob("*/manifest.json")) if root and root.is_dir() else []:
        if not PACK_ID.fullmatch(path.parent.name):
            continue
        try:
            facts = _manifest_facts(json.loads(path.read_text(encoding="utf-8")), "downloaded")
        except (OSError, ValueError):
            continue
        if facts["created_at"] >= found.get(path.parent.name, {}).get("created_at", ""):
            found[path.parent.name] = facts
    return found


def pack_rows(data_dir: Path | None, followed, held=()) -> list[dict]:
    """Every pack Lightning knows or the last download listed, for the Price files page."""
    root = local_folder(data_dir)
    try:
        published = json.loads((root / INDEX).read_text(encoding="utf-8")).get("packs", {}) if root else {}
    except (OSError, ValueError, AttributeError):
        published = {}
    have = pack_files(data_dir)
    rows = []
    for pack_id in [*PACKS, *sorted(p for p in published if p not in PACKS and PACK_ID.fullmatch(str(p)))]:
        known, listed = PACKS.get(pack_id), published.get(pack_id, {}) if isinstance(published.get(pack_id), dict) else {}
        venues = known.venues if known else tuple(listed.get("venues", ()))
        rows.append({"id": pack_id, "name": known.name if known else str(listed.get("name", pack_id)),
                     "covers": known.covers if known else str(listed.get("covers", "")),
                     "source": known.source if known else str(listed.get("source", "")),
                     "venues": ", ".join(venue_name(v) for v in venues), "on": pack_id in followed,
                     "held": pack_id in held,
                     "bytes": listed.get("bytes"), "have": have.get(pack_id)})
    return rows


def forget(data_dir: Path | None, pack_ids) -> None:
    """Remove the downloaded copies of packs no longer followed."""
    root = local_folder(data_dir)
    for pack_id in pack_ids:
        if root and PACK_ID.fullmatch(pack_id) and (root / pack_id).is_dir():
            shutil.rmtree(root / pack_id)


def _month_ends(first: date, last: date) -> list[str]:
    days, year, month = [], first.year, first.month
    while (year, month) <= (last.year, last.month):
        end = date(year, month, calendar.monthrange(year, month)[1])
        if end <= last:
            days.append(fmt_date(end))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return days


class MarketPrices:
    def __init__(self, assets, reporting):
        self.assets, self.reporting = assets, reporting

    def match(self, asset, market: MarketSet) -> str | None:
        instruments = market.instruments()
        if asset.isin:
            for key, instrument in instruments.items():
                if instrument.isin == asset.isin:
                    return key
        if asset.market_key in instruments:
            return asset.market_key
        for key, instrument in instruments.items():
            if asset.code in instrument.aliases:
                return key
        if asset.country and asset.mic:
            key = f"{asset.country}:{asset.ticker}"
            if key in instruments:
                return key
        return None

    def fill_rates(self, market: MarketSet, today: date) -> int:
        """Exchange rates from the followed fx file (source MARKET) for every pair between the profile currency
        and the registered ones: each month-end, each day money moved in a foreign currency, and the latest."""
        db, base = self.reporting.q.db, self.reporting.base_currency
        codes = {row["code"] for row in db.all("SELECT code FROM registered_currencies")} | {base}
        pairs = [(key, key[:3], key[4:]) for key, item in market.instruments().items()
                 if item.category == "CURRENCY" and len(key) == 7 and key[3] == "/" and key[:3] in codes
                 and key[4:] in codes]
        if not pairs:
            return 0
        active = sorted(row["date"] for row in db.all(
            "SELECT DISTINCT le.date FROM ledger_entries le JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE a.currency<>? AND le.date<=?", (base, fmt_date(today))))
        days = set(active)
        if active:
            days |= set(_month_ends(date.fromisoformat(active[0][:10]), today))
        saved = 0
        with db.transaction():
            for key, left, right in pairs:
                found = {}
                for day in sorted(days):
                    close = market.close_on(key, day)
                    if close:
                        found[close.date] = close.close
                latest = market.latest(key)
                if latest and (today - date.fromisoformat(latest.date)).days <= 10:
                    found[latest.date] = latest.close
                for day, close in found.items():
                    save_rate(db, day, left, right, close, "MARKET")
                    saved += 1
        return saved

    def fill(self, market: MarketSet, today: date) -> FillReport:
        report = FillReport(market.created_at)
        report.rates = self.fill_rates(market, today)
        first = self.reporting.first_activity_date()
        held: dict[int, list[str]] = {}
        if first:
            for day in _month_ends(date.fromisoformat(first[:10]), today):
                for holding in self.reporting.holdings(day)[0]:
                    if holding.quantity and holding.asset_id:
                        held.setdefault(holding.asset_id, []).append(day)
        for holding in self.reporting.holdings(fmt_date(today))[0]:
            if holding.quantity and holding.asset_id:
                held.setdefault(holding.asset_id, [])
        instruments = market.instruments()
        for asset_id, month_ends in sorted(held.items()):
            asset = self.assets.get_asset(asset_id)
            if asset.is_cash or asset.code.startswith(("OTH:ITEM-", "REF:")):
                continue
            key = self.match(asset, market)
            if key is None:
                report.unmatched.append(asset.name)
                continue
            if instruments[key].currency != asset.currency:
                report.other_currency.append(asset.name)
                continue
            self.assets.link_market(asset.id, key)
            report.matched.append(asset.name)
            found = {}
            for day in month_ends:
                close = market.close_on(key, day)
                if close is None:
                    if not self.assets.priced_on(asset.id, day):  # a typed price already covers it
                        report.missing.append((asset.name, day))
                        report.missing_ids.append((asset.id, day))
                else:
                    found[close.date] = close
            latest = market.latest(key)
            if latest and (today - date.fromisoformat(latest.date)).days <= 10:
                found[latest.date] = latest
            for close in found.values():  # one price per day, even when a month-end is also the latest close
                self.assets.set_price(asset.id, close.date, close.close, source=SOURCE)
            report.added += len(found)
        return report


# ------------------------------------------------------------------ filling without being asked
# Proposal › How the app gets prices: on first run, after a statement import and every month-end, the app
# fills the held instruments' prices from the files it already has. Nothing is downloaded here.
FILLED_SETTING = "market_filled"     # "<file date>|<month>" of the last automatic fill
MISSING_SETTING = "market_missing"   # what that fill could not find, for Needs you


def held_packs(c) -> list[str]:
    """The packs a profile needs for what it holds now (audit 2026-10-15): the market of every held listing,
    Egyptian funds for a held Egyptian fund, and exchange rates once anything is in another currency."""
    rows = c.db.all(
        "SELECT fa.mic, fa.country, fa.currency, ac.code AS class_code FROM ledger_entries le "
        "JOIN transactions t ON t.id = le.transaction_id AND t.status != 'VOID' "
        "JOIN financial_assets fa ON fa.id = le.asset_id JOIN asset_classes ac ON ac.id = fa.asset_class_id "
        "WHERE fa.is_cash = 0 GROUP BY le.account_id, le.asset_id HAVING SUM(le.quantity_e6) > 0")
    needed = set()
    for row in rows:
        mic = (row["mic"] or "").upper()
        needed.update(p.id for p in PACKS.values() if mic and mic in p.venues)
        if not mic and (row["class_code"] or "").startswith("FUND") and row["country"] == "EG":
            needed.add("eg-funds")
        if row["currency"] and row["currency"] != c.base_currency:
            needed.add("fx")
    foreign_cash = c.db.scalar("SELECT 1 FROM accounts WHERE active = 1 AND currency != ? LIMIT 1", (c.base_currency,))
    if foreign_cash:
        needed.add("fx")
    return [p for p in PACKS if p in needed]


def followed_packs(c) -> list[str]:
    """What the person chose to follow, plus every market they hold something on (never dropped by unticking)."""
    chosen_ids = chosen(c.settings.get("market_packs"))
    return chosen_ids + [p for p in held_packs(c) if p not in chosen_ids]


def fill_followed(c, on: date) -> FillReport | None:
    """Fill from the followed packs now, post the month-end returns this allows, and remember what is
    missing. None when there are no price files or the profile is a read-only copy."""
    if c.db.read_only:
        return None
    market = current_set(c.data_dir, followed_packs(c))
    if market is None:
        return None
    report = MarketPrices(c.assets, c.reporting).fill(market, on)
    c.reevaluations.process_due()
    c.settings.set(MISSING_SETTING, json.dumps([[asset_id, day] for asset_id, day in report.missing_ids[:200]]))
    c.settings.set(FILLED_SETTING, f"{market.created_at[:10]}|{on.isoformat()[:7]}")
    return report


def fill_if_due(c, on: date) -> FillReport | None:
    """The automatic fill: on first run, when a newer file arrived, or in a new month. Quiet otherwise."""
    if c.db.read_only:
        return None
    market = current_set(c.data_dir, followed_packs(c))
    if market is None or c.settings.get(FILLED_SETTING) == f"{market.created_at[:10]}|{on.isoformat()[:7]}":
        return None
    return fill_followed(c, on)


def missing_prices(c) -> list[tuple[str, str]]:
    """(investment, month-end) pairs the last fill could not find and nobody has typed since."""
    try:
        pairs = json.loads(c.settings.get(MISSING_SETTING) or "[]")
    except ValueError:
        return []
    found = []
    for asset_id, day in pairs if isinstance(pairs, list) else []:
        try:
            if not c.assets.priced_on(int(asset_id), str(day)):
                found.append((c.assets.get_asset(int(asset_id)).name, str(day)))
        except Exception:  # a removed asset or a damaged entry is simply not listed
            continue
    return found
