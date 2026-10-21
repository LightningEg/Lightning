"""Human-readable codes for master data.

- Accounts:           INSTITUTION-TYPE-CURRENCY   e.g. CIB-CUR-EGP
- Financial assets:   CLASS:SYMBOL                e.g. STK:COMI, CASH:EGP
- Asset classes and categories use dotted paths    e.g. FUND.GOLD, EXP.WORK.SOFTWARE

Codes are labels: relationships use internal integer ids, so codes can be renamed safely.
"""

from __future__ import annotations

import re
import unicodedata

from .errors import ValidationError

ACCOUNT_CODE_RE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")
ASSET_CODE_RE = re.compile(r"^[A-Z]+:[A-Z0-9]+([-_.][A-Z0-9]+)*$")
PATH_CODE_RE = re.compile(r"^[A-Z0-9_]+(\.[A-Z0-9_]+)*$")
SEGMENT_RE = re.compile(r"^[A-Z0-9_]+$")


def slug(text: str, max_len: int = 16, sep: str = "-") -> str:
    """'Carrefour Maadi' -> 'CARREFOUR-MAADI'. Non-latin text falls back to empty."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    parts = [p.upper() for p in re.findall(r"[A-Za-z0-9]+", normalized)]
    result = ""
    for part in parts:  # keep whole words only: "Cash at hand" -> "CASH-AT-HAND", never "CASH-AT-HA"
        candidate = f"{result}{sep}{part}" if result else part
        if len(candidate) > max_len:
            break
        result = candidate
    return result or (parts[0][:max_len] if parts else "")


def normalize(code: str) -> str:
    return re.sub(r"\s+", "-", (code or "").strip().upper())


def validate_account_code(code: str) -> str:
    code = normalize(code)
    if not ACCOUNT_CODE_RE.match(code) or len(code) > 40:
        raise ValidationError(
            "Account codes use capital letters, digits and dashes, e.g. CIB-CUR-EGP.", "code"
        )
    return code


def validate_asset_code(code: str) -> str:
    code = normalize(code)
    if not ASSET_CODE_RE.match(code) or len(code) > 40:
        raise ValidationError("Asset codes look like CLASS:SYMBOL, e.g. STK:COMI.", "code")
    return code


def validate_path_code(code: str) -> str:
    code = normalize(code).replace("-", "_")
    if not PATH_CODE_RE.match(code) or len(code) > 80:
        raise ValidationError(
            "Codes use capital letters, digits and underscores, joined by dots, e.g. EXP.WORK.SOFTWARE.",
            "code",
        )
    return code


def path_segment(text: str) -> str:
    seg = slug(text, max_len=24, sep="_")
    if not seg:
        raise ValidationError(
            "Could not build a code from this name — please type a code (latin letters).", "code"
        )
    return seg
