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


# ---- NF-5B2: FIFO across lots ----

def test_fifo_sale_cuts_across_lots_and_the_pieces_add_up():
    lines = [buy("2026-01-01", 10, 1000), buy("2026-02-01", 10, 1400), buy("2026-03-01", 10, 2000),
             sell("2026-04-01", 15, 3001)]
    book = build_lots(lines, method="fifo")
    first, second = book.disposals
    assert (first.lot_opened, first.quantity, first.cost) == ("2026-01-01", D(10), D(1000))
    assert (second.lot_opened, second.quantity, second.cost) == ("2026-02-01", D(5), D(700))
    assert first.proceeds + second.proceeds == D(3001)
    assert first.proceeds == D("2000.666667") and second.proceeds == D("1000.333333")
    assert sum(piece.cost for piece in book.disposals) == D(1700)
    assert [(lot.opened, lot.quantity, lot.cost) for lot in book.lots] == [
        ("2026-02-01", D(5), D(700)), ("2026-03-01", D(10), D(2000))]
    assert book.realized == D(3001) - D(1700)
    assert first.days_held == 90


def test_fifo_and_average_agree_when_there_is_one_buy():
    lines = [buy("2026-01-01", 10, 1000), sell("2026-02-01", 4, 700), sell("2026-03-01", 6, 1000)]
    a, f = build_lots(lines), build_lots(lines, method="fifo")
    assert (a.quantity, a.cost, a.realized) == (f.quantity, f.cost, f.realized)


def test_both_methods_account_for_every_pound_invested():
    lines = [buy("2026-01-01", 10, 1000), buy("2026-02-01", 10, 2000), sell("2026-03-01", 10, 2500)]
    for method in ("average", "fifo"):
        book = build_lots(lines, method=method)
        assert book.quantity == D(10)
        assert book.cost + sum(piece.cost for piece in book.disposals) == book.invested == D(3000)
    assert build_lots(lines).realized == D(1000) and build_lots(lines, method="fifo").realized == D(1500)


def test_fifo_return_of_capital_lowers_every_lot_in_proportion_to_its_cost():
    roc = LotLine("2026-03-01", "SEL", "INTERNAL", D(0), D(-300))
    book = build_lots([buy("2026-01-01", 10, 1000), buy("2026-02-01", 10, 2000), roc], method="fifo")
    assert [lot.cost for lot in book.lots] == [D(900), D(1800)]
    assert book.realized == D(0)
    over = build_lots([buy("2026-01-01", 10, 100), LotLine("2026-03-01", "SEL", "INTERNAL", D(0), D(-130))], method="fifo")
    assert over.cost == D(0) and over.realized == D(30)


def test_fifo_transfer_out_takes_the_oldest_cost_without_a_gain():
    lines = [buy("2026-01-01", 10, 1000), buy("2026-02-01", 10, 2000),
             LotLine("2026-03-01", "TRF", "INTERNAL", D(-12), D(-1400))]
    book = build_lots(lines, method="fifo")
    assert book.realized == D(0) and book.quantity == D(8)
    assert [(lot.quantity, lot.cost) for lot in book.lots] == [(D(8), D(1600))]


# ---- NF-5D: return and return per year, per purchase ----

def test_a_single_purchases_cagr_equals_its_xirr():
    from lightning.investments.xirr import xirr
    book = build_lots([buy("2025-01-01", 10, 1000)])
    lot = book.lots[0]
    rate = lot.cagr(D(130), "2026-01-01")
    assert lot.roi(D(130)) == D("0.3")
    assert abs(rate - xirr([("2025-01-01", D(-1000)), ("2026-01-01", D(1300))], "2026-01-01")) < D("0.000001")


def test_roi_and_cagr_are_none_without_a_day_or_a_cost():
    lot = build_lots([buy("2026-01-01", 10, 1000)]).lots[0]
    assert lot.roi(D(120)) == D("0.2") and lot.cagr(D(120), "2026-01-01") is None  # less than a day
    free = build_lots([LotLine("2026-01-01", "SPL", "INTERNAL", D(5), D(0))]).lots[0]
    assert free.roi(D(120)) is None and free.cagr(D(120), "2027-01-01") is None  # nothing was paid


def test_a_sold_piece_has_its_own_return():
    book = build_lots([buy("2025-01-01", 10, 1000), sell("2026-01-01", 10, 1300)])
    (piece,) = book.disposals
    assert piece.roi == D("0.3") and abs(piece.cagr - D("0.3")) < D("0.0001")
    roc = LotLine("2026-02-01", "SEL", "INTERNAL", D(0), D(-100))
    assert build_lots([buy("2025-01-01", 10, 1000), roc]).disposals[0].roi is None  # a return of capital sold nothing
