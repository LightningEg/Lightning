"""IT-12AE4 (ledger): the figures the register, import review and Settings show are worked out by their owners."""
from decimal import Decimal
from types import SimpleNamespace

from lightning.bank_import_rows import staged_amount, staged_total
from lightning.planning.position import ClassValue, class_group_totals
from lightning.reporting import account_figures
from lightning.transactions.figures import cash_amount, day_nets, group_value_updates

D = Decimal


def test_account_figures():
    class Reporting:
        values = {1: D("100.50"), 2: D("40")}
        owned = {1: D("80.50"), 2: D("40")}

        def account_value(self, account_id, as_of):
            return self.values[account_id]

        def owned_account_value(self, account_id, as_of):
            return self.owned[account_id]

    assert account_figures.combined_value(Reporting(), [1, 2], "2026-01-01") == (D("140.50"), D("120.50"), D("20.00"))
    rows = [{"total": D(n)} for n in ("50", "0", "20", "10", "10", "5", "5")]
    mix = account_figures.class_mix(rows)
    assert mix["total"] == D("100") and len(mix["parts"]) == 6 and mix["other"] == D("10")
    assert account_figures.class_mix(rows[:3])["other"] is None
    assert account_figures.share_of(D("25"), D("200")) == D("12.5")
    assert account_figures.in_own_currency(D("500"), SimpleNamespace(rate=D("50"))) == D("10")
    assert account_figures.in_own_currency(D("500"), None) is None
    assert account_figures.pocket_invested(D("500"), D("50"), D("4")) == D("6")
    assert account_figures.pocket_invested(D("500"), None, D("4")) is None
    assert account_figures.search_net((D("30"), D("12"))) == D("18")
    assert account_figures.search_net(None) is None
    figures = account_figures.other_asset_figures(D("1200"), D("1000"), [{"value": D("900")}, {"value": D("1100")}])
    assert figures == {"change": D("200"), "change_pct": D("20"), "history_changes": [None, D("200")]}
    assert account_figures.other_asset_figures(D("1"), None, [])["change_pct"] is None
    assert account_figures.equity(D("1000"), D("300")) == D("700")


def test_transaction_figures():
    assert cash_amount([SimpleNamespace(quantity=D("-30")), SimpleNamespace(quantity=D("-12.50"))]) == D("42.50")
    row = lambda day, kind, amount, base=None: SimpleNamespace(date=day, type=kind, amount=D(amount), amount_base=base, txn_id=1)  # noqa: E731
    rows = [row("d1", "IN", "100"), row("d1", "OUT", "-30"), row("d2", "OUT", "-5"), row("d3", "TRF", "10"), row("d3", "OUT", "-1")]
    assert day_nets(rows) == {"d1": D("70"), "d3": D("-1")}
    assert day_nets(rows, show_account=True) == {"d1": D("70")}
    grouped = group_value_updates([row("d1", "VAL", "5"), row("d1", "VAL", "-2"), row("d1", "IN", "1")])
    assert [(g.type, g.amount) for g in grouped] == [("VALS", D("3")), ("IN", D("1"))] and grouped[0].count == 2


def test_import_and_position_figures():
    assert staged_amount({"Amount": "1,250.50"}) == D("1250.50")
    assert staged_amount({"Amount": "−20"}) == D("-20") and staged_amount({"Amount": "x"}) == D("0")
    assert staged_total([{"Amount": "10"}, {"Amount": "-2.5"}, {}]) == D("7.5")
    cls = ClassValue(id=1, code="EQ", name="Stocks", value=D("1000"), factor=D("90"))
    assert class_group_totals([cls, None]) == (D("1000"), D("900"))
