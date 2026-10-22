"""Ordinary profiles fetch their own prices from the sources. Experimental journal profiles fetch on the home
and receive exact journaled price rows (owner, 2026-10-05; issues/6-market-data/6A-price-packs.md
› How the app gets prices).

When: never daily by itself. Month-end closes matter most, because the monthly revaluation is posted from them,
so on opening a profile the app fetches only when a month-end has passed that a held investment has no price
for: open it three days after the month ends and it fetches that month-end's close. It tries at most once a
day by itself, so a source that is down never slows every start. Update prices fetches at any time: every
held investment's latest close and every month-end it lacks.

Funds: Mubasher names each fund by its own number (EG:FUND:4104). A held fund without one is matched by name
against the fund list the app downloads anyway (only an exact match, case, punctuation and the word "fund"
aside, and only when one fund has that name); the number is then kept. A fund whose name differs gets its
number from its Mubasher page, pasted on Edit investment.

Gold: an estimate from the world price, per gram of each purity: Yahoo's gold close in dollars an ounce
(GC=F) ÷ 31.1034768 grams × the dollar's rate in pounds (EGP=X) × karat ÷ 24. It prices the gold price
references your gold items use (18K, 21K, 24K) and gold held by the gram. Egyptian shops price above or below
the world price; a price you type (your shop's) wins for its day.

How: one request for a whole board's latest closes (EGX from TradingView, every Egyptian fund from Mubasher),
so asking reveals nothing about what you hold; a month-end close comes from the instrument's history (Yahoo
for stocks, Mubasher for funds). Only closes that are final are kept: during trading hours today's moving
price is skipped. Prices are saved with source ONLINE, so a price you type for the same day wins. What the
sources cannot give is listed for Needs you, never guessed. The shared price files (the daily collector's
backup) stay one click away on Investment prices, and typing a price always works.

The work is split so the network never holds the database: plan() reads, gather() only fetches, save() writes.
Opening a profile starts gather() on its own thread and the profile opens at once; the next page saves what it
found on the database's own thread (an encrypted profile is used from one thread only) and says so.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as clock, timedelta, timezone
from decimal import Decimal

from lightning.core.dates import fmt_date
from lightning.fx import rate_for, save_rate
from lightning.market.http import APP_AGENT, Polite
from lightning.market.model import Quote, SourceError
from lightning.market.packs import PACKS
from lightning.market.sources import banque_misr, mubasher, tradingview, yahoo
from lightning.workflows.market_prices import MISSING_SETTING, _month_ends

SOURCE = "ONLINE"
TRIED_SETTING = "prices_online_tried"   # the day the app last fetched by itself
OFFLINE_ENV = "LIGHTNING_PRICES_OFFLINE"  # "1": never fetch (tests, and anyone who wants no network)
FAILS_SETTING = "prices_online_fails"    # fetches in a row that left month-ends missing because a source failed
NEAR_DAYS = 10                           # a close this close to a month-end stands for it (as revaluation reads it)
CURRENCY = {"egx": "EGP", "eg-funds": "EGP", "us": "USD", "gold": "EGP"}
RATE_PIVOT = "EGP"                          # Yahoo quotes currencies against the pound here
OUNCE = Decimal("31.1034768")              # grams in a troy ounce


@dataclass
class Want:
    asset_id: int
    name: str
    key: str            # the instrument: EG:COMI, EG:FUND:4104, US:AAPL
    pack: str
    month_ends: list[str] = field(default_factory=list)  # held month-ends without a price
    purity: Decimal = Decimal(1)                          # gold: karat / 24


@dataclass
class RateWant:
    currency: str        # quoted against the pound: Yahoo's <CCY>EGP=X
    days: list[str] = field(default_factory=list)   # month-ends and activity days without a fresh rate


@dataclass
class Plan:
    on: str
    wants: list[Want] = field(default_factory=list)
    rates: list[RateWant] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)          # held, but no source can name it (type its price)
    other_currency: list[str] = field(default_factory=list)   # priced in another currency than the holding
    unlinked: list[Want] = field(default_factory=list)        # held funds without a Mubasher number yet
    linked: dict[int, str] = field(default_factory=dict)      # asset id -> the number its name matched

    def month_ends_missing(self) -> int:
        return sum(len(w.month_ends) for w in self.wants + self.unlinked) + sum(len(r.days) for r in self.rates)


@dataclass
class Report:
    saved: int = 0
    rates: int = 0                                           # exchange rates saved
    priced: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)         # sources that did not answer
    missing: list[tuple[str, str]] = field(default_factory=list)  # (investment, month-end) still without a price
    unknown: list[str] = field(default_factory=list)
    other_currency: list[str] = field(default_factory=list)
    gold: list[str] = field(default_factory=list)            # gold priced from the world price (an estimate)
    linked: list[str] = field(default_factory=list)          # funds found on Mubasher by their name
    unmatched: list[str] = field(default_factory=list)       # funds Mubasher has no such name for

    def summary(self) -> str:
        parts = [f"Fetched {self.saved} price{'s' if self.saved != 1 else ''} for {len(self.priced)} "
                 f"investment{'s' if len(self.priced) != 1 else ''}." if self.saved else "No new prices fetched."]
        if self.rates:
            parts.append(f"Fetched {self.rates} exchange rate{'s' if self.rates != 1 else ''}.")
        if self.failed:
            parts.append(f"Not reachable now: {', '.join(self.failed)}.")
        if self.missing:
            shown = ", ".join(f"{name} {day}" for name, day in self.missing[:3])
            parts.append(f"{len(self.missing)} month-end price{'s' if len(self.missing) != 1 else ''} still missing: "
                         f"{shown}{' and more' if len(self.missing) > 3 else ''}.")
        if self.gold:
            parts.append("Gold is an estimate from the world price and the dollar's rate; type your shop's price "
                         "to use it instead.")
        if self.linked:
            parts.append(f"Found on Mubasher by name: {', '.join(self.linked[:3])}{' and more' if len(self.linked) > 3 else ''}.")
        if self.unmatched:
            parts.append(f"No fund on Mubasher is named {', '.join(self.unmatched[:3])}"
                         f"{' and more' if len(self.unmatched) > 3 else ''}; paste its Mubasher page in Edit investment.")
        if self.unknown:
            parts.append(f"No online source for {', '.join(self.unknown[:3])}{' and more' if len(self.unknown) > 3 else ''}"
                         "; type their prices.")
        if self.other_currency:
            parts.append(f"Priced in another currency, left for you: {', '.join(self.other_currency[:3])}.")
        return " ".join(parts)


def enabled() -> bool:
    return os.environ.get(OFFLINE_ENV, "").strip() not in ("1", "true", "yes")


def instrument_key(asset) -> tuple[str, str] | None:
    """Which instrument and pack an investment is, when a source can name it: its saved market key, else a
    stock's country and ticker (EGX by default). Funds need their saved key (EG:FUND:<Mubasher id>)."""
    key = (asset.market_key or "").strip()
    if not key and asset.code.startswith("STK:"):
        key = f"{asset.country or 'EG'}:{asset.ticker}"
    if key.startswith("EG:FUND:"):
        return key, "eg-funds"
    if key.startswith("EG:"):
        return key, "egx"
    if key.startswith("US:"):
        return key, "us"
    return None


