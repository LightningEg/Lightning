"""The market file: every instrument with its category and ISO names, and its closing prices.

A folder (or the same folder zipped) holding:

    manifest.json        schema, created_at, and for every file its sha256, rows, first and last date
    instruments.csv      key,isin,mic,ticker,name,name_ar,category,country,currency,unit,aliases,sources,status,first_date,last_date
    monthly/YYYY.csv     date,key,close: the last close of each month, per instrument
    daily/YYYY-MM.csv    date,key,close: every daily close

The collector writes it (tools/market); the app only reads it. Reading checks every file against the
manifest, so a damaged or tampered file is refused rather than half-read. issues/6-market-data/6A-price-packs.md.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lightning.core.errors import ValidationError

from .iso import is_country, is_currency, is_isin, is_mic

SCHEMA = 1
INSTRUMENT_FIELDS = ("key", "isin", "mic", "ticker", "name", "name_ar", "category", "country", "currency", "unit",
                     "aliases", "sources", "status", "first_date", "last_date")
PRICE_FIELDS = ("date", "key", "close")
CATEGORIES = ("STOCK", "FUND.EQUITY", "FUND.FIXED_INCOME", "FUND.MONEY_MARKET", "FUND.GOLD", "FUND.OTHER",
              "CURRENCY", "GOLD", "INDEX")
STATUSES = ("active", "inactive", "delisted")
# Keys never change once published (proposal › The market file).
_KEY = re.compile(r"[A-Z]{2}:FUND:[A-Za-z0-9-]+"       # EG:FUND:4104
                  r"|[A-Z]{2}:[A-Z0-9][A-Z0-9._\-]*"    # EG:COMI, US:BRK.B, SE:ERIC_B, EG:EGX30
                  r"|[A-Z]{3}/[A-Z]{3}"                  # USD/EGP: the price of one US dollar in pounds
                  r"|XAU:(?:24|22|21|18|14|12)K")        # XAU:21K: pounds per gram of 21K gold
MAX_GAP_DAYS = 10  # a close older than this before the asked day is not used for it
# The only files a market file may hold, so a manifest can never name a path outside its folder.
FILE_NAME = re.compile(r"instruments\.csv|health\.json|daily/\d{4}-\d{2}\.csv|monthly/\d{4}\.csv")
MAX_UNPACKED = 200_000_000  # bytes; the whole history is about 15 MB unpacked


class MarketFileError(ValidationError):
    """The market file is damaged, from a newer Lightning, or not a market file."""


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    category: str
    currency: str
    isin: str = ""
    mic: str = ""
    ticker: str = ""
    name_ar: str = ""
    country: str = ""
    unit: str = "unit"
    aliases: tuple[str, ...] = ()
    sources: dict[str, str] = field(default_factory=dict)
    status: str = "active"
    first_date: str = ""
    last_date: str = ""

    def check(self) -> None:
        """Refuse a row whose names are not the ISO forms the file promises."""
        problems = []
        if not _KEY.fullmatch(self.key):
            problems.append(f"key {self.key!r} is not one of the published forms")
        if self.category not in CATEGORIES:
            problems.append(f"category {self.category!r}")
        if not is_currency(self.currency):
            problems.append(f"currency {self.currency!r} is not ISO 4217")
        if self.isin and not is_isin(self.isin):
            problems.append(f"ISIN {self.isin!r} fails its ISO 6166 check")
        if self.mic and not is_mic(self.mic):
            problems.append(f"MIC {self.mic!r} is not ISO 10383")
        if self.country and not is_country(self.country):
            problems.append(f"country {self.country!r} is not ISO 3166")
        if self.status not in STATUSES:
            problems.append(f"status {self.status!r}")
        if not self.name.strip():
            problems.append("no name")
        if problems:
            raise MarketFileError(f"{self.key}: " + "; ".join(problems))

    def row(self) -> dict[str, str]:
        return {"key": self.key, "isin": self.isin, "mic": self.mic, "ticker": self.ticker, "name": self.name,
                "name_ar": self.name_ar, "category": self.category, "country": self.country,
                "currency": self.currency, "unit": self.unit, "aliases": "|".join(self.aliases),
                "sources": "|".join(f"{k}={v}" for k, v in sorted(self.sources.items())),
                "status": self.status, "first_date": self.first_date, "last_date": self.last_date}

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Instrument:
        sources = dict(part.split("=", 1) for part in (row.get("sources") or "").split("|") if "=" in part)
        return cls(key=row["key"], name=row["name"], category=row["category"], currency=row["currency"],
                   isin=row.get("isin", ""), mic=row.get("mic", ""), ticker=row.get("ticker", ""),
                   name_ar=row.get("name_ar", ""), country=row.get("country", ""), unit=row.get("unit") or "unit",
                   aliases=tuple(a for a in (row.get("aliases") or "").split("|") if a), sources=sources,
                   status=row.get("status") or "active", first_date=row.get("first_date", ""),
                   last_date=row.get("last_date", ""))


@dataclass(frozen=True)
class Close:
    date: str
    key: str
    close: Decimal


def price_text(value: Decimal) -> str:
    """A close as written: at most six decimals, no trailing zeros, never exponent form."""
    text = format(value.quantize(Decimal("0.000001")).normalize(), "f")
    return text


def _csv(rows: list[dict], fields: tuple[str, ...]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _month_end_closes(closes: list[Close]) -> list[Close]:
    """The last close of each month, per instrument."""
    last: dict[tuple[str, str], Close] = {}
    for close in closes:
        slot = (close.key, close.date[:7])
        if slot not in last or close.date > last[slot].date:
            last[slot] = close
    return sorted(last.values(), key=lambda c: (c.date[:4], c.key, c.date))


def write(folder: Path, instruments: list[Instrument], closes: list[Close], created_at: str,
          health: dict | None = None, pack: str = "", source: str = "") -> dict:
    """Write a whole market folder from instruments and every daily close, and return its manifest.

    Monthly files are derived from the daily closes, so the two can never disagree."""
    folder = Path(folder)
    for instrument in instruments:
        instrument.check()
    keys = {i.key for i in instruments}
    if len(keys) != len(instruments):
        raise MarketFileError("Two instruments share a key.")
    unknown = sorted({c.key for c in closes} - keys)
    if unknown:
        raise MarketFileError(f"Closes for instruments the file does not list: {', '.join(unknown[:5])}")
    if any(c.close <= 0 for c in closes):
        raise MarketFileError("A close is zero or negative.")
    files: dict[str, bytes] = {"instruments.csv": _csv(
        [i.row() for i in sorted(instruments, key=lambda i: i.key)], INSTRUMENT_FIELDS)}
    by_month: dict[str, list[Close]] = {}
    for close in sorted(closes, key=lambda c: (c.date, c.key)):
        by_month.setdefault(close.date[:7], []).append(close)
    for month, rows in by_month.items():
        files[f"daily/{month}.csv"] = _csv([{"date": c.date, "key": c.key, "close": price_text(c.close)}
                                            for c in sorted(rows, key=lambda c: (c.key, c.date))], PRICE_FIELDS)
    by_year: dict[str, list[Close]] = {}
    for close in _month_end_closes(closes):
        by_year.setdefault(close.date[:4], []).append(close)
    for year, rows in by_year.items():
        files[f"monthly/{year}.csv"] = _csv([{"date": c.date, "key": c.key, "close": price_text(c.close)}
                                             for c in rows], PRICE_FIELDS)
    if health is not None:
        files["health.json"] = json.dumps(health, indent=2, sort_keys=True).encode("utf-8")
    manifest = ({"schema": SCHEMA, "created_at": created_at, "files": {}} | ({"pack": pack} if pack else {})
                | ({"source": source} if source else {}))  # the citation travels with the prices
    for name, data in sorted(files.items()):
        entry = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if name.endswith(".csv") and name != "instruments.csv":
            dates = [line.split(",", 1)[0] for line in data.decode("utf-8").splitlines()[1:]]
            entry |= {"rows": len(dates), "first_date": min(dates), "last_date": max(dates)}
        elif name == "instruments.csv":
            entry["rows"] = len(instruments)
        manifest["files"][name] = entry
    # Only changed files are rewritten; partitions that no longer exist are removed (install).
    install(folder, {name: data for name, data in files.items()
                     if not (folder / name).exists() or (folder / name).read_bytes() != data}, manifest)
    return manifest


def pack(folder: Path, zip_path: Path, daily_months: int = 13) -> Path:
    """Zip a market folder for shipping: every monthly file, the last `daily_months` daily files, and a
    manifest that lists exactly what is inside."""
    folder, zip_path = Path(folder), Path(zip_path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    daily = sorted(name for name in manifest["files"] if name.startswith("daily/"))
    keep = {name for name in manifest["files"] if not name.startswith("daily/")} | set(daily[-daily_months:])
    packed = dict(manifest, files={name: entry for name, entry in manifest["files"].items() if name in keep})
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(keep):
            archive.write(folder / name, name)
        archive.writestr("manifest.json", json.dumps(packed, indent=2, sort_keys=True) + "\n")
    return zip_path


def install(folder: Path, changed: dict[str, bytes], manifest: dict) -> None:
    """Write already-checked files into a market folder: each through a .part file, then the files the
    manifest no longer lists are removed and the manifest is written last, so a folder interrupted
    half-way still fails its checks instead of mixing two versions unnoticed."""
    folder = Path(folder)
    for name in changed:
        if not FILE_NAME.fullmatch(name):
            raise MarketFileError(f"The market file lists a file it may not hold ({name[:40]}).")
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(changed.items()):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        part.write_bytes(data)
        part.replace(target)
    listed = set(manifest.get("files", {}))
    for old in [*folder.glob("*.csv"), *folder.glob("*.json"), *folder.glob("daily/*.csv"), *folder.glob("monthly/*.csv")]:
        name = old.relative_to(folder).as_posix()
        if name != "manifest.json" and name not in listed:
            old.unlink()
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class MarketFile:
    """Read a market folder or zip. Every file is checked against the manifest before it is used."""

    def __init__(self, files: dict[str, bytes], manifest: dict):
        self.manifest = manifest
        self.created_at: str = manifest.get("created_at", "")
        self._files = files
        self._instruments: dict[str, Instrument] | None = None
        self._series: dict[str, tuple[list[str], list[Decimal]]] | None = None

    @classmethod
    def open(cls, path: Path) -> MarketFile:
        path = Path(path)
        if not path.is_dir():
            try:
                return cls.from_zip(path.read_bytes())
            except OSError as exc:
                raise MarketFileError(f"This is not a Lightning market file ({exc.__class__.__name__}).") from None
        try:
            raw = {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*")
                   if p.is_file() and not p.name.endswith(".part")}
        except OSError as exc:
            raise MarketFileError(f"This is not a Lightning market file ({exc.__class__.__name__}).") from None
        return cls.from_files(raw)

    @classmethod
    def from_zip(cls, data: bytes) -> MarketFile:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED:
                    raise MarketFileError("This file is far larger than a Lightning market file.")
                raw = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise MarketFileError(f"This is not a Lightning market file ({exc.__class__.__name__}).") from None
        return cls.from_files(raw)

    @classmethod
    def from_files(cls, raw: dict[str, bytes]) -> MarketFile:
        """A market file from its files by name (manifest.json among them), each checked against the manifest."""
        raw = dict(raw)
        try:
            manifest = json.loads(raw.pop("manifest.json"))
        except (KeyError, ValueError) as exc:
            raise MarketFileError(f"This is not a Lightning market file ({exc.__class__.__name__}).") from None
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise MarketFileError("This market file is from a different version of Lightning.")
        files = {}
        for name, entry in manifest.get("files", {}).items():
            if not FILE_NAME.fullmatch(name):
                raise MarketFileError(f"The market file lists a file it may not hold ({name[:40]}).")
            data = raw.get(name)
            if data is None:
                raise MarketFileError(f"The market file is missing {name}.")
            if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                raise MarketFileError(f"{name} in the market file is damaged (its checksum does not match).")
            files[name] = data
        if "instruments.csv" not in files:
            raise MarketFileError("The market file has no instrument list.")
        return cls(files, manifest)

    def save(self, folder: Path) -> None:
        """Put this whole file into `folder` (an imported market.zip), replacing what was there."""
        install(folder, self._files, self.manifest)

    def _rows(self, name: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self._files[name].decode("utf-8"))))

    def instruments(self) -> dict[str, Instrument]:
        if self._instruments is None:
            self._instruments = {row["key"]: Instrument.from_row(row) for row in self._rows("instruments.csv")}
        return self._instruments

    def _load(self) -> dict[str, tuple[list[str], list[Decimal]]]:
        if self._series is None:
            points: dict[str, dict[str, Decimal]] = {}
            names = sorted(n for n in self._files if n.startswith(("monthly/", "daily/")))
            for name in names:  # daily after monthly: a day's close is the same either way
                for row in self._rows(name):
                    try:
                        points.setdefault(row["key"], {})[row["date"]] = Decimal(row["close"])
                    except (KeyError, InvalidOperation):
                        raise MarketFileError(f"{name} has a row that is not a date, key and price.") from None
            self._series = {key: (sorted(days), [days[d] for d in sorted(days)]) for key, days in points.items()}
        return self._series

    def daily_closes(self) -> list[Close]:
        """Every close in the daily files: what the collector merges into (monthly files derive from them)."""
        closes = []
        for name in sorted(n for n in self._files if n.startswith("daily/")):
            for row in self._rows(name):
                closes.append(Close(row["date"], row["key"], Decimal(row["close"])))
        return closes

    def last_date(self) -> str:
        """The newest close in the file."""
        return max((entry.get("last_date", "") for entry in self.manifest["files"].values()), default="")

    def close_on(self, key: str, day: str, max_gap_days: int = MAX_GAP_DAYS) -> Close | None:
        """The last close on or before `day`, if it is at most `max_gap_days` older; else None."""
        series = self._load().get(key)
        if not series:
            return None
        dates, closes = series
        at = bisect_right(dates, day) - 1
        if at < 0:
            return None
        found = dates[at]
        if date.fromisoformat(day) - date.fromisoformat(found) > timedelta(days=max_gap_days):
            return None
        return Close(found, key, closes[at])

    def latest(self, key: str) -> Close | None:
        series = self._load().get(key)
        return Close(series[0][-1], key, series[1][-1]) if series else None
