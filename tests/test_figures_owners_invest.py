"""IT-12AE4: the investment and account figures the screens read, worked out by their owners."""
from dataclasses import dataclass
from decimal import Decimal as D
from types import SimpleNamespace

from lightning.accounts import totals
from lightning.deposits.domain import GameyaFrequency, GameyaTerms
from lightning.investments import owned
from lightning.investments.domain import Portfolio, Position


def _position(asset_id=1, quantity=D(10), cost=D(100), value=D(150), realized=D(0), dividends=D(0), **extra):
    fields = dict(owned_quantity=quantity, owned_cost_basis=cost, owned_realized=D(0))
    fields.update(extra)
    return Position(1, "Broker", asset_id, f"STK:A{asset_id}", f"Asset {asset_id}", "Stocks", "Equity", "share",
                    quantity, cost, realized, dividends, None, None, "", value, **fields)


def test_owned_only_keeps_your_share_of_the_value():
    h = _position(quantity=D(10), cost=D(100), value=D(150), owned_quantity=D(4), owned_cost_basis=D(40),
                  has_other_owners=True, xirr=D("0.1"))
    mine = h.owned_only()
    assert (mine.quantity, mine.cost_basis, mine.value, mine.xirr) == (D(4), D(40), D(60), None)
    assert mine.gain_pct == D(50) and mine.value_plus_paid == D(60)
    assert _position(xirr=D("0.125")).xirr_pct == D("12.5")
    earlier = _position(realized=D(0))
    later = _position(realized=D(7), dividends=D(3))
    assert later.realized_since(earlier) == D(7) and later.dividends_since(None) == D(3)


class _Valuer:
    def value_of(self, asset_id, units, day):
        return SimpleNamespace(value=D(15) * units)


class _Others:
    def investment_positions(self, day):
        return [{"account_id": 1, "asset_id": 1, "units": D(2)}]


def test_owned_portfolio_leaves_out_what_you_hold_for_others():
    today = Portfolio("2026-02-01", [_position(owned_quantity=D(8), owned_cost_basis=D(80))])
    before = Portfolio("2026-01-31", [_position(value=D(120), owned_quantity=D(8), owned_cost_basis=D(80))])
    prefs = {1: {"risk_level": "High risk", "investment_horizon": None, "is_cash": False}}
    own = owned.owned_portfolio(_Valuer(), _Others(), prefs, today, before, "2026-02-01", "2026-01-31", D(5))
    assert own.owned_value == D(120) and own.owned_cost == D(80) and own.owned_unrealized == D(40)
    assert own.starting_owned_value == D(90) and own.period_value_change == D(30)
    assert own.own_units_by_holding == {"1:1": D(8)} and own.buckets == {"High risk": D(120)}
    assert own.period_distributions == D(5) and own.max_class_result == D(30)


def test_small_investment_figures():
    assert owned.target_total({"A": D(60), "B": D(30)}) == D(90)
    assert owned.target_room({"A": D(60), "B": D(30)}, "A") == (D(30), D(70))
    assert owned.in_lens(D(100), D(50)) == D(2) and owned.in_lens(None, D(50)) is None
    assert owned.six_month_change(D(150), D(100), D(20)) == D(30)
    assert owned.by_class([{"asset_id": 1, "account_id": 1, "amount": D(5)},
                           {"asset_id": 2, "account_id": 1, "amount": D(9)}], {(1, 1): "Stocks"}) == {"Stocks": D(5)}
    assert owned.suggested_total([{"suggested": D(3)}, {"suggested": D(4)}]) == D(7)
    assert owned.planner_row("A", D(50), D(100), D(50), D(100)) == {"weight": D(50), "after": D(50)}
    assert owned.per_share_total(D("0.333"), D(10)) == D("3.33")
    assert owned.unit_price(D(100), D(4)) == D(25) and owned.exact_from_e6(1_500_000) == D("1.5")
    values, total = owned.owned_by_bucket(Portfolio("d", [_position()]), {(1, 1): D(5)}, {})
    assert values == {"Medium risk": D(75)} and total == D(75)  # no saved level read: Medium risk
    row = SimpleNamespace(value=D(9))
    assert owned.values_by_bucket([row, SimpleNamespace(value=None)], lambda r: "X") == {"X": D(9)}
    assert len(owned.dividends_since(Portfolio("d", [_position(owned_dividends=D(4))]), Portfolio("d"))) == 1


@dataclass
class _Account:
    id: int
    parent_id: int | None = None
    active: bool = True
    kind: str = "Cash"


def test_account_totals_roll_pockets_into_their_broker():
    rows = [(_Account(1), D(100), D(90), 2), (_Account(2, parent_id=1), D(50), D(50), 1), (_Account(3), None, None, 0)]
    rolled = totals.roll_up_pockets(rows)
    assert [(r[0].id, r[1], r[2], r[3]) for r in rolled] == [(1, D(150), D(140), 3), (3, None, None, 0)]
    assert totals.active_total(rolled[:1]) == D(150)
    groups = totals.group_totals(rolled, lambda account: account.kind)
    assert groups["Cash"]["balance"] is None and len(groups["Cash"]["rows"]) == 2
    assert totals.held_for_others(D(10), D(7)) == D(3)
    assert totals.with_investments(D(10), D(5), False) == D(15) and totals.with_investments(None, D(5), False) is None


def test_gameya_pot_is_every_members_instalment():
    terms = GameyaTerms(1, "Aunt", 10, D(1000), list(GameyaFrequency)[0], "2026-01-01", 3, D(10000), D(0), 2, 2)
    assert terms.pot == D(10000)


def test_a_sales_list_without_amounts_opens_on_the_phone(tmp_path, monkeypatch):
    """The crawl found /investments/report-detail?kind=sales failing on the phone: a sale has no base amount and the
    template divided it anyway. The route now hands every row its amount (None when there is none)."""
    from lightning.bootstrap import build
    from lightning.samples import load_mohab_2026
    from tests.test_figures_agree import _client
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "sales.db")
    load_mohab_2026(c)
    try:
        for phone in (False, True):
            for kind in ("sales", "flows", "dividends", "result", "holdings"):
                page = _client(c, phone).get(f"/investments/report-detail?from=2026-05-01&to=2026-09-30&kind={kind}")
                assert page.status_code == 200, kind
    finally:
        c.db.close()