def fund_name(text: str) -> str:
    """A fund's name for matching: case, punctuation and the words every fund name shares set aside."""
    words = re.sub(r"[^\w]+", " ", (text or "").casefold().replace("&", " and ")).split()
    return " ".join(word for word in words if word not in {"fund", "funds", "the", "mutual"})


def link_funds(work: Plan, instruments) -> list[Want]:
    """Name each unlinked fund by the one Mubasher fund with the same name; the matched become wants."""
    by_name: dict[str, list[str]] = {}
    for instrument in instruments:
        by_name.setdefault(fund_name(instrument.name), []).append(instrument.key)
    matched = []
    for want in work.unlinked:
        keys = by_name.get(fund_name(want.name), [])
        if len(keys) == 1 and want.asset_id not in work.linked:
            want.key, work.linked[want.asset_id] = keys[0], keys[0]
            work.wants.append(want)
            matched.append(want)
    return matched


def final_day(pack: str, now: datetime) -> date:
    """The latest trading day whose close is final at `now` (UTC): today once the market's prices are final,
    else the trading day before. Holidays are not known here; a holiday's close is the day before's."""
    spec = PACKS[pack]
    hour, minute = (int(part) for part in spec.final_utc.split(":"))
    now = now.astimezone(timezone.utc)
    day = now.date() if now.time() >= clock(hour, minute) else now.date() - timedelta(days=1)
    while day.weekday() not in spec.days:
        day -= timedelta(days=1)
    return day


