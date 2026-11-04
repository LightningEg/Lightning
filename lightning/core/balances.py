"""Exact running quantities in caller-supplied order.

Callers retain their policies: daily net movements for owned/cash availability,
transaction/line order for historical holdings. This helper never sorts, nets,
rounds or clamps a negative balance; validation and messages belong to callers.
"""
from collections.abc import Iterable, Iterator
from typing import NamedTuple


class BalanceStep(NamedTuple):
    day: str
    before: int
    after: int


def running_balances(movements: Iterable[tuple[str, int]], opening: int = 0) -> Iterator[BalanceStep]:
    """Walk integer-millionth quantities without buffering the history."""
    balance = opening
    for day, quantity in movements:
        before = balance
        balance += quantity
        yield BalanceStep(day, before, balance)
