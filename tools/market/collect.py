"""One collector run: for each pack whose market traded today, ask its sources, check every answer, merge
into the pack's folder, report health; then describe every pack in index.json (lightning/market/packs.py).

A failing source never stops the others and never removes a price: its pack keeps its last good closes,
and its health.json counts failures in a row so the workflow can open an issue (proposal › Keeping it alive).
Published closes are never changed by a run; a different value for a published day is only reported."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from lightning.market.bundle import Close, Instrument, MarketFile, write
from lightning.market.packs import PACK_ID, PACKS, write_index

from . import checks
from lightning.market.model import Quote, SourceError, SourceResult
from lightning.market.sources import banque_misr, mubasher, tradingview, yahoo

INACTIVE_AFTER_DAYS = 30


def _load(folder: Path) -> tuple[dict[str, Instrument], dict[str, list[Close]], dict]:
    if not (folder / "manifest.json").exists():
        return {}, {}, {}
    market = MarketFile.open(folder)
    series: dict[str, list[Close]] = {}
    for close in market.daily_closes():
        series.setdefault(close.key, []).append(close)
    for closes in series.values():
        closes.sort(key=lambda c: c.date)
    health = json.loads((folder / "health.json").read_text(encoding="utf-8")) if (folder / "health.json").exists() else {}
    return dict(market.instruments()), series, health


def _sources(session, pack: str, today: str, instruments: dict[str, Instrument]):
    """(name, fetch) for one pack's sources, highest priority first."""
    classes = {int(i.sources["mubasher"]): i.category for i in instruments.values() if "mubasher" in i.sources}
    if pack == "eg-funds":
        return [("mubasher-funds", lambda: mubasher.fetch(session, classes))]
    if pack == "fx":
        return [("banque-misr", lambda: banque_misr.fetch(session, today))]
    if pack in tradingview.BOARDS:
        return [(f"tradingview-{pack}", lambda: tradingview.fetch(session, pack, today))]
    return []


def _settle_keys(result: SourceResult, instruments: dict[str, Instrument]) -> None:
    """Keys never change once published, so a listing whose key is already another venue's (one ticker on
    both Dubai and Abu Dhabi) is published as KEY-MIC. A source lists each instrument's quotes in the order
    of its instruments, so the n-th quote under a key belongs to the n-th instrument that had it."""
    taken = {k: i.mic for k, i in instruments.items() if i.mic}
    keys: dict[str, list[str]] = {}
    for n, instrument in enumerate(result.instruments):
        original = instrument.key
        owner = taken.get(original)
        if owner and instrument.mic and owner != instrument.mic:
            instrument = result.instruments[n] = replace(instrument, key=f"{original}-{instrument.mic}")
        taken.setdefault(instrument.key, instrument.mic)
        keys.setdefault(original, []).append(instrument.key)
    seen: dict[str, int] = {}
    for n, quote in enumerate(result.quotes):
        if len(set(keys.get(quote.key, ()))) > 1 or keys.get(quote.key, [quote.key])[0] != quote.key:
            index = seen[quote.key] = seen.get(quote.key, -1) + 1
            result.quotes[n] = replace(quote, key=keys[quote.key][min(index, len(keys[quote.key]) - 1)])


def _merge_instrument(old: Instrument | None, new: Instrument) -> Instrument:
    """Keep the key, ISIN, aliases and a known category; take the source's fresh name and venue."""
    if old is None:
        return new
    return replace(old, name=new.name or old.name, mic=new.mic or old.mic, ticker=new.ticker or old.ticker,
                   currency=new.currency or old.currency, isin=old.isin or new.isin,
                   category=old.category if new.category == "FUND.OTHER" else new.category,
                   sources={**old.sources, **new.sources})


def _health_entry(previous: dict, name: str, ok: bool, created_at: str, **facts) -> dict:
    entry = dict(previous.get(name, {}))
    entry.update(facts, ok=ok, checked_at=created_at)
    if ok:
        entry.update(last_ok=created_at, failures_in_a_row=0, error="")
    else:
        entry["failures_in_a_row"] = int(entry.get("failures_in_a_row", 0)) + 1
    return entry


def _finish(folder, instruments, series, quotes, problems, health, today, created_at):
    """Append accepted quotes, keep published ones, refresh status and dates, write the folder."""
    categories = {k: i.category for k, i in instruments.items()}
    accepted, found = checks.accept(quotes, series, categories, today, history=False)
    return _write(folder, instruments, series, accepted, problems + found, health, today, created_at)