def due_month_ends(on: date, first: date, now: datetime) -> list[str]:
    """Month-ends from `first` whose closes are final by `now`: every one before `on`, and `on` itself once
    the day's prices are final (the evening of the last day of a month)."""
    days = _month_ends(first, on)
    hour, minute = (int(part) for part in PACKS["egx"].final_utc.split(":"))
    if days and days[-1] == fmt_date(on) and now.astimezone(timezone.utc).time() < clock(hour, minute):
        days.pop()
    return days


def plan(c, on: date, now: datetime | None = None) -> Plan:
    """What to fetch: every held investment a source can name, with the month-ends it lacks a price for."""
    now = now or datetime.now(timezone.utc)
    result = Plan(fmt_date(on))
    first = c.reporting.first_activity_date()
    held: dict[int, list[str]] = {}
    held_on: dict[int, list[str]] = {}  # every due month-end it was held on, priced or not (gold items)
    if first:
        for day in due_month_ends(on, date.fromisoformat(first[:10]), now):
            for holding in c.reporting.holdings(day)[0]:
                if holding.quantity and holding.asset_id:
                    held_on.setdefault(holding.asset_id, []).append(day)
                    if not c.reevaluations.has_price(holding.asset_id, day):
                        held.setdefault(holding.asset_id, []).append(day)
    for holding in c.reporting.holdings(fmt_date(on))[0]:
        if holding.quantity and holding.asset_id:
            held.setdefault(holding.asset_id, [])
    gold: dict[int, list[str]] = {}  # gold price references and gold held by the gram -> month-ends to price
    for asset_id, month_ends in sorted(held.items()):
        asset = c.assets.get_asset(asset_id)
        if asset.code.startswith("OTH:ITEM-"):
            item = c.reporting.q.physical_item(asset_id)
            if item and item.get("reference_asset_id"):
                ref = item["reference_asset_id"]
                gold.setdefault(ref, [])
                gold[ref] += [d for d in held_on.get(asset_id, [])
                              if d not in gold[ref] and not c.reevaluations.has_price(ref, d)]
            continue
        if asset.code.startswith("GLD:") and asset.purity:
            gold.setdefault(asset_id, []).extend(d for d in month_ends if d not in gold[asset_id])
            continue
        if asset.is_cash or asset.code.startswith(("REF:", "GLD:")):
            continue
        found = instrument_key(asset)
        if found is None and asset.code.startswith("FND:"):
            result.unlinked.append(Want(asset.id, asset.name, "", "eg-funds", month_ends))
            continue
        if found is None:
            if month_ends:
                result.unknown.append(asset.name)
            continue
        key, pack = found
        if pack != "eg-funds" and CURRENCY[pack] != asset.currency:
            result.other_currency.append(asset.name)
            continue
        result.wants.append(Want(asset.id, asset.name, key, pack, month_ends))
    for asset_id, month_ends in sorted(gold.items()):
        asset = c.assets.get_asset(asset_id)
        if asset.purity and asset.currency == CURRENCY["gold"]:
            result.wants.append(Want(asset.id, asset.name, "XAU/USD", "gold", sorted(month_ends), asset.purity))
    foreign = {a.currency for a in c.accounts.list() if a.currency != c.base_currency}
    first_foreign = c.db.scalar("SELECT MIN(le.date) FROM ledger_entries le JOIN financial_assets a "
                                "ON a.id=le.asset_id WHERE a.currency<>?", (c.base_currency,))
    if foreign and first_foreign:  # exchange rates: each foreign currency (and the profile's) against the pound
        days = due_month_ends(on, date.fromisoformat(first_foreign[:10]), now) + [fmt_date(on)]
        for code in sorted(({c.base_currency} | foreign) - {RATE_PIVOT}):
            lacking = [d for d in days if (r := rate_for(c.db, code, RATE_PIVOT, d)) is None or r.stale]
            if lacking:
                result.rates.append(RateWant(code, sorted(set(lacking))))
    return result


def per_gram(ounces: list[Quote], dollars: list[Quote]) -> list[Quote]:
    """Pure gold in pounds a gram, each day both series have: dollars an ounce ÷ grams an ounce × the dollar's
    rate on or before that day (rates are not published on every day gold trades)."""
    rates = sorted((q.date, q.close) for q in dollars)
    out = []
    for q in sorted(ounces, key=lambda q: q.date):
        prior = [(day, close) for day, close in rates if day <= q.date]
        if prior and (date.fromisoformat(q.date) - date.fromisoformat(prior[-1][0])).days <= 5:
            out.append(Quote("XAU", q.date, (q.close / OUNCE * prior[-1][1]).quantize(Decimal("0.000001")),
                             "yahoo-history"))
    return out


