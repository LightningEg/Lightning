"""NF-5B1: lots are derived from ledger lines; the average method reproduces the portfolio's old pool exactly."""
from decimal import Decimal as D

import pytest

from lightning.investments.lots import LotLine, build_lots


def buy(day, qty, cost):
    return LotLine(day, "BUY", "EXTERNAL", D(qty), D(cost))


def sell(day, qty, got):
    return LotLine(day, "SEL", "EXTERNAL", -D(qty), -D(got))


def test_average_lot_absorbs_every_buy_and_sells_at_the_average():
    book = build_lots([buy("2026-01-01", 10, 1000), buy("2026-02-01", 10, 1400), sell("2026-03-01", 5, 800)])
    assert [(lot.opened, lot.quantity, lot.cost) for lot in book.lots] == [("2026-01-01", D(15), D(1800))]
    (piece,) = book.disposals
    assert (piece.quantity, piece.cost, piece.proceeds, piece.gain) == (D(5), D(600), D(800), D(200))
    assert piece.days_held == 59
    assert (book.quantity, book.cost, book.realized, book.invested) == (D(15), D(1800), D(200), D(2400))


def test_a_sold_out_holding_keeps_its_gain_and_opens_a_new_lot_on_the_next_buy():
    book = build_lots([buy("2026-01-01", 10, 1000), sell("2026-02-01", 10, 1500), buy("2026-03-01", 4, 500)])
    assert [(lot.opened, lot.quantity, lot.cost) for lot in book.lots] == [("2026-03-01", D(4), D(500))]
    assert book.realized == D(500)


def test_return_of_capital_lowers_cost_and_the_excess_is_a_gain():
    roc = LotLine("2026-02-01", "SEL", "INTERNAL", D(0), D(-300))
    book = build_lots([buy("2026-01-01", 10, 1000), roc, LotLine("2026-03-01", "SEL", "INTERNAL", D(0), D(-900))])
    assert book.cost == D(0)
    assert book.quantity == D(10)
    assert [piece.gain for piece in book.disposals] == [D(0), D(200)]


def test_a_transfer_out_removes_cost_without_a_gain():
    book = build_lots([buy("2026-01-01", 10, 1000), LotLine("2026-02-01", "TRF", "INTERNAL", D(-4), D(-400))])
    assert (book.quantity, book.cost, book.realized) == (D(6), D(600), D(0))


def test_unknown_method_is_refused():
    with pytest.raises(ValueError):
        build_lots([], method="lifo")
