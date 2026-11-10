"""The phone's Financial health: the investing rate sits with Saving here (the Overview's old tile; 3AN4, owner
2026-11-02). The PC shows that figure on Investments and the Overview, so its page does not carry it (3AY11)."""
from __future__ import annotations

from lightning.core.dates import fmt_date, parse_month
from lightning.investments.report import investing_rate, investment_period
from lightning.planning.health import HealthFigure
from lightning.ui.health_rows import limit_words, meter

AFTER = "planned_savings_rate"   # the row the investing rate follows, in the Saving group


def _investing_figure(c, month: str) -> HealthFigure:
    """The investing rate of the last completed month, next to the savings rate it comes out of: the share of what
    you kept that you moved into investments (3AN4). It has no limit; it is the Overview's old tile, moved here."""
    first, last = parse_month(month)
    flow = c.reporting.cash_flow(first, last)
    added = investment_period(c.db, c.accounts, c.assets, c.reporting, fmt_date(first), fmt_date(last))["net_money"]
    return HealthFigure("investing_rate", investing_rate(added, flow.net), "%", month, None, "minimum", None,
                        (("Net flow", flow.net), ("Money added", added)), "/investments")


def present(request, c, context: dict) -> dict:
    figure = _investing_figure(c, context["savings_month"])
    row = {"item": figure, "meter": meter(figure), "limit_words": limit_words(figure)}
    groups = []
    for group in context["groups"]:
        if group["title"] == "Saving":
            keys = [entry["item"].key for entry in group["items"]]
            at = keys.index(AFTER) + 1 if AFTER in keys else len(keys)
            group = {**group, "items": [*group["items"][:at], row, *group["items"][at:]]}
        groups.append(group)
    return {"figures": (*context["figures"], figure), "groups": groups}
