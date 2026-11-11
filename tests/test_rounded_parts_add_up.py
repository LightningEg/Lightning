"""BT-2E part 7: parts shown in whole units add up to the total shown (largest remainder)."""
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

from lightning.core.money import round_to_total
from lightning.planning.domain import WhatYouOwe
from lightning.planning.position import ClassValue, Position
from lightning.ui import visuals


def test_round_to_total_keeps_sum_of_the_rounded_total():
    parts = [D("10.4"), D("10.4"), D("10.4"), D("0.4")]  # plain rounding: 10+10+10+0 = 30 against 32 (31.6)
    out = round_to_total(parts)
    assert sum(out) == D(32) and all(abs(o - p) < 1 for o, p in zip(out, parts))
    assert sum(round_to_total([D("1.5"), D("1.5")], D(3))) == 3


def _position(free, kept, class_values):
    classes = tuple(ClassValue(i, f"C{i}", f"C{i}", v, D(100)) for i, v in enumerate(class_values, 1))
    return Position(
        as_of="2026-01-31", what_you_own=D(0), held_for_others=D(0), unvalued=(), bank_and_wallet_cash=free + kept,
        brokerage_cash=D(0), classes=classes, reserves=D(0), reserve_rows=(), owe=WhatYouOwe(D(0), D(0)),
        kept_apart=kept)


def test_if_you_sold_today_parts_add_up_to_the_shown_total():
    p = _position(D("100.4"), D("0.4"), [D("10.4"), D("10.4"), D("10.4")])
    plain = [round(x) for x in (p.free_cash, p.kept_apart, p.holdings_after_sale)]
    assert sum(plain) != round(p.if_you_sold_today)  # the bug: 100 + 0 + 31 against 132
    s = p.sale_parts
    assert s["free_cash"] + s["kept_apart"] + s["holdings_after_sale"] == s["total"] == D(132)
    assert sum(s["classes"].values()) == s["holdings_after_sale"]


def test_where_money_in_went_parts_add_up_to_the_shown_total(monkeypatch):
    monkeypatch.setattr(visuals, "money_in_groups", lambda c, a, b: [
        {"label": n, "value": D("100.4"), "href": ""} for n in "abc"])
    reporting = SimpleNamespace(spending_by_category=lambda a, b, depth=1: [
        SimpleNamespace(code=n, label=n, value=D("100.4")) for n in "xyz"])
    c = SimpleNamespace(reporting=reporting, categories=SimpleNamespace(get_by_code=lambda code: SimpleNamespace(id=1)))
    from lightning.reporting.service import CashFlow
    flow = CashFlow("2026-01-01", "2026-01-31", D("301.2"), D("301.2"), D(0), D("301.2"), D("301.2"), D(0), D(0))
    out = visuals.money_sankey(c, date(2026, 1, 1), date(2026, 1, 31), flow)
    sources = [n["value"] for n in out["sources"]]
    targets = [n["value"] for n in out["targets"]]
    assert sum(sources) == sum(targets) == out["hub"]["value"] == D(301)
    assert sorted(sources) == [D(100), D(100), D(101)]