def _range(oldest: date, on: date) -> str:
    """The shortest Yahoo history range reaching back to `oldest` (with room for a month-end on a weekend)."""
    days = (on - oldest).days + NEAR_DAYS
    for limit, name in ((28, "1mo"), (88, "3mo"), (178, "6mo"), (360, "1y"), (725, "2y"), (1820, "5y"), (3640, "10y")):
        if days <= limit:
            return name
    return "max"


def gather(work: Plan, session=None, now: datetime | None = None, budget: float = 20.0) -> tuple[dict, list[str]]:
    """Fetch, touching no database: the closes found per asset id, and the sources that failed. Latest closes
    come from whole boards; history only for investments missing a month-end. Stops when `budget` runs out."""
    now = now or datetime.now(timezone.utc)
    session = session or Polite(min_interval=0.3, retries=2, timeout=10.0, user_agent=APP_AGENT)
    deadline = time.monotonic() + budget
    found: dict[int, dict[str, Decimal]] = {}
    failed: list[str] = []
    on = date.fromisoformat(work.on)

    def last_final(want: Want) -> date:  # a fund's NAV is published once, already final, on its own date
        if want.pack == "gold":  # gold trades round the clock: yesterday's close is the last final one
            return min(now.astimezone(timezone.utc).date() - timedelta(days=1), on)
        return on if want.pack == "eg-funds" else min(final_day(want.pack, now), on)

    def pick(want: Want, quotes, latest_known: bool) -> None:
        """The last close on or before each missing month-end (within NEAR_DAYS), and the latest if none yet."""
        picked: list[Quote] = []
        ordered = sorted((q for q in quotes if date.fromisoformat(q.date) <= last_final(want)), key=lambda q: q.date)
        for day in sorted(set(want.month_ends)):
            before = [q for q in ordered if q.date <= day]
            if before and (date.fromisoformat(day) - date.fromisoformat(before[-1].date)).days <= NEAR_DAYS:
                picked.append(before[-1])
        if ordered and not latest_known:
            picked.append(ordered[-1])
        keep(want, picked)

    def keep(want: Want, quotes) -> None:
        for quote in quotes:
            if date.fromisoformat(quote.date) <= last_final(want):
                found.setdefault(want.asset_id, {})[quote.date] = quote.close

    by_pack: dict[str, list[Want]] = {}
    for want in work.wants:
        by_pack.setdefault(want.pack, []).append(want)
    if by_pack.get("egx"):  # the whole EGX board, one request: only final closes (not during trading)
        final, utc_today = final_day("egx", now), now.astimezone(timezone.utc).date()
        if final == utc_today or utc_today.weekday() not in PACKS["egx"].days:
            try:
                board = tradingview.fetch(session, "egx", fmt_date(final))
                closes = {q.key: q for q in board.quotes}
                for want in by_pack["egx"]:
                    if want.key in closes:
                        keep(want, [closes[want.key]])
            except SourceError:
                failed.append("TradingView")
    if by_pack.get("eg-funds") or work.unlinked:  # every Egyptian fund's latest NAV, one request
        try:
            listing = mubasher.fetch(session)
            navs = {q.key: q for q in listing.quotes}
            by_pack.setdefault("eg-funds", []).extend(link_funds(work, listing.instruments))
            for want in by_pack["eg-funds"]:
                if want.key in navs:
                    keep(want, [navs[want.key]])
        except SourceError:
            failed.append("Mubasher")
    golds = by_pack.get("gold", [])
    if golds and time.monotonic() <= deadline:  # two series price every purity: gold in dollars, the dollar in pounds
        oldest = min([date.fromisoformat(d) for want in golds for d in want.month_ends] or [on])
        try:
            grams = per_gram(yahoo.fetch_history(session, "XAU/USD", _range(oldest, on)),
                             yahoo.fetch_history(session, "USD/EGP", _range(oldest, on)))
        except SourceError:
            failed.append("Yahoo Finance")
        else:
            for want in golds:
                pick(want, [Quote(want.key, q.date, (q.close * want.purity).quantize(Decimal("0.000001")), q.source)
                            for q in grams], False)
    for rate in work.rates:  # exchange rates: the closes that stand for each day lacking one, and the latest
        if time.monotonic() > deadline:
            break
        try:
            quotes = yahoo.fetch_history(session, f"{rate.currency}/{RATE_PIVOT}", _range(date.fromisoformat(min(rate.days)), on))
        except SourceError:
            if "Yahoo Finance" not in failed:
                failed.append("Yahoo Finance")
            continue
        final = min(now.astimezone(timezone.utc).date() - timedelta(days=1), on)  # a currency trades round the clock
        ordered = sorted((q for q in quotes if date.fromisoformat(q.date) <= final), key=lambda q: q.date)
        chosen: dict[str, Decimal] = {}
        for day in rate.days:
            before = [q for q in ordered if q.date <= day]
            if before and (date.fromisoformat(day) - date.fromisoformat(before[-1].date)).days <= NEAR_DAYS:
                chosen[before[-1].date] = before[-1].close
        if ordered:
            chosen[ordered[-1].date] = ordered[-1].close
        found.setdefault(f"fx:{rate.currency}", {}).update(chosen)
    for want in work.wants:  # history: month-ends still missing, and a latest close the board did not give
        latest_known = bool(found.get(want.asset_id))
        if want.pack == "gold" or (not want.month_ends and latest_known) or time.monotonic() > deadline:
            continue
        oldest = date.fromisoformat(min(want.month_ends)) if want.month_ends else on
        try:
            if want.pack == "eg-funds":
                quotes = mubasher.fetch_history(session, want.key, want.key.rsplit(":", 1)[1])
            else:
                quotes = yahoo.fetch_history(session, want.key, _range(oldest, on))
        except SourceError:
            name = "Mubasher" if want.pack == "eg-funds" else "Yahoo Finance"
            if name not in failed:
                failed.append(name)
            continue
        pick(want, quotes, latest_known)
    return found, failed


