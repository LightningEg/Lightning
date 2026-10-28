"""Institutions: Egypt's banks, brokers and wallets (a bundled list) plus the ones a person adds.

`accounts.institution` stays plain text; the picker writes the institution's name. A logo is a bundled
file (never fetched while the app runs); without one, or for a custom institution, a monogram tile shows.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lightning.core.dates import now_iso
from lightning.core.errors import ValidationError
from lightning.database.connection import Database

CSV_FILE = Path(__file__).with_name("institutions.csv")
LOGO_URL = "/static/institutions/"
# What picking an institution of each kind says about the account (AccountType values). A kind not listed
# (a fintech, a post office) leaves the type as it is.
KIND_TO_ACCOUNT_TYPE = {"bank": "BANK", "broker": "BROKERAGE", "wallet": "CASH"}


@dataclass(frozen=True)
class Institution:
    name: str
    short_name: str = ""
    arabic_name: str = ""
    kind: str = ""
    website: str = ""
    logo: str = ""      # a file in ui/static/institutions, or empty (monogram)
    code: str = ""
    custom: bool = False
    markets: tuple[str, ...] = ()   # brokers only: the price packs they trade (lightning/market/packs.py ids)
    home_currency: str = ""         # brokers only: the currency the account is usually held in

    @property
    def label(self) -> str:
        return self.short_name or self.name

    @property
    def mono(self) -> str:
        return monogram(self.label)

    @property
    def logo_url(self) -> str:
        return LOGO_URL + self.logo if self.logo else ""


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.sub(r"[^\w&]+", " ", value, flags=re.UNICODE).split())


def monogram(name: str) -> str:
    """Up to two initials: 'CIB' -> 'CI', 'Banque Misr' -> 'BM', 'My Credit Union' -> 'MC'."""
    words = [w for w in re.split(r"[\s\-_/]+", str(name or "").strip()) if w[:1].isalnum()]
    if not words:
        return "?"
    letters = words[0][:2] if len(words) == 1 else words[0][0] + words[1][0]
    return letters.upper()


@lru_cache(maxsize=1)
def builtin() -> tuple[Institution, ...]:
    with CSV_FILE.open(encoding="utf-8", newline="") as handle:
        return tuple(Institution(code=row["code"], name=row["name"], short_name=row["short_name"],
                                 arabic_name=row["arabic_name"], kind=row["kind"], website=row["website"],
                                 logo=row["logo"], markets=tuple((row.get("markets") or "").split()),
                                 home_currency=(row.get("home_currency") or "").strip().upper())
                     for row in csv.DictReader(handle))


@lru_cache(maxsize=1)
def _builtin_index() -> dict[str, Institution]:
    index: dict[str, Institution] = {}
    for item in builtin():
        for text in (item.name, item.short_name, item.arabic_name, item.code):
            key = normalize(text)
            if key:
                index.setdefault(key, item)
    return index


def match_builtin(text: str) -> Institution | None:
    return _builtin_index().get(normalize(text))


# Accounts that need no institution (cash, gold, a flat, a gam'eya) show an icon of their kind instead of initials
# when no known institution names them (owner, 2026-10-28). Names are the Lucide icons drawn by macros.kind_icon.
KIND_ICON = {"CASH": "wallet", "CASH_AT_HAND": "banknote", "PHYSICAL_ASSET": "gem", "OTHER_ASSET": "box",
             "GAMEYA": "people"}


def tile(text: str, kind: str = "") -> dict[str, str]:
    """What a tile shows for an institution's written name: a bundled logo, else a known institution's
    monogram, else the icon of the account's kind (AccountType value, or CASH_AT_HAND), else a monogram."""
    found = match_builtin(text)
    if found is not None:
        return {"logo": found.logo_url, "mono": found.mono, "name": found.name, "icon": ""}
    return {"logo": "", "mono": monogram(text), "name": str(text or ""), "icon": KIND_ICON.get(str(kind or ""), "")}


class InstitutionService:
    def __init__(self, db: Database):
        self.db = db

    def custom(self) -> list[Institution]:
        return [Institution(name=row["name"], short_name=row["short_name"] or "", custom=True)
                for row in self.db.all("SELECT name, short_name FROM institutions ORDER BY name COLLATE NOCASE")]

    def list(self) -> list[Institution]:
        """Built-in and added institutions together, by name."""
        return sorted([*builtin(), *self.custom()], key=lambda item: item.name.casefold())

    def match(self, text: str) -> Institution | None:
        """The institution a free-text value means ('cib', 'Commercial International Bank'), or None."""
        found = match_builtin(text)
        if found is not None:
            return found
        key = normalize(text)
        return next((item for item in self.custom() if normalize(item.name) == key
                     or normalize(item.short_name) == key), None) if key else None

    def add(self, name: str) -> Institution:
        """Save an institution the list does not have; a repeat or a built-in match returns the existing one."""
        name = " ".join(str(name or "").split())
        if not name:
            raise ValidationError("Enter the institution's name.", "institution")
        if len(name) > 80:
            raise ValidationError("Keep the institution's name under 80 characters.", "institution")
        existing = self.match(name)
        if existing is not None:
            return existing
        self.db.execute("INSERT INTO institutions(name, short_name, normalized_name, created_at) VALUES(?,?,?,?)",
                        (name, None, normalize(name), now_iso()))
        return Institution(name=name, custom=True)

    def form_hints(self) -> dict[str, dict[str, str]]:
        """For the Add account form: each picker value -> the account type its kind implies and the short name
        used to suggest the account's name. The browser only applies this; the mapping lives here."""
        hints: dict[str, dict[str, str]] = {}
        for option in self.options():
            found = self.match(option["value"])
            if found is None:
                continue
            hints[option["value"]] = {"type": KIND_TO_ACCOUNT_TYPE.get(found.kind, ""), "short": found.label}
        return hints

    def used_before(self) -> list[str]:
        """Names already on this profile's accounts, most used first."""
        return [row["institution"] for row in self.db.all(
            "SELECT institution, COUNT(*) n FROM accounts WHERE trim(COALESCE(institution,''))<>'' "
            "GROUP BY institution ORDER BY n DESC, institution COLLATE NOCASE")]

    def options(self) -> list[dict]:
        """Picker rows: 'Used before' first, then everything else. Each carries its tile."""
        used = self.used_before()
        rows, seen = [], set()
        for text in used:
            found = self.match(text)
            value = found.name if found else text
            shown = tile(text) if found is None else {"logo": found.logo_url, "mono": found.mono}
            if normalize(value) in seen:
                continue
            seen.add(normalize(value))
            rows.append({"value": text, "label": found.label if found else text, "arabic": found.arabic_name if found else "",
                         "group": "Used before", **shown})
        for item in self.list():
            if normalize(item.name) in seen:
                continue
            rows.append({"value": item.name, "label": item.label, "arabic": item.arabic_name, "group": "Institutions",
                         "logo": item.logo_url, "mono": item.mono})
        return rows
