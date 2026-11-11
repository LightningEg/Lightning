"""English counts with their noun, so no screen builds a plural by hand."""
from __future__ import annotations


def counted(n, one: str, other: str) -> str:
    """counted(1, "day", "days") is "1 day"; counted(2, ...) is "2 days"; counted(0, ...) is "0 days"."""
    return f"{n} {one}" if n == 1 else f"{n} {other}"
