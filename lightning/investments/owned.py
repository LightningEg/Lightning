"""Your own share of the portfolio, apart from units held for someone else, and the other figures the
Investments pages show (IT-12AE4: a screen reads these, it never works money out itself)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from lightning.core.money import ZERO


@dataclass
class OwnedPortfolio:
    """The portfolio on one day, your units only, beside the day before the period starts."""
    custody: dict  # (account id, asset id) -> units held for someone else today
    prior_custody: dict  # the same, the day before the period
    starting_owned_value: Decimal
    own_by_holding: dict  # "account:asset" -> your value
    own_cost_by_holding: dict
    own_units_by_holding: dict
    owned_value: Decimal
    owned_cost: Decimal
    owned_positions: list
    asset_class_rows: list  # (class name, totals) with something of yours, largest first
    buckets: dict  # allocation class -> your value
    owned_rows: list  # (holding, your value, bucket, horizon, your cost, your gain, your units)
    period_realized: Decimal
    period_distributions: Decimal

    @property
    def owned_unrealized(self) -> Decimal:
        return self.owned_value - self.owned_cost

    @property
    def period_value_change(self) -> Decimal:
        return self.owned_value - self.starting_owned_value

    @property
    def max_class_result(self) -> Decimal:
        """The largest class result this period (its size only), the scale of the class bars; 1 when none."""
        return max((abs(row["period_unrealized"] + row["realized"] + row["dividends"])
                    for _, row in self.asset_class_rows), default=ZERO) or Decimal(1)


def owned_portfolio(reporting, money_from_others, preferences: dict, p, prior, day: str, before_day: str,
                    period_interest: Decimal) -> OwnedPortfolio:
    """Split ``p`` (the portfolio on ``day``) and ``prior`` (on ``before_day``) into what is yours and what
    you hold for others, per holding and per class; ``preferences`` are the assets' allocation choices."""
    prior_by_key = {(x.account_id, x.asset_id): x for x in prior.positions}
    custody = defaultdict(lambda: ZERO)
    for row in money_from_others.investment_positions(day):
        custody[(row["account_id"], row["asset_id"])] += row["units"]
    prior_custody = defaultdict(lambda: ZERO)
    prior_custody_value = ZERO
    for row in money_from_others.investment_positions(before_day):
        prior_custody[(row["account_id"], row["asset_id"])] += row["units"]
        valuation = reporting.value_of(row["asset_id"], row["units"], before_day)
        if valuation.value is not None:
            prior_custody_value += valuation.value
    starting_owned_value = prior.value - prior_custody_value
    custody_value = custody_cost = Decimal(0)
    own_by_holding = {}
    own_cost_by_holding = {}
    own_units_by_holding = {}
    for holding in p.open:
        units = custody.get((holding.account_id, holding.asset_id), 0)
        if not units:
            continue
        value = reporting.value_of(holding.asset_id, units, day).value
        held_value = value or Decimal(0)
        if value is not None:
            custody_value += value
        if holding.quantity:
            custody_cost += holding.cost_basis - holding.owned_cost_basis
        own_by_holding[f"{holding.account_id}:{holding.asset_id}"] = (holding.value or Decimal(0)) - held_value
        own_cost_by_holding[f"{holding.account_id}:{holding.asset_id}"] = holding.owned_cost_basis
        own_units_by_holding[f"{holding.account_id}:{holding.asset_id}"] = holding.quantity-units
    owned_value = p.value - custody_value
    owned_cost = p.cost_basis - custody_cost
    owned_positions = [h for h in p.open
                       if own_units_by_holding.get(f"{h.account_id}:{h.asset_id}", h.quantity) > ZERO]
    class_totals = defaultdict(lambda: {"total": ZERO, "yours": ZERO, "others": ZERO, "capital": ZERO,
                                        "starting_capital": ZERO, "unrealized": ZERO, "period_unrealized": ZERO,
                                        "realized": ZERO, "dividends": ZERO})
    for holding in p.open:
        category = holding.asset_class.split(" › ")[-1]
        total = holding.value or ZERO
        yours = own_by_holding.get(f"{holding.account_id}:{holding.asset_id}", total)
        row = class_totals[category]
        row["total"] += total; row["yours"] += yours; row["others"] += total-yours
        key = (holding.account_id, holding.asset_id)
        holding_key = f"{holding.account_id}:{holding.asset_id}"
        owned_capital = own_cost_by_holding.get(holding_key, holding.cost_basis)
        row["capital"] += owned_capital
        row["unrealized"] += yours - owned_capital
        old = prior_by_key.get(key)
        old_owned_value, old_owned_capital = ZERO, ZERO
        if old and old.quantity:
            old_other_units = prior_custody.get(key, ZERO)
            old_valuation = reporting.value_of(holding.asset_id, old_other_units, before_day)
            old_owned_value = (old.value or ZERO) - (old_valuation.value or ZERO)
            old_owned_capital = old.owned_cost_basis
        row["starting_capital"] += old_owned_capital
        row["period_unrealized"] += (yours - owned_capital) - (old_owned_value - old_owned_capital)
        row["realized"] += (holding.owned_realized or ZERO)-((old.owned_realized or ZERO) if old else ZERO)
        row["dividends"] += holding.owned_net_dividends-(old.owned_net_dividends if old else ZERO)
    asset_class_rows = sorted(((name, row) for name, row in class_totals.items() if row["yours"] > ZERO),
                              key=lambda item: (-item[1]["yours"], item[0].casefold()))
    buckets = defaultdict(lambda: ZERO)
    owned_rows = []
    for h in p.open:
        key = f"{h.account_id}:{h.asset_id}"
        owned_units = own_units_by_holding.get(key, h.quantity)
        if owned_units <= ZERO:
            continue
        yours = own_by_holding.get(key, h.value) if h.value is not None else None
        asset = preferences.get(h.asset_id)
        bucket = (asset["allocation_bucket"] if asset else None) or h.asset_class.split(" › ")[-1]
        horizon = (asset["investment_horizon"] if asset else None) or "Unassigned"
        if yours is not None:
            buckets[bucket] += yours
        capital = own_cost_by_holding.get(key, h.cost_basis)
        owned_rows.append((h, yours, bucket, horizon, capital, yours-capital if yours is not None else None,
                           owned_units))
    return OwnedPortfolio(
        custody=custody, prior_custody=prior_custody, starting_owned_value=starting_owned_value,
        own_by_holding=own_by_holding, own_cost_by_holding=own_cost_by_holding,
        own_units_by_holding=own_units_by_holding, owned_value=owned_value, owned_cost=owned_cost,
        owned_positions=owned_positions, asset_class_rows=asset_class_rows, buckets=buckets, owned_rows=owned_rows,
        period_realized=p.owned_realized - prior.owned_realized,
        period_distributions=p.owned_dividends - prior.owned_dividends + period_interest)


