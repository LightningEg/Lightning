"""The Investments holdings table grouped five ways, the By currency breakdown and the USD lens.

Every figure here is arithmetic on rows the shared holdings read model already built: a view only regroups the same holdings, so each
view's total is Holdings value. Nothing is stored; the USD lens is a display conversion at one dated rate.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from lightning.core.money import ZERO
from lightning.market.iso import venue_name

from .lots import allocate_value, cagr, roi

VIEWS = ("class", "account", "currency", "market", "security")
VIEW_LABELS = {"class": "By class", "account": "By account", "currency": "By currency", "market": "By market",
               "security": "By security"}
SHOWN = 4  # guideline A16: four names, then Other


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def parse_view(text: str | None) -> str:
    return text if text in VIEWS else "class"


def make_group(name: str, rows: list[dict], holdings_total: Decimal) -> dict:
    group = {"name": name, "value": ZERO, "cost": ZERO, "gain": ZERO, "invested": ZERO, "rows": rows}
    for r in rows:
        group["value"] += r["value"] or ZERO
        group["cost"] += r["cost"] or ZERO
        group["gain"] += r.get("gain") or ZERO
        group["invested"] += r.get("invested", r["value"] or ZERO)
    rows.sort(key=lambda r: (-(r["value"] or ZERO), (r["h"].asset_name if r["h"] else r["name"]).casefold()))
    group["weight"] = group["value"] / holdings_total * 100 if holdings_total else ZERO
    group["gain_pct"] = group["gain"] / group["invested"] * 100 if group["invested"] else None
    return group


def regroup(view: str, class_groups: list[dict], holdings_total: Decimal, *, accounts: dict, assets: dict,
            base: str, other_label: str = "Other") -> list[dict]:
    """The same rows, grouped by ``view``. ``accounts`` maps id -> Account, ``assets`` maps id -> asset."""
    if view == "class":
        return class_groups
    keyed: dict[str, list[dict]] = {}
    for g in class_groups:
        for r in g["rows"]:
            h = r["h"]
            asset = assets.get(h.asset_id if h else r.get("asset_id"))
            if view == "account":
                account = accounts.get(h.account_id if h else r["account_id"])
                parent = accounts.get(getattr(account, "parent_id", None))  # a pocket rolls up into its broker
                owner = parent or account
                name = owner.name if owner else (h.account_label if h else r["name"])
            elif view == "currency":
                name = (asset.currency if asset is not None else None) or base
            elif view == "market":
                mic = getattr(asset, "mic", None)
                is_fund = str(getattr(asset, "code", "")).startswith("FND:")  # a fund is not a share on that exchange
                name = "Funds" if is_fund else venue_name(mic) if mic else g["name"]  # unlisted: its kind (Certificates, Gold, ...)
            else:  # security: one row per asset, the accounts that hold it beneath
                name = h.short_name if h else r["name"]
            keyed.setdefault(name, []).append(r)
    groups = sorted((make_group(n, rows, holdings_total) for n, rows in keyed.items()),
                    key=lambda g: (-g["value"], g["name"].casefold()))
    if view == "market" and len(groups) > SHOWN + 1:
        tail = [r for g in groups[SHOWN:] for r in g["rows"]]
        groups = groups[:SHOWN] + [make_group(other_label, tail, holdings_total)]
    return groups


def by_currency(holdings: dict[str, Decimal], cash: dict[str, Decimal], base: str, other_label: str = "Other") -> dict:
    """Value per currency (holdings plus brokerage cash), in the profile currency: four, then Other.

    ``holdings`` and ``cash`` map a currency code to its value in the profile currency."""
    totals: dict[str, Decimal] = {}
    for source in (holdings, cash):
        for code, value in source.items():
            totals[code] = totals.get(code, ZERO) + (value or ZERO)
    total = sum(totals.values(), ZERO)
    ordered = sorted(((c, v) for c, v in totals.items() if v), key=lambda i: (-i[1], i[0]))
    shown, rest = ordered[:SHOWN], ordered[SHOWN:]
    if len(rest) == 1:  # one name is not worth an Other
        shown, rest = ordered, []
    rows = [{"label": c, "value": v, "share": v / total * 100 if total else ZERO} for c, v in shown]
    if rest:
        rest_value = sum((v for _, v in rest), ZERO)
        rows.append({"label": other_label, "value": rest_value, "share": rest_value / total * 100 if total else ZERO,
                     "note": ", ".join(c for c, _ in rest)})
    abroad = total - totals.get(base, ZERO)
    return {"rows": rows, "total": total, "abroad": abroad, "abroad_share": abroad / total * 100 if total else ZERO}


def fx_total(rows: list[dict]) -> Decimal:
    """What the exchange rate added to the unrealized gain of foreign holdings (sum of fx_part)."""
    return sum((r["fx_part"] for r in rows if r.get("fx_part") is not None), ZERO)


def in_lens(groups: list[dict], divisor: Decimal) -> list[dict]:
    """The groups with every pound figure divided by ``divisor`` (units, native prices and percentages stay)."""
    out = []
    for g in groups:
        rows = []
        for r in g["rows"]:
            row = dict(r)
            for key in ("cost", "value", "gain", "price_part", "fx_part", "invested"):
                if r.get(key) is not None:
                    row[key] = r[key] / divisor
            if not r.get("currency"):  # a pound price per unit; a foreign one stays in its own currency
                for key in ("average_cost", "price"):
                    if r.get(key) is not None:
                        row[key] = r[key] / divisor
            rows.append(row)
        out.append({**g, "rows": rows, "value": g["value"] / divisor, "cost": g["cost"] / divisor,
                    "gain": g["gain"] / divisor, "invested": (g.get("invested") or 0) / divisor})
    return out


def _lens(value, divisor: Decimal):
    return None if value is None else value / divisor



def grouped_figures(class_groups: list[dict], total: Decimal, report: dict, spark: dict, *,
                    accounts: dict, assets: dict, base: str, other: str, view: str,
                    rate, use_usd: bool) -> dict:
    """One grouping/lens calculation for holdings, currency totals and hero values.

    A lens changes denomination only; percentages and stored values stay intact.
    The caller supplies the dated quote and localized Other label, never formulas.
    """
    kwargs = {"accounts": accounts, "assets": assets,
              "base": base, "other_label": other}
    currency_groups = regroup("currency", class_groups, total, **kwargs)
    breakdown = by_currency({g["name"]: g["value"] for g in currency_groups},
                                          report.get("investment_cash_by_currency") or {}, base, other)
    rows = [r for g in class_groups for r in g["rows"]]
    gain = sum((g["gain"] for g in class_groups), ZERO)
    fx_gain = fx_total(rows)
    groups = regroup(view, class_groups, total, **kwargs)
    lens_usd = rate is not None and use_usd
    divisor = rate.rate if lens_usd else Decimal(1)
    if lens_usd:
        groups = in_lens(groups, divisor)
        breakdown = {**breakdown, "total": breakdown["total"] / divisor, "abroad": breakdown["abroad"] / divisor,
                     "rows": [{**r, "value": r["value"] / divisor} for r in breakdown["rows"]]}
    return {"holding_groups": groups, "view": view, "views": VIEW_LABELS,
            "currency_card": breakdown, "fx_gain": fx_gain / divisor, "total_gain": gain / divisor,
            "lens": {"usd": lens_usd, "code": "USD" if lens_usd else base, "available": rate is not None,
                     "rate": rate.rate if rate else None, "as_of": rate.date if rate else None,
                     "divisor": divisor},
            "hero_result": _lens(report.get("result"), divisor),
            "hero_value": _lens(spark["latest"], divisor),
            "hero_change": _lens(spark["change"], divisor)}


def purchase_returns(h, day: str):
    """Your own purchases still held, and the pieces of your sales, each with its return and its return per year
    (NF-5D). Percent figures are worked out here, never in the template."""
    def pct(rate):
        return None if rate is None else rate * 100
    mine = [lot for lot in h.lots if lot.owner_id is None and lot.quantity > ZERO]
    values = [None] * len(mine)
    if mine and h.value is not None and h.quantity > ZERO:
        # Costs and the headline value are in profile currency; h.price is a native quote.
        # Use the same owned share as Position.owned_only, with the last lot taking the remainder.
        owned_value = h.value * (sum((lot.quantity for lot in mine), ZERO) / h.quantity)
        values = allocate_value(owned_value, [lot.quantity for lot in mine])
    held = [{"opened": lot.opened, "units": lot.quantity, "cost": lot.cost,
             "value": value,
             "gain": None if value is None else value - lot.cost,
             "roi": None if value is None else pct(roi(value - lot.cost, lot.cost)),
             # A yearly rate on weeks is a guess dressed as a fact: it shows only once held a full year (r30 N2).
             "cagr": None if value is None or _days_between(lot.opened, day) < 365 else
                     pct(cagr(value, lot.cost, _days_between(lot.opened, day)))}
            for lot, value in zip(mine, values)]
    sold = [{"opened": d.lot_opened, "sold": d.sold, "units": d.quantity, "cost": d.cost, "proceeds": d.proceeds,
             "gain": d.gain, "roi": pct(d.roi), "cagr": pct(d.cagr) if d.days_held >= 365 else None}
            for d in h.disposals if d.owner_id is None and d.quantity]
    return held, sold
