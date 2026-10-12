"""SQL for rules, their conditions and actions, and the past transactions a rule could refile."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.dates import now_iso
from lightning.core.memo import request_cached
from lightning.core.money import from_e6
from lightning.database.connection import Database

from .engine import Condition, Part, Rule


class RuleRepository:
    def __init__(self, db: Database):
        self.db = db

    @request_cached
    def rules(self, active_only: bool = True) -> list[Rule]:
        heads = self.db.all("SELECT * FROM rules" + (" WHERE active=1" if active_only else "") + " ORDER BY position, id")
        conditions: dict[int, list[Condition]] = {}
        for row in self.db.all("SELECT * FROM rule_conditions ORDER BY id"):
            conditions.setdefault(row["rule_id"], []).append(
                Condition(row["field"], row["op"], row["value"], row["value_to"]))
        actions: dict[int, list] = {}
        for row in self.db.all("SELECT * FROM rule_actions ORDER BY position, id"):
            actions.setdefault(row["rule_id"], []).append(dict(row))
        out = []
        for head in heads:
            acts = actions.get(head["id"], [])
            category = next((a["category_id"] for a in acts if a["action"] == "category"), None)
            out.append(Rule(
                id=head["id"], conditions=tuple(conditions.get(head["id"], [])), match_all=bool(head["match_all"]),
                category_id=category, tags=tuple(a["value"] for a in acts if a["action"] == "tag"),
                parts=tuple(Part(a["category_id"], a["method"], Decimal(a["value"])) for a in acts
                            if a["action"] == "split"),
                position=head["position"]))
        return out

    def save(self, rule_id: int | None, match_all: bool, conditions: list[Condition], category_id: int | None,
             tags: list[str], parts: list[Part]) -> int:
        now = now_iso()
        if rule_id is None:
            position = (self.db.scalar("SELECT MAX(position) FROM rules") or 0) + 1
            rule_id = int(self.db.execute(
                "INSERT INTO rules(match_all,position,active,created_at,updated_at) VALUES (?,?,1,?,?)",
                (int(match_all), position, now, now)).lastrowid)
        else:
            self.db.execute("UPDATE rules SET match_all=?,updated_at=? WHERE id=?", (int(match_all), now, rule_id))
            self.db.execute("DELETE FROM rule_conditions WHERE rule_id=?", (rule_id,))
            self.db.execute("DELETE FROM rule_actions WHERE rule_id=?", (rule_id,))
        for c in conditions:
            self.db.execute("INSERT INTO rule_conditions(rule_id,field,op,value,value_to) VALUES (?,?,?,?,?)",
                            (rule_id, c.field, c.op, c.value, c.value_to))
        position = 0
        if category_id:
            self.db.execute("INSERT INTO rule_actions(rule_id,action,category_id,position) VALUES (?,?,?,?)",
                            (rule_id, "category", category_id, position))
        for tag in tags:
            position += 1
            self.db.execute("INSERT INTO rule_actions(rule_id,action,value,position) VALUES (?,?,?,?)",
                            (rule_id, "tag", tag, position))
        for part in parts:
            position += 1
            self.db.execute(
                "INSERT INTO rule_actions(rule_id,action,category_id,value,method,position) VALUES (?,?,?,?,?,?)",
                (rule_id, "split", part.category_id, format(part.value, "f"), part.method, position))
        return rule_id

    def delete(self, rule_id: int) -> None:
        self.db.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    def single_category_history(self) -> list[dict]:
        """Posted, owned money-in and money-out transactions filed under one category: what a rule may refile."""
        rows = self.db.all(
            "SELECT t.id,t.date,t.type,t.counterparty,c.name canonical,t.notes,MIN(l.account_id) account_id,"
            "SUM(l.amount_e6) amount_e6,MIN(l.category_id) category_id,COUNT(DISTINCT l.category_id) categories "
            "FROM transactions t JOIN ledger_entries l ON l.transaction_id=t.id "
            "LEFT JOIN counterparties c ON c.id=t.counterparty_id "
            "WHERE t.status='POSTED' AND t.type IN ('IN','OUT') AND l.category_id IS NOT NULL AND l.owner_id IS NULL "
            "GROUP BY t.id HAVING categories=1 ORDER BY t.date DESC, t.id DESC")
        return [dict(row) | {"amount": from_e6(row["amount_e6"])} for row in rows]

    def filed_by_name(self) -> list[dict]:
        """How often each counterparty name was filed under each category: posted, owned money-in and money-out
        transactions with one non-system category. One aggregate query, names compared without case; each row
        also carries the category set on the counterparty of that name (``default_category_id``)."""
        rows = self.db.all(
            "SELECT f.name, f.category_id, f.n, (SELECT d.default_category_id FROM counterparties d"
            " WHERE d.name=f.name COLLATE NOCASE LIMIT 1) default_category_id FROM ("
            " SELECT MAX(name) name, category_id, COUNT(*) n FROM ("
            "  SELECT t.id, COALESCE(c.name, NULLIF(TRIM(t.counterparty), '')) name, MIN(l.category_id) category_id"
            "  FROM transactions t JOIN ledger_entries l ON l.transaction_id=t.id"
            "  JOIN categories k ON k.id=l.category_id AND k.is_system=0"
            "  LEFT JOIN counterparties c ON c.id=t.counterparty_id"
            "  WHERE t.status='POSTED' AND t.type IN ('IN','OUT') AND l.category_id IS NOT NULL"
            "  AND NOT EXISTS (SELECT 1 FROM ledger_entries o WHERE o.transaction_id=t.id AND o.owner_id IS NOT NULL)"
            "  GROUP BY t.id HAVING COUNT(DISTINCT l.category_id)=1)"
            " WHERE name IS NOT NULL GROUP BY name COLLATE NOCASE, category_id) f")
        return [dict(row) for row in rows]