def _write(folder, instruments, series, accepted: list[Quote], problems, health, today, created_at):
    for quote in accepted:
        closes = series.setdefault(quote.key, [])
        same = next((c for c in closes if c.date == quote.date), None)
        if same is None:
            closes.append(Close(quote.date, quote.key, quote.close))
        elif same.close != quote.close:
            problems.append(f"{quote.source}: {quote.key} {quote.date} would change a published {same.close} "
                            f"to {quote.close}; kept (corrections go through corrections.csv)")
    cutoff = (date.fromisoformat(today) - timedelta(days=INACTIVE_AFTER_DAYS)).isoformat()
    for key, instrument in list(instruments.items()):
        closes = sorted(series.get(key, []), key=lambda c: c.date)
        series[key] = closes
        status = instrument.status if instrument.status == "delisted" else (
            "active" if closes and closes[-1].date >= cutoff else "inactive")
        instruments[key] = replace(instrument, status=status, first_date=closes[0].date if closes else "",
                                   last_date=closes[-1].date if closes else "")
    health["_run"] = {"created_at": created_at, "problems": problems[:200], "problem_count": len(problems)}
    write(folder, list(instruments.values()), [c for closes in series.values() for c in closes], created_at, health,
          pack=Path(folder).name, source=PACKS[Path(folder).name].source if Path(folder).name in PACKS else "")
    return health


def collect(root: Path, session, today: str, created_at: str, packs=tuple(PACKS)) -> dict:
    """Run the packs whose market traded today; return each pack's health (unchanged for a skipped pack)."""
    root, weekday, report = Path(root), date.fromisoformat(today).weekday(), {}
    for pack in packs:
        folder = root / pack
        if pack not in PACKS or not PACK_ID.fullmatch(pack):
            report[pack] = {"_run": {"problems": [f"{pack}: not a pack this collector knows"]}}
            continue
        if weekday not in PACKS[pack].days:
            report[pack] = _load(folder)[2]
            continue
        instruments, series, health = _load(folder)
        sources = _sources(session, pack, today, instruments)
        active = {name for name, _ in sources}
        # A changed provider must not keep the retired provider's failure as this run's result.
        health = {name: entry for name, entry in health.items() if name.startswith("_") or name in active}
        quotes, problems = [], []
        for name, fetch in sources:
            try:
                result: SourceResult = fetch()
                minimum = checks.MINIMUM_ROWS.get(name, 1)
                if len(result.quotes) < minimum:
                    raise SourceError(f"answered with {len(result.quotes)} prices, fewer than the {minimum} expected")
            except SourceError as exc:
                health[name] = _health_entry(health, name, False, created_at, error=str(exc), rows=0)
                continue
            _settle_keys(result, instruments)
            for instrument in result.instruments:
                instruments[instrument.key] = _merge_instrument(instruments.get(instrument.key), instrument)
            quotes += result.quotes
            health[name] = _health_entry(health, name, True, created_at, rows=len(result.quotes))
        report[pack] = _finish(folder, instruments, series, quotes, problems, health, today, created_at)
    write_index(root, created_at)
    return report


def backfill(root: Path, session, keys: list[str], today: str, created_at: str) -> dict:
    """Whole history for some instruments, in whichever pack lists them: Mubasher's CSV for funds, Yahoo's
    chart for the rest. Returns the health of each pack written."""
    root, report, left = Path(root), {}, list(keys)
    for folder in sorted(p.parent for p in root.glob("*/manifest.json")):
        instruments, series, health = _load(folder)
        mine = [k for k in left if k in instruments]
        if not mine:
            continue
        left = [k for k in left if k not in instruments]
        accepted, problems = [], []
        for key in mine:
            instrument = instruments[key]
            try:
                if "mubasher" in instrument.sources:
                    found = mubasher.fetch_history(session, key, instrument.sources["mubasher"])
                else:
                    found = yahoo.fetch_history(session, key, mic=instrument.mic)
            except SourceError as exc:
                problems.append(f"{key}: {exc}")
                continue
            quotes, issues = checks.accept(found, series, {key: instrument.category}, today, history=True)
            accepted += quotes
            problems += issues
        report[folder.name] = _write(folder, instruments, series, accepted, problems, health, today, created_at)
    if left:
        report["_run"] = {"problems": [f"{key}: not in the instrument list of any pack; run collect first" for key in left]}
    write_index(root, created_at)
    return report
