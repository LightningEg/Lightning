"""Dated manual exchange rates, quoted in profile currency per foreign unit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, now_iso, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import check_places, from_e6, to_decimal, to_e6
from lightning.database.connection import Database
from lightning.market.bundle import MAX_GAP_DAYS


class CurrencyRates:
    def __init__(self, db: Database, profile_currency: str):
        self.db = db
        self.profile_currency = profile_currency

    def save(self, currency: str, day: str, rate: object) -> None:
        currency = (currency or "").strip().upper()
        if currency == self.profile_currency:
            raise ValidationError("The profile currency already has a rate of 1.", "currency")
        if not self.db.scalar("SELECT 1 FROM registered_currencies WHERE code=?", (currency,)):
            raise ValidationError("Register this currency first.", "currency")
        on = parse_date(day, "date")
        if on > today():
            raise ValidationError("The rate date cannot be in the future.", "date")
        value = check_places(to_decimal(rate, "rate"), 6)
        if value <= 0:
            raise ValidationError("Enter a rate greater than zero.", "rate")
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) "
                "VALUES(?,?,?,?,'MANUAL',?) ON CONFLICT(date,base,quote,source) "
                "DO UPDATE SET rate_e6=excluded.rate_e6,created_at=excluded.created_at",
                (fmt_date(on), currency, self.profile_currency, to_e6(value), now_iso()),
            )

    def list(self) -> list[dict]:
        rows = self.db.all(
            "SELECT date,base AS currency,quote,rate_e6,source FROM fx_rates "
            "WHERE quote=? ORDER BY date DESC,base,source LIMIT 300", (self.profile_currency,))
        return [dict(row) | {"rate": from_e6(row["rate_e6"])} for row in rows]


# ---------------------------------------------------------------- one lookup for every caller
# A rate is stored as quoted (foreign per profile currency, or any pair a price file quotes); derived rates
# (inverse, cross through EGP) are computed here and never stored.

SOURCE_RANK = ("MANUAL", "TRADE", "MARKET", "ONLINE")   # who wins when one day holds several rates
STALE_DAYS = MAX_GAP_DAYS       # older than this still values a balance but is shown "as of <date>"
MISSING_DAYS = 45               # older than this is no rate at all (Needs you)
PIVOT = "EGP"                   # cross rates run through the pound
_RANK_SQL = "CASE source " + " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(SOURCE_RANK)) + " ELSE 9 END"
_SIX = Decimal("0.000001")
ONE_ = Decimal(1)


@dataclass(frozen=True)
class Rate:
    rate: Decimal    # `quote` per one `base`, 6 places
    date: str        # the day the rate was quoted (the older day, for a cross rate)
    source: str      # MANUAL, TRADE, MARKET or ONLINE
    kind: str        # direct, inverse or cross
    age_days: int

    @property
    def stale(self) -> bool:
        return self.age_days > STALE_DAYS

    @property
    def as_of(self) -> str | None:
        """The date to show beside a value when the rate is not from the last STALE_DAYS."""
        return self.date if self.stale else None


@request_cached  # valuation asks for the same rate dozens of times per page; a write clears the memo
def _stored(db: Database, base: str, quote: str, day: str,
            exclude: tuple[str, ...] = ()) -> tuple[Decimal, str, str] | None:
    on = _date.fromisoformat(day)
    floor = (on - timedelta(days=min(MISSING_DAYS, on.toordinal() - 1))).isoformat()
    skip = f" AND source NOT IN ({','.join('?' for _ in exclude)})" if exclude else ""
    row = db.one(
        f"SELECT rate_e6,date,source FROM fx_rates WHERE base=? AND quote=? AND date<=? AND date>=?{skip} "
        f"ORDER BY date DESC,{_RANK_SQL} LIMIT 1", (base, quote, day, floor, *exclude))
    return (from_e6(row["rate_e6"]), row["date"], row["source"]) if row else None


def _pair(db: Database, base: str, quote: str, day: str,
          exclude: tuple[str, ...] = ()) -> tuple[Decimal, str, str, str] | None:
    """(exact rate, day, source, kind): direct, else inverse; when both exist the newer day wins, a tie
    going to the direct one. Rounded only once, by `rate_for`."""
    direct, inverse = _stored(db, base, quote, day, exclude), _stored(db, quote, base, day, exclude)
    if direct and (not inverse or direct[1] >= inverse[1]):
        return direct[0], direct[1], direct[2], "direct"
    if inverse:
        return ONE_ / inverse[0], inverse[1], inverse[2], "inverse"
    return None


def _age(day: str, on: str) -> int:
    return (_date.fromisoformat(day) - _date.fromisoformat(on)).days


def rate_for(db: Database, base: str, quote: str, day: str, exclude: tuple[str, ...] = ()) -> Rate | None:
    """`quote` per one `base` on `day`: direct, else inverse, else cross through EGP; None when no rate is
    newer than MISSING_DAYS. The one function valuation, revaluation and posting all use. `exclude` leaves out
    sources (a conversion's own saved rate when it is compared with the market's)."""
    if base == quote:
        return Rate(ONE_, day, "MANUAL", "direct", 0)
    found = _pair(db, base, quote, day, exclude)
    if not found and PIVOT not in (base, quote):
        first, second = _pair(db, base, PIVOT, day, exclude), _pair(db, PIVOT, quote, day, exclude)
        if first and second:
            found = (first[0] * second[0], min(first[1], second[1]),
                     max(first[2], second[2], key=SOURCE_RANK.index), "cross")
    if not found:
        return None
    value = found[0].quantize(_SIX)
    return Rate(value, found[1], found[2], found[3], _age(day, found[1])) if value > 0 else None


def save_rate(db: Database, day: str, base: str, quote: str, rate: Decimal, source: str) -> None:
    """Store a quoted rate from a file, a fetch or a conversion (a typed rate goes through CurrencyRates.save)."""
    value = Decimal(rate).quantize(_SIX)
    if value <= 0 or base == quote:
        return
    db.execute(
        "INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(date,base,quote,source) DO UPDATE SET rate_e6=excluded.rate_e6,created_at=excluded.created_at",
        (day, base, quote, to_e6(value), source, now_iso()))


def spread_cost(db: Database, base: str, sent: Decimal, sent_currency: str, received: Decimal,
                received_currency: str, day: str) -> Decimal | None:
    """What a conversion cost beyond the market, in the profile currency: the market value of what was sent
    minus the market value of what arrived (the conversion's own saved rate, source TRADE, is not the market).
    None when the market has no rate for the day."""
    def market(currency: str) -> Decimal | None:
        if currency == base:
            return ONE_
        found = rate_for(db, currency, base, day, exclude=("TRADE",))
        return found.rate if found else None

    given, got = market(sent_currency), market(received_currency)
    if given is None or got is None:
        return None
    return (sent * given - received * got).quantize(Decimal("0.01"))