def save(c, work: Plan, found: dict, failed: list[str]) -> Report:
    """Write what was fetched (a typed price on the same day still wins), post the month-end revaluations
    it allows, and remember what is still missing for Needs you."""
    report = Report(failed=list(failed), unknown=list(work.unknown), other_currency=list(work.other_currency))
    on = date.fromisoformat(work.on)
    for want in work.unlinked:
        if want.asset_id in work.linked:
            c.assets.link_market(want.asset_id, work.linked[want.asset_id])
            report.linked.append(want.name)
        elif "Mubasher" not in failed:
            report.unmatched.append(want.name)
    for want in work.wants:
        closes = found.get(want.asset_id, {})
        for day, close in sorted(closes.items()):
            if (on - date.fromisoformat(day)).days > NEAR_DAYS and not any(
                    0 <= (date.fromisoformat(m) - date.fromisoformat(day)).days <= NEAR_DAYS for m in want.month_ends):
                continue  # an old close that stands for no month-end we need
            c.assets.set_price(want.asset_id, day, Decimal(close).quantize(Decimal("0.000001")), source=SOURCE)
            report.saved += 1
        if closes:
            report.priced.append(want.name)
            if want.pack == "gold":
                report.gold.append(want.name)
    for rate in work.rates:
        for day, close in sorted(found.get(f"fx:{rate.currency}", {}).items()):
            save_rate(c.db, day, rate.currency, RATE_PIVOT, Decimal(close), SOURCE)
            report.rates += 1
    c.reevaluations.process_due()
    missing_ids = []
    for want in work.wants:
        for day in want.month_ends:
            if not c.reevaluations.has_price(want.asset_id, day):
                report.missing.append((want.name, day))
                missing_ids.append([want.asset_id, day])
    try:
        earlier = json.loads(c.settings.get(MISSING_SETTING) or "[]")
    except ValueError:
        earlier = []
    planned = {w.asset_id for w in work.wants}
    kept = [pair for pair in earlier if isinstance(pair, list) and len(pair) == 2 and pair[0] not in planned]
    c.settings.set(MISSING_SETTING, json.dumps((kept + missing_ids)[:200]))
    if report.missing and report.failed:
        c.settings.set(FAILS_SETTING, str(failures(c) + 1))
    elif not report.missing:
        c.settings.set(FAILS_SETTING, "0")
    return report


def failures(c) -> int:
    """Fetches in a row that a failing source left incomplete: after two, Lightning offers the shared files."""
    try:
        return int(c.settings.get(FAILS_SETTING) or 0)
    except ValueError:
        return 0


def fetch_now(c, on: date, session=None, now: datetime | None = None) -> Report:
    """Update prices: every held investment's latest close and every month-end it lacks, now."""
    work = plan(c, on, now)
    found, failed = gather(work, session, now) if work.wants or work.unlinked or work.rates else ({}, [])
    return save(c, work, found, failed)


