from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request

from lightning.core.dates import month_of, parse_date, today
from lightning.core.figures import FIGURES
from lightning.core.errors import ValidationError
from lightning.planning.emergency_context import emergency_liquidity_context
from ..health_rows import _TONE, limit_words, meter as figure_meter, tone_of

from .. import charts, kpis, status as page_status
from ..periods import parse_period
from ..web import container, render

router = APIRouter()

# The page answers "Am I financially healthy?": four headline figures, then every figure against its limit.
KPI_KEYS = ("emergency_fund", "savings_rate", "debt_to_net_worth", "fixed_costs_to_income")
GROUPS = (("Cushion", ("emergency_fund",)),
          ("Saving", ("savings_rate", "planned_savings_rate", "investing_rate")),
          ("Debt and monthly commitments", ("debt_to_cash", "debt_to_net_worth", "fixed_costs_to_income",
                                            "loan_payments_to_income")))


BAND_WORDS = {"good": "Good", "watch": "Watch", "alert": "Needs you"}
_BAND_CHIP = {"good": "up", "watch": "", "alert": "over"}  # green tint, quiet, rose (A08)


def _health_trend(months, values, name: str, tone: str) -> dict:
    """Use the zero-based trend axis and keep missing months as gaps in the line."""
    chart = charts.trend(months, [{"name": name, "tone": tone, "values": values}], min_points=3)
    if chart["too_short"]:
        return chart
    dots = iter(chart["series"][0]["dots"])
    runs, run = [], []
    for value in values:
        if value is None:
            if run:
                runs.append(run)
                run = []
        else:
            dot = next(dots)
            run.append(dot)
    if run:
        runs.append(run)
    zero = next(tick["y"] for tick in chart["ticks"] if tick["value"] == 0)
    chart["runs"] = [{"line": " ".join(f"{d['x']:.2f},{d['y']:.2f}" for d in run),
                      "area": (f"M{run[0]['x']:.2f},{zero:.2f} "
                               + " ".join(f"L{d['x']:.2f},{d['y']:.2f}" for d in run)
                               + f" L{run[-1]['x']:.2f},{zero:.2f} Z")}
                     for run in runs if len(run) >= 2]
    return chart


def _chip(period: str) -> str:
    """The period in a few characters: "As of 2026-10-06 · months of …" → "2026-10-06",
    "Monthly · 2026-07 to 2026-09" → "2026-07 to 2026-09"."""
    parts = period.split(" · ")
    text = parts[1] if parts[0] == "Monthly" and len(parts) > 1 else parts[0]
    return text.removeprefix("As of ")


def _kpi(item, label: str) -> dict:
    """One headline card (stat_tile): coloured by what the figure means, its chip says good or bad."""
    tone = tone_of(item)
    chip_tone = _BAND_CHIP.get(item.band or "", "")
    meter = figure_meter(item)
    return {"key": item.key, "label": label, "href": item.href, "surface": tone,
            "value": None if item.gap else item.value, "empty": "—",
            "kind": "months" if item.unit == "months" else "rate",
            "badge": {"text": BAND_WORDS.get(item.band or "") or _chip(item.period), "tone": chip_tone, "arrow": ""},
            "sub": item.gap or limit_words(item), "band": item.band,
            "meter": {"tone": meter["tone"], "width": meter["fill"], "ticks": meter["ticks"]} if meter else None}


def _trend_summary(trends, attr: str) -> dict:
    known = [(m.month, getattr(m, attr)) for m in trends if getattr(m, attr) is not None]
    if not known:
        return {}
    low = min(known, key=lambda x: x[1])
    return {"first": trends[0].month, "last_month": known[-1][0], "last": known[-1][1],
            "low_month": low[0], "low": low[1], "high": max(value for _, value in known)}


@router.get("/financial-health")
async def financial_health(request: Request):
    c = container(request)
    raw = request.query_params.get("as_of")
    error = ""
    period = None
    try:
        if raw:  # the phone's date box and old links
            as_of = parse_date(raw, "as-of date")
            if as_of > today():
                raise ValidationError("Choose today or an earlier as-of date.", "as_of")
        else:  # the PC's one period control (A05): balances as of the period's last day
            period = parse_period(request.query_params, today(), c.reporting.first_activity_date())
            as_of = period.end
    except ValidationError as exc:
        as_of = today()
        error = exc.message
    if period is None or error:
        period = parse_period({"period": "month", "month": month_of(as_of)}, today())
    overview = c.health.overview(as_of)
    liquidity_context = emergency_liquidity_context(c.position.at(as_of, match_payments=False))
    trends = overview["trends"]
    labels = {key: ("Emergency fund" if key == "emergency_fund" else FIGURES[key].label) for key in _TONE}
    by_key = {item.key: item for item in overview["figures"]}
    rows = [{"title": title, "items": [{"item": by_key[k], "meter": figure_meter(by_key[k]),
                                        "limit_words": limit_words(by_key[k])} for k in keys if k in by_key]}
            for title, keys in GROUPS]
    judged = [item for item in overview["figures"] if item.status in ("within your limit", "outside your limit") and item.limit is not None]  # BV-12D: only a figure with a limit
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
              "detail": " · ".join(x for x in (limit_words(item), item.period) if x), "href": item.href,
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
                  as_of_iso=as_of.isoformat(), period=period, month=period.start_text[:7],
                  today_iso=today().isoformat(),
                  # A month that says its gap in words is left out of the line (it skips missing points).
                  savings_chart=_health_trend([m.month for m in trends], savings_values, "Savings rate", "in"),
                  worth_chart=_health_trend([m.month for m in trends], worth_values, "Net worth", "hold"),
                  savings_spark=charts.sparkline(savings_values),
                  worth_spark=(charts.sparkline(worth_values) if all(v is not None for v in worth_values)
                               else {"points": ""}),
                  error=error)


