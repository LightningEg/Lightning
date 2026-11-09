"""Category marks for the phone's rows (IV-11D6, guideline C08.2): one 24px line icon per built-in category, stroke
1.75, drawn in the row chip's in or out colour. A category a person made has no mark here and keeps the arrow.
Paths are drawn for a 24 × 24 box; one path string each, as the row's arrow is."""
from __future__ import annotations

_CIRCLE = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"
_RECEIPT = "M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2zM9 8h6M9 12h6M9 16h3"
_LANDMARK = "M3 21h18M5 21V10M10 21V10M14 21V10M19 21V10M2 10l10-6 10 6z"
_CAR = "M5 16v-5l2-5h10l2 5v5M3 16h18v2H3zM7 18v2M17 18v2M5 11h14"
_OTHER = _CIRCLE + "M8 12h.01M12 12h.01M16 12h.01"
_UNKNOWN = _CIRCLE + "M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"
_GIFT = "M3 8h18v4H3zM5 12v9h14v-9M12 8v13M12 8C10 4 7 4 7 6s3 2 5 2M12 8c2-4 5-4 5-2s-3 2-5 2"

MARKS: dict[str, str] = {
    "EXP.PERSONAL.FOOD": "M5 11h14l-1.5 8.5a2 2 0 0 1-2 1.5h-7a2 2 0 0 1-2-1.5zM9 11l3-6 3 6",          # basket
    "EXP.PERSONAL.DINING": "M7 3v18M4 3v5a3 3 0 0 0 6 0V3M17 21V3c-2 0-3 2-3 6s1 4 3 4",              # fork and knife
    "EXP.PERSONAL.TRANSPORT": _CAR,
    "EXP.PERSONAL.HOUSING": "m3 10 9-7 9 7v11H3zM9 21v-6h6v6",                                        # house
    "EXP.PERSONAL.UTILITIES": "M13 2 4 14h7l-1 8 9-12h-7z",                                          # bolt
    "EXP.PERSONAL.HEALTH": "M20.8 8.6a5 5 0 0 0-8.8-3.2 5 5 0 0 0-8.8 3.2c0 5.4 8.8 11.4 8.8 11.4s8.8-6 8.8-11.4zM3 12h5l2-3 3 6 2-3h6",
    "EXP.PERSONAL.SHOPPING": "M6 7h12l1 14H5zM9 7a3 3 0 0 1 6 0",                                     # bag
    "EXP.PERSONAL.ENTERTAINMENT": "M3 5h18v4a3 3 0 0 0 0 6v4H3v-4a3 3 0 0 0 0-6zM14 5v2M14 11v2M14 17v2",  # ticket
    "EXP.PERSONAL.EDUCATION": "M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5M22 9v6",                   # cap
    "EXP.PERSONAL.GIFTS": _GIFT,
    "EXP.PERSONAL.GIFTS_RECEIVED": _GIFT,
    "EXP.PERSONAL.OTHER_INCOME": _CIRCLE + "M12 8v8M8 12h8",
    "EXP.PERSONAL.OTHER": _OTHER,
    "EXP.PERSONAL.FEES": _RECEIPT,
    "EXP.PERSONAL.TAXES": _LANDMARK,
    "EXP.WORK.SALARY": "M3 8h18v12H3zM8 8V5h8v3M3 13h18",                                            # briefcase
    "EXP.WORK.BONUS": "m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2-5.5-2.9-5.5 2.9 1-6.2L3 9.6l6.2-.9z",        # star
    "EXP.WORK.BUSINESS": "M4 5h16v11H4zM2 19h20",                                                      # laptop
    "EXP.WORK.TRANSPORT": _CAR,
    "EXP.WORK.SOFTWARE": "m8 8-5 4 5 4M16 8l5 4-5 4M14 5l-4 14",                                       # code
    "EXP.WORK.MEALS": "M4 8h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 10h2a2 2 0 0 1 0 4h-2M8 2v3M12 2v3",  # cup
    "EXP.WORK.OFFICE": "M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7",  # clip
    "EXP.WORK.OTHER": _OTHER,
    "EXP.SYSTEM.CUSTODY": "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M16 3a4 4 0 0 1 0 8M22 21v-1a6 6 0 0 0-4-5.7",
    "EXP.SYSTEM.LOANS": "M2 6h20v12H2zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 12h.01M18 12h.01",         # note
    "EXP.SYSTEM.TRANSFERS": "M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4",
    "EXP.SYSTEM.CAPITAL": "M4 17l6-6 4 4 6-7M14 8h6v6",
    "EXP.SYSTEM.ADJUSTMENT": "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4",            # sliders
    "EXP.SYSTEM.ZAKAT": "M12 20s-8-5-8-10.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15 12 20 12 20z",  # heart
    "EXP.UNACCOUNTED": _UNKNOWN,
    "INC.UNACCOUNTED": _UNKNOWN,
    "EXP.INVEST.INTEREST": "M19 5 5 19M7 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 15a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",  # percent
    "EXP.INVEST.DIVIDEND": "M12 3a9 9 0 1 0 9 9h-9zM15 3.5A9 9 0 0 1 20.5 9H15z",                      # pie
    "EXP.INVEST.FEES": _RECEIPT,
    "EXP.INVEST.TAX": _LANDMARK,
    "EXP.INVEST.OTHER": _OTHER,
}


def mark(code: str) -> str:
    """The category's mark, or "" for a category a person made (its row keeps the arrow)."""
    return MARKS.get(code or "", "")
