"""The phone's Investments page (templates/phone/investments/index.html): the hero sentence, the value line with its
Month / YTD / All links and the holdings as one flat list, shaped from the page's own figures (3AY11)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import Request

from lightning.core.dates import fmt_date, today
from lightning.core.figures import label
from lightning.core.money import ZERO, fmt, signed_pct
from lightning.ui import charts, status as page_status
from lightning.ui.i18n import translate


def _link(request: Request, **changes) -> str:
    """This page's address with some query parameters changed (None drops one); the period and the rest stay."""
    query = {**dict(request.query_params), **changes}
    query = {k: v for k, v in query.items() if v not in (None, "")}
    return "/investments" + ("?" + urlencode(query) if query else "")


PHONE_RANGES = (("month", "Month"), ("ytd", "YTD"), ("all", "All"))


PHONE_HOLDINGS_SHOWN = 5  # the page lists the biggest five; "See all" lists every holding, grouped


_SENTENCES = {(True, True): "Up {amt} {when} ({pct}).", (True, False): "Up {amt} {when}.",
              (False, True): "Down {amt} {when} ({pct}).", (False, False): "Down {amt} {when}."}


def _signed_percent(value) -> str | None:
    """+1.9% or −0.4%, one decimal, a real minus sign; a value that rounds to zero reads 0.0% (as the signed_pct filter)."""
    if value is None:
        return None
    return signed_pct(value) + "%"


def _when_phrase(period, current: bool, locale: str) -> str:
    """How the period reads inside the hero sentence: this month, in 2026-09, this year, since your first record."""
    if period.key == "month":
        return translate("this month", locale) if current else translate("in {month}", locale, month=period.start_text[:7])
    return translate({"ytd": "this year", "all": "since your first record"}.get(period.key, "in these dates"), locale)


def _phone_hero_line(result, growth, period, current: bool, locale: str) -> dict:
    """One calm sentence under Portfolio value: "Up 7,956 this month (+1.9%)." When there is no result, the page's own
    status sentence says why (a missing price) or that nothing moved."""
    if result is None or result == ZERO:
        return page_status.investments(result, True, period.key, current)
    pct = _signed_percent(growth)
    values = {"amt": fmt(abs(result), 0), "when": _when_phrase(period, current, locale)}
    if pct is not None:
        values["pct"] = pct
    return page_status.sentence(_SENTENCES[(result > ZERO, pct is not None)], **values)


def _phone_value_line(c, period, divisor: Decimal) -> tuple[Decimal, dict]:
    """Portfolio value on the period's last day, and the line of it from the first day to the last: seven dates
    spread evenly (five or three on a very short period), so the chart can name its first, middle and last."""
    span = (period.end - period.start).days  # not money
    count = 7 if span >= 6 else 5 if span >= 4 else 3 if span >= 2 else 0
    days = [period.start + timedelta(days=round(span * i / (count - 1))) for i in range(count)] if count else []  # not money
    values = [c.position.portfolio_value_in(day, divisor) for day in days]
    series = [{"name": label("portfolio_value"), "tone": "hold", "area": True, "values": values}]
    end_value = values[-1] if values else c.position.portfolio_value_in(period.end, divisor)
    return end_value, {**charts.trend([fmt_date(day) for day in days], series), "count": count}


def _phone_parts(c, request: Request, period, extras: dict, current: bool) -> dict:
    """What the phone's Investments page adds to the PC's figures: the hero (Portfolio value at the period's end and
    one sentence), the value line with its Month / YTD / All links, and the holdings as one flat list, biggest first
    (the biggest five, or every holding grouped when asked: ?holdings=all)."""
    value, chart = _phone_value_line(c, period, extras["lens"]["divisor"])
    rows = [r for g in extras["holding_groups"] for r in g["rows"]]
    rows.sort(key=lambda r: (r["value"] is None, -(r["value"] or ZERO), (r["h"].asset_name if r["h"] else r["name"]).casefold()))
    expanded = request.query_params.get("holdings") == "all" and len(rows) > PHONE_HOLDINGS_SHOWN
    return {"value": value, "chart": chart, "expanded": expanded,
            "line": _phone_hero_line(extras["hero_result"], extras["growth"], period, current,
                                     "ar" if c.settings.get("locale") == "ar" else "en"),
            "rows": rows if expanded else rows[:PHONE_HOLDINGS_SHOWN],
            "more": len(rows) > PHONE_HOLDINGS_SHOWN,
            "all_link": _link(request, holdings="all") + "#holdings-heading",
            "fewer_link": _link(request, holdings=None) + "#holdings-heading",
            "ranges": [{"key": key, "text": text, "selected": period.key == key,
                        "href": _link(request, period=key)} for key, text in PHONE_RANGES]}


def present(request, c, context: dict) -> dict:
    period = context["period"]
    return {"invest_phone": _phone_parts(c, request, period, context, period.end >= today())}