def fetch_if_due(c, on: date, session=None, now: datetime | None = None) -> Report | None:
    """On opening a profile: fetch only when a held investment lacks a passed month-end's price, at most once
    a day. None when nothing was due (no request is made), offline, or the profile is a read-only copy."""
    if c.db.read_only or not enabled() or c.settings.get(TRIED_SETTING) == fmt_date(on):
        return None
    work = plan(c, on, now)
    if not work.month_ends_missing():
        return None
    c.settings.set(TRIED_SETTING, fmt_date(on))
    found, failed = gather(work, session, now, budget=12.0)
    return save(c, work, found, failed)


# ------------------------------------------------------------------ in the background, on opening a profile
@dataclass
class _Job:
    container: object
    work: Plan
    done: threading.Event = field(default_factory=threading.Event)
    found: dict = field(default_factory=dict)
    failed: list = field(default_factory=list)


_job: _Job | None = None  # one open profile per app, so at most one fetch in flight


def start_if_due(c, on: date, session=None, now: datetime | None = None) -> bool:
    """fetch_if_due without the wait: the sources are asked on another thread while the profile opens;
    apply_finished() saves the answer on the next page. False when nothing was due (no request is made)."""
    global _job
    # Journal profiles use JournalAutomation: its worker returns only data, and
    # the owning loop publishes every save through the home confirmation path.
    if c.db.has_table("journal_meta"):
        return False
    if c.db.read_only or not enabled() or c.settings.get(TRIED_SETTING) == fmt_date(on):
        return False
    work = plan(c, on, now)
    if not work.month_ends_missing():
        return False
    c.settings.set(TRIED_SETTING, fmt_date(on))
    job = _Job(c, work)

    def run() -> None:
        try:
            job.found, job.failed = gather(work, session, now, budget=30.0)
        except Exception:  # noqa: BLE001 - an unexpected answer leaves prices as they were
            job.failed = ["the price sources"]
        finally:
            job.done.set()

    _job = job
    threading.Thread(target=run, name="online-prices", daemon=True).start()
    return True


def running(c) -> bool:
    """Whether a background fetch for this profile is still asking the sources (pages show it in a corner)."""
    job = _job
    return job is not None and job.container is c and not job.done.is_set()


def apply_finished(c) -> str:
    """Save a finished background fetch for this profile, on the caller's (the database's) thread, and say
    what it did, once. "" while it runs, or when there is nothing to save."""
    global _job
    job = _job
    if job is None:
        return ""
    # A caller for a newly opened profile proves the old container has been
    # closed. Drop its completed result without touching either connection.
    if job.container is not c:
        _job = None
        return ""
    db = getattr(c, "db", None)
    if db is None:
        _job = None
        return ""
    if db.has_table("journal_meta"):
        _job = None
        return ""
    if not job.done.is_set():
        return ""
    _job = None
    if job.container is not c or c.db.read_only:
        return ""  # the profile it was for is closed, or reopened read-only
    report = save(c, job.work, job.found, job.failed)
    return f"Month-end prices: {report.summary()}"


# ------------------------------------------------------------------ Settings › Price files › Test price sources
def probe(session=None) -> list[tuple[str, bool, str]]:
    """Ask each source once, as Update prices would, and say what came back: (source, works, what)."""
    session = session or Polite(min_interval=0.3, retries=1, timeout=10.0, user_agent=APP_AGENT)
    day = fmt_date(final_day("egx", datetime.now(timezone.utc)))
    def count(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"
    checks = (
        ("TradingView", lambda: count(len(tradingview.fetch(session, "egx", day).quotes), "Egyptian stock", "Egyptian stocks")),
        ("Yahoo Finance", lambda: count(len(yahoo.fetch_history(session, "EG:COMI", "1mo")), "day", "days")
         + " of CIB's history"),
        ("Mubasher", lambda: count(len(mubasher.fetch(session).quotes), "Egyptian fund", "Egyptian funds")),
        ("Banque Misr", lambda: count(len(banque_misr.fetch(session, fmt_date(date.today())).quotes),
                                                "exchange rate", "exchange rates")),
    )
    results = []
    for name, check in checks:
        try:
            results.append((name, True, check()))
        except SourceError as exc:
            results.append((name, False, str(exc)))
        except Exception as exc:  # noqa: BLE001 - an unexpected answer is a failing source, said plainly
            results.append((name, False, f"answered something Lightning cannot read ({exc.__class__.__name__})"))
    return results


def probe_summary(results) -> str:
    return " · ".join(f"{name}: {'works, ' + what if works else 'not working (' + what + ')'}"
                      for name, works, what in results)
