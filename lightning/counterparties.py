"""Canonical counterparty identity and user-confirmed spelling aliases."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from lightning.core.dates import now_iso
from lightning.core.memo import request_cached
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.database.connection import Database

MAX_ALIASES_PER_COUNTERPARTY = 20
KINDS = ("PERSON", "BUSINESS")


def normalize(value: str) -> str:
    """Normalize harmless spelling differences without erasing meaningful words."""
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


class CounterpartyService:
    def __init__(self, db: Database):
        self.db = db

    @request_cached
    def resolve(self, value: str):
        key = normalize(value)
        if not key:
            return None
        return self.db.one(
            "SELECT c.* FROM counterparties c WHERE c.normalized_name=? "
            "UNION SELECT c.* FROM counterparties c JOIN counterparty_aliases a "
            "ON a.counterparty_id=c.id WHERE a.normalized_alias=? LIMIT 1", (key, key)
        )

    def resolve_many(self, values) -> dict:
        """{value: row or None} for many names at once, in one read (backend roadmap B4): a saved name wins over
        an alias, as in `resolve`."""
        keys = {value: normalize(value) for value in values}
        found: dict = {}
        if any(keys.values()):
            by_alias = {row["_key"]: row for row in self.db.all(
                "SELECT c.*, a.normalized_alias AS _key FROM counterparties c "
                "JOIN counterparty_aliases a ON a.counterparty_id=c.id")}
            by_name = {row["normalized_name"]: row for row in self.db.all("SELECT c.* FROM counterparties c")}
            found = {key: by_name.get(key) or by_alias.get(key) for key in set(keys.values()) if key}
        return {value: found.get(key) if key else None for value, key in keys.items()}

    @request_cached
    def get(self, counterparty_id: int):
        return self.db.one("SELECT * FROM counterparties WHERE id=?", (counterparty_id,))

    def aliases_for(self, counterparty_id: int):
        return self.db.all(
            "SELECT id,alias FROM counterparty_aliases WHERE counterparty_id=? ORDER BY alias COLLATE NOCASE",
            (counterparty_id,),
        )

    def search_names(self):
        """Canonical names and confirmed aliases offered by smart-search pickers."""
        rows = self.db.all(
            "SELECT name AS value FROM counterparties WHERE active=1 "
            "UNION SELECT a.alias AS value FROM counterparty_aliases a "
            "JOIN counterparties c ON c.id=a.counterparty_id WHERE c.active=1 "
            "ORDER BY value COLLATE NOCASE"
        )
        return [row["value"] for row in rows]

    def list_active(self):
        """Counterparties available in picker controls, in display order."""
        return self.db.all("SELECT id,name,default_category_id FROM counterparties WHERE active=1 ORDER BY name COLLATE NOCASE")

    def list_people(self):
        """People only: the names owner pickers ("Held for") offer. Shops and employers stay out."""
        return self.db.all(
            "SELECT id,name,default_category_id FROM counterparties WHERE active=1 AND kind='PERSON' "
            "ORDER BY name COLLATE NOCASE"
        )

    list_owners = list_people

    def set_kind(self, counterparty_id: int, kind: str | None) -> None:
        """Mark a name as a PERSON or a BUSINESS (None clears the mark)."""
        kind = (kind or "").strip().upper() or None
        if kind is not None and kind not in KINDS:
            raise ValidationError("Choose person or business.", "kind")
        cur = self.db.execute("UPDATE counterparties SET kind=?,updated_at=? WHERE id=?",
                              (kind, now_iso(), counterparty_id))
        if cur.rowcount != 1:
            raise NotFoundError("Counterparty not found.")

    def ensure_person(self, name: str) -> int:
        """The id of the person this owner name means: a saved name is used (and counts as a person if it was
        not yet marked), a new name is saved as a person."""
        found = self.resolve(name)
        if found:
            if found["kind"] is None:
                self.db.execute("UPDATE counterparties SET kind='PERSON',updated_at=? WHERE id=?",
                                (now_iso(), found["id"]))
            return int(found["id"])
        return self.create(name, kind="PERSON")

    def list_all(self):
        """All saved Counterparties for management, including archived entries."""
        return self.db.all("SELECT id,name,default_category_id,active,kind FROM counterparties ORDER BY name COLLATE NOCASE")

    def rename(self, counterparty_id: int, name: str, default_category_id: int | None = None) -> None:
        name = " ".join((name or "").split())
        key = normalize(name)
        if not key:
            raise ValidationError("Enter a counterparty name.", "counterparty")
        current = self.get(counterparty_id)
        if not current:
            raise NotFoundError("Counterparty not found.")
        collision = self.resolve(name)
        if collision and int(collision["id"]) != counterparty_id:
            raise ConflictError(f"{name} already matches another saved counterparty.", "counterparty")
        old_name = current["name"]
        with self.db.transaction():
            # Once an alias becomes the canonical name, keep just the canonical entry.
            self.db.execute("DELETE FROM counterparty_aliases WHERE counterparty_id=? AND normalized_alias=?",
                            (counterparty_id, key))
            self.db.execute("UPDATE counterparties SET name=?,normalized_name=?,default_category_id=?,updated_at=? WHERE id=?",
                            (name, key, default_category_id, now_iso(), counterparty_id))
            self.db.execute("UPDATE transactions SET counterparty=? WHERE counterparty_id=?",
                            (name, counterparty_id))
            self._link_historical(counterparty_id, name)
            if normalize(old_name) != key:
                self.add_alias(counterparty_id, old_name)

    def set_active(self, counterparty_id: int, active: bool) -> None:
        cur = self.db.execute("UPDATE counterparties SET active=?,updated_at=? WHERE id=?",
                              (int(active), now_iso(), counterparty_id))
        if cur.rowcount != 1:
            raise NotFoundError("Counterparty not found.")

    def delete_or_archive(self, counterparty_id: int) -> bool:
        """Delete an unused record; archive one referenced by transaction history. Returns archived."""
        if not self.get(counterparty_id):
            raise NotFoundError("Counterparty not found.")
        # Any record that refers to it (history, owners, plans, reserves, claims...) keeps it archived; its
        # own spellings go with it.
        used = self.db.referenced("counterparties", counterparty_id, ignore=("counterparty_aliases",))
        if used:
            self.set_active(counterparty_id, False)
            return True
        with self.db.transaction():
            self.db.execute("DELETE FROM counterparty_aliases WHERE counterparty_id=?", (counterparty_id,))
            self.db.execute("DELETE FROM counterparties WHERE id=?", (counterparty_id,))
        return False

    def suggestions(self, value: str, limit: int = 3) -> list[tuple[str, float]]:
        """Rank likely matches for a human to confirm; suggestions are never auto-merged."""
        key = normalize(value)
        if len(key) < 3 or self.resolve(value):
            return []
        rows = self.db.all(
            "SELECT name, normalized_name AS normalized FROM counterparties WHERE active=1 "
            "UNION SELECT c.name, a.normalized_alias FROM counterparty_aliases a "
            "JOIN counterparties c ON c.id=a.counterparty_id WHERE c.active=1"
        )
        best: dict[str, float] = {}
        for row in rows:
            ratio = SequenceMatcher(None, key, row["normalized"]).ratio()
            if ratio >= 0.68:
                best[row["name"]] = max(best.get(row["name"], 0), ratio)
        return sorted(best.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit]

    def create(self, name: str, default_category_id: int | None = None, alias: str | None = None,
               kind: str | None = None) -> int:
        name = " ".join((name or "").split())
        key = normalize(name)
        if not key:
            raise ValidationError("Enter a counterparty name.", "counterparty")
        if kind is not None and kind not in KINDS:
            raise ValidationError("Choose person or business.", "kind")
        if self.resolve(name):
            raise ConflictError(f"{name} already matches a saved counterparty. Choose it instead.", "counterparty")
        now = now_iso()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO counterparties(name,normalized_name,default_category_id,created_at,updated_at,kind) "
                "VALUES (?,?,?,?,?,?)", (name, key, default_category_id, now, now, kind)
            )
            counterparty_id = cur.lastrowid
            self._link_historical(counterparty_id, name)
            if alias:
                if normalize(alias) != key:
                    self.add_alias(counterparty_id, alias)
                else:
                    self._link_historical(counterparty_id, alias)
        return counterparty_id

    def add_alias(self, counterparty_id: int, alias: str) -> None:
        alias = " ".join((alias or "").split())
        key = normalize(alias)
        if not key:
            raise ValidationError("Enter the spelling to remember.", "alias")
        if not self.get(counterparty_id):
            raise NotFoundError("Counterparty not found.")
        if self.resolve(alias):
            existing = self.resolve(alias)
            if existing["id"] == counterparty_id:
                return
            raise ConflictError(f"“{alias}” is already linked to {existing['name']}.", "alias")
        with self.db.transaction():
            alias_count = self.db.scalar(
                "SELECT COUNT(*) FROM counterparty_aliases WHERE counterparty_id=?", (counterparty_id,)
            )
            if int(alias_count or 0) >= MAX_ALIASES_PER_COUNTERPARTY:
                raise ValidationError(f"A counterparty can have at most {MAX_ALIASES_PER_COUNTERPARTY} aliases.", "alias")
            self.db.execute(
                "INSERT INTO counterparty_aliases(counterparty_id,alias,normalized_alias,created_at) "
                "VALUES (?,?,?,?)", (counterparty_id, alias, key, now_iso())
            )
            self._link_historical(counterparty_id, alias)

    def rename_alias(self, counterparty_id: int, alias_id: int, alias: str) -> None:
        alias = " ".join((alias or "").split())
        key = normalize(alias)
        if not key:
            raise ValidationError("Enter the spelling to remember.", "alias")
        row = self.db.one(
            "SELECT id FROM counterparty_aliases WHERE id=? AND counterparty_id=?", (alias_id, counterparty_id)
        )
        if not row:
            raise NotFoundError("Alias not found.")
        existing = self.resolve(alias)
        if existing and existing["id"] != counterparty_id:
            raise ConflictError(f"“{alias}” is already linked to {existing['name']}.", "alias")
        duplicate = self.db.one(
            "SELECT id FROM counterparty_aliases WHERE normalized_alias=? AND id<>?", (key, alias_id)
        )
        if duplicate or (existing and normalize(existing["name"]) == key):
            raise ConflictError(f"“{alias}” is already saved for this counterparty.", "alias")
        self.db.execute(
            "UPDATE counterparty_aliases SET alias=?,normalized_alias=? WHERE id=? AND counterparty_id=?",
            (alias, key, alias_id, counterparty_id),
        )
        self._link_historical(counterparty_id, alias)

    def remove_alias(self, counterparty_id: int, alias_id: int) -> None:
        cur = self.db.execute(
            "DELETE FROM counterparty_aliases WHERE id=? AND counterparty_id=?", (alias_id, counterparty_id)
        )
        if cur.rowcount != 1:
            raise NotFoundError("Alias not found.")

    def _link_historical(self, counterparty_id: int, alias: str) -> None:
        # Each distinct unlinked spelling is normalised once, not each transaction (9I): thousands of buys and
        # sells share a handful of names.
        key = normalize(alias)
        target = self.get(counterparty_id)
        for row in self.db.all(
                "SELECT DISTINCT counterparty FROM transactions WHERE counterparty_id IS NULL AND counterparty<>''"):
            if normalize(row["counterparty"]) == key:
                self.db.execute("UPDATE transactions SET counterparty_id=?,counterparty=? "
                                "WHERE counterparty_id IS NULL AND counterparty=?",
                                (counterparty_id, target["name"], row["counterparty"]))

    def set_default_category(self, counterparty_id: int, category_id: int | None) -> None:
        cur = self.db.execute(
            "UPDATE counterparties SET default_category_id=?,updated_at=? WHERE id=?",
            (category_id, now_iso(), counterparty_id)
        )
        if cur.rowcount != 1:
            raise NotFoundError("Counterparty not found.")
