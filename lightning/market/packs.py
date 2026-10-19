"""Price packs: the market file is published as one folder per pack (Egyptian stocks, Gulf stocks, ...),
each with its own sources, schedule and manifest, so you download only the exchanges you follow and each
pack is refreshed when its own market closes. issues/6-market-data/6A-price-packs.md › Packs.

Published layout (the open data repository, `market/`):

    index.json           schema, created_at, and for every pack its name, venues, date and download size
    <pack>/manifest.json one market file per pack (bundle.py), its manifest naming the pack
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .bundle import MAX_UNPACKED, SCHEMA, Close, Instrument, MarketFile, MarketFileError

INDEX = "index.json"
PACK_ID = re.compile(r"[a-z][a-z0-9-]{1,23}")  # also a folder name, so never a path
DAILY_MONTHS = 13  # what an app keeps of the daily files; older days are in the month-end files


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    covers: str
    venues: tuple[str, ...]      # ISO 10383 MICs; none for funds, currencies and gold
    days: frozenset[int]         # trading days as Python weekdays (Monday 0, Sunday 6)
    final_utc: str               # when the day's prices are final; the collector runs after it
    default: bool = False
    source: str = ""             # who the prices come from, cited wherever they are published or shown
    publish: bool = False        # owner decision 2026-10-05: only sources that allow republishing are published


def publishable(pack_ids) -> list[str]:
    """The packs whose sources allow us to republish them (proposal › Rights and limits)."""
    return [p for p in pack_ids if p in PACKS and PACKS[p].publish]


_SUN_THU, _MON_FRI = frozenset({6, 0, 1, 2, 3}), frozenset({0, 1, 2, 3, 4})
PACKS: dict[str, Pack] = {p.id: p for p in (
    Pack("egx", "Egyptian stocks", "Every stock listed on EGX, and the EGX indices", ("XCAI",), _SUN_THU, "13:30", True,
         "TradingView, Yahoo Finance"),
    Pack("eg-funds", "Egyptian funds", "Egyptian mutual funds' prices (NAV), with their fund class", (), _SUN_THU, "19:00", True,
         "Mubasher"),
    Pack("fx", "Exchange rates", "Banque Misr's transfer-rate midpoints, in pounds", (), _SUN_THU, "13:30", True,
         "Banque Misr (banquemisr.com; transfer buy/sell midpoint)", publish=True),
    Pack("us", "US stocks and ETFs", "The 600 largest US stocks and 100 largest ETFs on Nasdaq, NYSE and NYSE Arca",
         ("XNAS", "XNYS", "ARCX", "XASE"), _MON_FRI, "22:30", source="TradingView, Yahoo Finance"),
    Pack("gcc", "Gulf stocks", "Every stock on the Saudi Exchange, Dubai, Abu Dhabi, Qatar, Boursa Kuwait, Bahrain and Oman",
         ("XSAU", "XDFM", "XADS", "DSMQ", "XKUW", "XBAH", "XMUS"), _SUN_THU | {4}, "13:30", source="TradingView"),
    Pack("europe", "European stocks and ETFs", "The largest stocks and UCITS ETFs in London, Xetra, Euronext, Madrid, "
         "Milan, Zurich and Nasdaq Nordic", ("XLON", "XETR", "XPAR", "XAMS", "XBRU", "XLIS", "XMAD", "XMIL", "XSWX",
                                              "XSTO", "XCSE", "XHEL", "XICE"), _MON_FRI, "17:30", source="TradingView"),
)}


def chosen(setting: str | None) -> list[str]:
    """The packs a profile follows: its saved list ("none" for none), or the default packs before it saves one."""
    if (setting or "").strip() == "none":
        return []
    ids = [p.strip() for p in (setting or "").split(",") if p.strip()]
    return [p for p in ids if PACK_ID.fullmatch(p)] if ids else [p.id for p in PACKS.values() if p.default]


def download_bytes(manifest: dict, daily_months: int = DAILY_MONTHS) -> int:
    """What an app downloads for a pack: every file but the daily ones older than `daily_months`."""
    files = manifest.get("files", {})
    daily = sorted(name for name in files if name.startswith("daily/"))
    return sum(int(e.get("bytes", 0)) for n, e in files.items() if not n.startswith("daily/") or n in daily[-daily_months:])


def write_index(root: Path, created_at: str) -> dict:
    """Describe every pack folder under `root` in index.json, so an app can list and size them before
    downloading. A pack the app does not know yet still shows, by the name given here."""
    root, packs = Path(root), {}
    for manifest_path in sorted(root.glob("*/manifest.json")):
        pack_id = manifest_path.parent.name
        if not PACK_ID.fullmatch(pack_id):
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        known = PACKS.get(pack_id)
        files = manifest.get("files", {})
        if not files.get("instruments.csv", {}).get("rows"):
            continue  # no prices yet (its source has not answered): its health is kept, but no app is offered it
        packs[pack_id] = {
            "name": known.name if known else pack_id, "covers": known.covers if known else "",
            "source": known.source if known else str(manifest.get("source", "")),
            "venues": list(known.venues) if known else [], "created_at": manifest.get("created_at", ""),
            "last_date": max((e.get("last_date", "") for e in files.values()), default=""),
            "instruments": files.get("instruments.csv", {}).get("rows", 0), "bytes": download_bytes(manifest)}
    index = {"schema": SCHEMA, "created_at": created_at, "packs": packs}
    (root / INDEX).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def pack_release(root: Path, zip_path: Path, pack_ids, daily_months: int = DAILY_MONTHS) -> Path:
    """Zip packs for a release, one folder each, every pack trimmed to its last `daily_months` daily files
    (its month-end files keep the whole history)."""
    root, zip_path = Path(root), Path(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for pack_id in pack_ids:
            folder = root / pack_id
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            daily = sorted(name for name in manifest["files"] if name.startswith("daily/"))
            keep = {n: e for n, e in manifest["files"].items() if not n.startswith("daily/") or n in daily[-daily_months:]}
            for name in sorted(keep):
                archive.write(folder / name, f"{pack_id}/{name}")
            archive.writestr(f"{pack_id}/manifest.json", json.dumps(dict(manifest, files=keep), indent=2, sort_keys=True) + "\n")
    return zip_path


def read_zip(data: bytes) -> dict[str, MarketFile]:
    """A market.zip as its packs: either one pack (manifest.json at the top, naming its pack) or several
    (one folder per pack, as a release ships them). Every file is checked before anything is used."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED:
                raise MarketFileError("This file is far larger than a Lightning market file.")
            raw = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketFileError(f"This is not a Lightning market file ({exc.__class__.__name__}).") from None
    if "manifest.json" in raw:
        market = MarketFile.from_files(raw)
        pack_id = str(market.manifest.get("pack", ""))
        if not PACK_ID.fullmatch(pack_id):
            raise MarketFileError("This market file does not say which pack it is.")
        return {pack_id: market}
    groups: dict[str, dict[str, bytes]] = {}
    for name, content in raw.items():
        pack_id, _, rest = name.partition("/")
        if rest and PACK_ID.fullmatch(pack_id):
            groups.setdefault(pack_id, {})[rest] = content
    markets = {p: MarketFile.from_files(files) for p, files in groups.items() if "manifest.json" in files}
    if not markets:
        raise MarketFileError("This is not a Lightning market file (no pack in it).")
    return markets


class MarketSet:
    """Several packs read as one: instruments from all of them, each key's prices from the pack that has it."""

    def __init__(self, packs: dict[str, MarketFile]):
        self.packs = packs
        self.created_at = max((m.created_at for m in packs.values()), default="")
        self._owner: dict[str, MarketFile] = {}
        self._instruments: dict[str, Instrument] = {}
        for market in packs.values():
            for key, instrument in market.instruments().items():
                self._owner.setdefault(key, market)
                self._instruments.setdefault(key, instrument)

    def instruments(self) -> dict[str, Instrument]:
        return self._instruments

    def close_on(self, key: str, day: str) -> Close | None:
        market = self._owner.get(key)
        return market.close_on(key, day) if market else None

    def latest(self, key: str) -> Close | None:
        market = self._owner.get(key)
        return market.latest(key) if market else None
