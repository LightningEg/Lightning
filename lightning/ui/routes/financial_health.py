from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request

from lightning.core.dates import parse_date, today
from lightning.core.figures import FIGURES
from lightning.core.errors import ValidationError
from lightning.planning.emergency_context import emergency_liquidity_context

from .. import charts, kpis, status as page_status
from ..web import container, render

router = APIRouter()

# What each figure's colour means when it is inside its limit (guideline A03, A08): a cushion is money you
# hold, a savings rate is money kept, debt and fixed costs are money out. Outside its limit it needs you.
_TONE = {"emergency_fund": "hold", "net_worth": "hold", "savings_rate": "in", "planned_savings_rate": "in",
         "debt_to_cash": "out", "debt_to_net_worth": "out", "fixed_costs_to_income": "out",
         "loan_payments_to_income": "out"}
# The page answers "Am I financially healthy?": four headline figures, then every figure against its limit.
KPI_KEYS = ("emergency_fund", "savings_rate", "debt_to_net_worth", "fixed_costs_to_income")
GROUPS = (("Cushion", ("emergency_fund",)),
          ("Saving", ("savings_rate", "planned_savings_rate")),
          ("Debt and monthly commitments", ("debt_to_cash", "debt_to_net_worth", "fixed_costs_to_income",
                                            "loan_payments_to_income")))


BAND_WORDS = {"good": "Good", "watch": "Watch", "alert": "Needs you"}
_BAND_CHIP = {"good": "up", "watch": "", "alert": "over"}  # green tint, quiet, rose (A08)


def _tone(item) -> str:
    return "over" if item.band == "alert" else _TONE.get(item.key, "hold")


def _meter(item) -> dict | None:
    """The figure on a track that reaches a little past the larger of the figure and its limit; the
    limit is a tick. Percentages use 0–100% unless a figure or limit goes past it."""
    if item.value is None or item.gap:
        return None
    value = max(Decimal(item.value), Decimal(0))
    limit = Decimal(item.limit) if item.limit is not None else None
    if item.unit == "%":
        top = max(Decimal(100), value * Decimal("1.1"), (limit or 0) * Decimal("1.1"))
    else:
        top = max((limit or 0) * Decimal("1.25"), value * Decimal("1.1"), Decimal(1))
    alert = Decimal(item.alert) if item.alert is not None else None
    return {"fill": float(min(value / top * 100, Decimal(100))),
            "tick": float(limit / top * 100) if limit is not None else None,
            "ticks": [float(min(bound / top * 100, Decimal(100))) for bound in (limit, alert) if bound is not None],
            "tone": {"out": "spend"}.get(_tone(item), _tone(item))}  # the chart tone names (style.css)


def _limit_words(item) -> str:
    if item.limit is None:
        return "No limit set"
    side = "at least" if item.direction == "minimum" else "at most"
    amount = f"{item.limit:.1f}%" if item.unit == "%" else f"{item.limit:.0f} months"
    if item.band == "alert" and item.alert is not None:
        past = f"{item.alert:.1f}%" if item.unit == "%" else f"{item.alert:.0f} months"
        return f"{'Below' if item.direction == 'minimum' else 'Above'} {past}: needs you"
    if item.band == "watch":
        return f"Good is {side} {amount}"
    if item.band == "good":
        return f"Good: {side} {amount}"
    return f"Good is {side} {amount}"


def _chip(period: str) -> str:
    """The period in a few characters: "As of 2026-10-06 · months of …" → "2026-10-06",
    "Monthly · 2026-07 to 2026-09" → "2026-07 to 2026-09"."""
    parts = period.split(" · ")
    text = parts[1] if parts[0] == "Monthly" and len(parts) > 1 else parts[0]
    return text.removeprefix("As of ")


