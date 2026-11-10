"""English counts with the right noun: the one place a plural is decided (IV-3BC)."""
from __future__ import annotations

from decimal import Decimal


def counted(n: int | Decimal, one: str, other: str | None = None) -> str:
    """counted(1, "day", "days") is "1 day"; counted(2, "day", "days") is "2 days"; `other` defaults to one + "s"."""
    return f"{n} {one}" if n == 1 else f"{n} {other if other is not None else one + 's'}"