def target_total(targets: dict) -> Decimal:
    """What the target weights add up to, in percent."""
    return sum(targets.values(), ZERO)


def target_room(targets: dict, bucket: str) -> tuple[Decimal, Decimal]:
    """(what the other classes' targets take, what is left of 100% for ``bucket``; below zero when over)."""
    others = sum((w for b, w in targets.items() if b != bucket), ZERO)
    return others, 100 - others


def in_lens(amount: Decimal | None, divisor) -> Decimal | None:
    """An amount in the lens's currency (``divisor`` is the rate; 1 for pounds)."""
    return None if amount is None else amount / divisor


def six_month_change(latest: Decimal, first: Decimal, added: Decimal) -> Decimal:
    """Value change over the six-month line, without holdings recorded as already owned (not growth)."""
    return latest - first - added


def dividends_since(current, before) -> list[tuple[str, Decimal]]:
    """(asset name, your dividends) paid between the ``before`` portfolio and the ``current`` one."""
    paid_before = {(x.account_id, x.asset_id): x.owned_dividends for x in before.positions}
    return [(x.asset_name, x.owned_dividends - paid_before.get((x.account_id, x.asset_id), ZERO))
            for x in current.positions]


def by_class(rows: list[dict], class_of: dict) -> dict[str, Decimal]:
    """Each row's ``amount`` added up by the class of its (asset id, account id); rows of no class left out."""
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        name = class_of.get((row.get("asset_id"), row.get("account_id")))
        if name:
            totals[name] += row["amount"]
    return totals


def suggested_total(rows: list[dict]) -> Decimal:
    """The planner rows' suggested amounts added up."""
    return sum((r["suggested"] for r in rows), ZERO)


def owned_by_bucket(portfolio, custody: dict, preferences: dict) -> tuple[dict, Decimal]:
    """Your value per allocation class (units held for others left out) and their total, positive only."""
    values = defaultdict(lambda: ZERO); total = ZERO
    for position in portfolio.open:
        units = max(ZERO, position.quantity-custody.get((position.account_id, position.asset_id), ZERO))
        value = (position.value or ZERO)*units/position.quantity if position.quantity else ZERO
        if value <= ZERO:
            continue
        meta = preferences.get(position.asset_id)
        bucket = (meta["allocation_bucket"] if meta else None) or position.asset_class.split(" › ")[-1]
        values[bucket] += value; total += value
    return values, total


def planner_row(bucket: str, value: Decimal, total: Decimal, suggested: Decimal, amount: Decimal) -> dict:
    """A class's share now and after the suggested amount is added, in percent."""
    return {"weight": value/total*100 if total else ZERO,
            "after": (value+suggested)/(total+amount)*100 if total+amount else ZERO}


def values_by_bucket(rows, bucket_of) -> dict:
    """Owned holdings' values added up per allocation class (``bucket_of(row)``); unpriced rows left out."""
    values = defaultdict(lambda: ZERO)
    for row in rows:
        if row.value is None:
            continue
        values[bucket_of(row)] += row.value
    return values


def per_share_total(amount: Decimal, units: Decimal) -> Decimal:
    """A per-share dividend times the shares held, to the piastre."""
    return (amount * units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def unit_price(total: Decimal, quantity: Decimal) -> Decimal:
    """The unit price behind a total value, to the six places a price is kept (a total rarely divides evenly)."""
    return (total / quantity).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def exact_from_e6(value: int) -> Decimal:
    """Stored micro-units as an exact Decimal (unlike ``from_e6``, no normalising)."""
    return Decimal(value) / Decimal(1_000_000)