def _kpi(item, label: str) -> dict:
    """One headline card (stat_tile): coloured by what the figure means, its chip says good or bad."""
    tone = _tone(item)
    chip_tone = _BAND_CHIP.get(item.band or "", "")
    meter = _meter(item)
    return {"key": item.key, "label": label, "href": item.href, "surface": tone,
            "value": None if item.gap else item.value, "empty": "—",
            "kind": "months" if item.unit == "months" else "rate",
            "badge": {"text": BAND_WORDS.get(item.band or "") or _chip(item.period), "tone": chip_tone, "arrow": ""},
            "sub": item.gap or _limit_words(item), "band": item.band,
            "meter": {"tone": meter["tone"], "width": meter["fill"], "ticks": meter["ticks"]} if meter else None}


def _trend_summary(trends, attr: str) -> dict:
    known = [(m.month, getattr(m, attr)) for m in trends if getattr(m, attr) is not None]
    if not known:
        return {}
    low = min(known, key=lambda x: x[1])
    return {"first": trends[0].month, "last_month": known[-1][0], "last": known[-1][1],
            "low_month": low[0], "low": low[1]}


@router.get("/financial-health")
async def financial_health(request: Request):
    c = container(request)
    raw = request.query_params.get("as_of")
    try:
        as_of = parse_date(raw, "as-of date") if raw else today()
        if as_of > today():
            raise ValidationError("Choose today or an earlier as-of date.", "as_of")
    except ValidationError as exc:
        as_of = today()
        error = exc.message
    else:
        error = ""
    overview = c.health.overview(as_of)
    liquidity_context = emergency_liquidity_context(c.position.at(as_of, match_payments=False))
    trends = overview["trends"]
    labels = {key: ("Emergency fund" if key == "emergency_fund" else FIGURES[key].label) for key in _TONE}
    by_key = {item.key: item for item in overview["figures"]}
    rows = [{"title": title, "items": [{"item": by_key[k], "meter": _meter(by_key[k]),
                                        "limit_words": _limit_words(by_key[k])} for k in keys if k in by_key]}
            for title, keys in GROUPS]
    judged = [item for item in overview["figures"] if item.status in ("within your limit", "outside your limit")]
    savings_values = [month.savings_rate for month in trends]
    worth_values = [month.net_worth for month in trends]
    # Answer first (guideline 3.33): the count within your limits is the Lead, the savings rate over time beside it;
    # each figure outside its limit is a Needs you row; the list below is the one home of every figure.
    within = sum(1 for item in judged if item.status == "within your limit")
    outside = [item for item in judged if item.band == "alert"]  # Watch stays quiet (A08)
    lead = (kpis.card("Within your limits", Decimal(within), kpis.compare(f"of the {len(judged)} figures you set a limit for"),
                      tone="in" if not outside else "over", kind="count", key="within",
                      line_=kpis.line(f"{len(outside)} need{'s' if len(outside) == 1 else ''} you" if outside else "All of them are good"))
            if judged else None)
    needs = [{"label": f"{labels.get(item.key, item.key)} is outside your limit",
              "detail": " · ".join(x for x in (_limit_words(item), item.period) if x), "href": item.href,
              "action": "See details"} for item in outside]
    status = page_status.health(within, len(judged), [labels.get(item.key, item.key) for item in outside])
    return render(request, "financial_health.html", **overview, lead=lead, needs=needs, status=status,
                  liquidity_context=liquidity_context,
                  limits=c.health.limit_settings(),
                  kpis=[_kpi(by_key[k], labels[k]) for k in KPI_KEYS if k in by_key],
                  groups=rows, labels=labels,
                  within=within, judged=len(judged),
                  savings_summary=_trend_summary(trends, "savings_rate"),
                  worth_summary=_trend_summary(trends, "net_worth"),
                  as_of_iso=as_of.isoformat(),
                  today_iso=today().isoformat(),
                  # A month that says its gap in words is left out of the line (it skips missing points).
                  savings_spark=charts.sparkline(savings_values),
                  worth_spark=(charts.sparkline(worth_values) if all(v is not None for v in worth_values)
                               else {"points": ""}),
                  error=error)
