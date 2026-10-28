"""Link the sections (NF-7T): what a transaction touched, a counterparty's page, what depends on an account,
and a tag's totals.

Every method only reads what is already stored and asks the services that own each figure; nothing new is
stored and no money moves. A plan or reserve shown here stays a plan: it is linked, never posted.
"""
from __future__ import annotations

from datetime import date, timedelta

from lightning.core.dates import fmt_date, today
from lightning.core.errors import NotFoundError
from lightning.core.money import ZERO, from_e6
from lightning.rules import engine
from lightning.transactions.tags import normalize as normal_tag, tags_in

SHOWN = 4  # four names, then Other (guideline A11)


def _four_then_other(totals: dict[str, object], key: str = "money_out") -> list[dict]:
    """Rows largest first: four by name, then one Other row with the rest."""
    rows = sorted((row for row in totals.values() if row[key]), key=lambda row: -row[key])
    if len(rows) <= SHOWN + 1:
        return rows
    rest = rows[SHOWN:]
    other = {"name": "Other", "href": "", key: sum((row[key] for row in rest), ZERO), "count": len(rest)}
    return rows[:SHOWN] + [other]


class LinkedSections:
    def __init__(self, container):
        self.c = container
        self.db = container.db

    # ------------------------------------------------------------------ 7T1 a transaction
    def transaction(self, transaction_id: int) -> dict:
        """Everything one transaction touches, gathered once for its page (PC and phone)."""
        c = self.c
        txn = c.transactions.get(transaction_id)
        claims = self._claims_for(txn.id)
        rows = self.db.all(
            "SELECT r.batch_id,r.account_id,r.row_number,r.bank_reference,r.status,b.file_name,b.posted_at "
            "FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
            "WHERE r.transaction_id=? ORDER BY b.id,r.row_number", (txn.id,))
        sources = [dict(row) | {"sms": str(row["file_name"] or "").startswith("SMS ")} for row in rows]
        settled = [dict(row) | {"amount": from_e6(row["amount_e6"]),
                                "href": "/plan/loans" if row["kind"] == "LOAN" else "/plan/recurring"}
                   for row in self.db.all(
            "SELECT p.due_date,p.status,p.amount_e6,i.id AS item_id,i.name,i.kind "
            "FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
            "WHERE p.transaction_id=? UNION ALL "
            "SELECT x.due_date,'PAID',x.principal_e6+x.fee_e6,i.id,i.name,i.kind "
            "FROM loan_extra_payments x JOIN planned_items i ON i.id=x.planned_item_id "
            "WHERE x.transaction_id=? ORDER BY due_date", (txn.id, txn.id))]
        interest = [dict(row) | {"amount": from_e6(row["amount_e6"])} for row in self.db.all(
            "SELECT c.name,c.account_id,e.event_date,l.amount_e6 FROM cd_interest_receipt_links l "
            "JOIN cd_interest_receipt_events e ON e.id=l.event_id JOIN cd_certificates c ON c.id=e.certificate_id "
            "WHERE l.transaction_id=? ORDER BY e.event_date", (txn.id,))]
        counterparty = None
        counterparty_id = self.db.scalar("SELECT counterparty_id FROM transactions WHERE id=?", (txn.id,))
        if counterparty_id:
            party = c.counterparties.get(counterparty_id)
            if party:
                counterparty = {"id": party["id"], "name": party["name"]}
        owners = []
        for line in txn.lines:
            if line.owner_id and line.owner_id not in {o["id"] for o in owners}:
                party = c.counterparties.get(line.owner_id)
                if party:
                    owners.append({"id": party["id"], "name": party["name"]})
        touched = {
            "budget": self.budget_impacts(txn),
            "settled": settled,
            "reserves": [] if txn.is_void else c.reserves.links_for_transaction(txn.id),
            "claims": claims,
            "interest": interest,
            "sources": sources,
            "rule": None if txn.is_void else self._rule_for(txn, counterparty),
            "counterparty": counterparty,
            "owners": owners,
            "tags": tags_in(txn.notes),
        }
        touched["count"] = sum(len(touched[key]) for key in ("budget", "settled", "reserves", "claims",
                                                              "interest", "sources", "tags")) + bool(touched["rule"])
        return touched

    def budget_impacts(self, txn) -> list[dict]:
        """Each spending category's budget line this month, and what is left in it (or the plan that covers it)."""
        c = self.c
        impacts: list[dict] = []
        expense_lines = [line for line in txn.lines if line.category_id and line.effect.value == "OUTFLOW"]
        if not expense_lines or txn.is_void:
            return impacts
        budget_month = c.budgets.month_view(txn.date[:7])
        budget_by_id = {line.category_id: line for section in budget_month.sections for line in section.lines}
        seen: set[int] = set()
        for posting in expense_lines:
            if posting.category_id in seen:
                continue
            seen.add(posting.category_id)
            budget_line = budget_by_id.get(posting.category_id)
            if not budget_line:
                continue
            shown = budget_line
            if shown.remaining is None and shown.covered:
                parent = c.categories.get(posting.category_id).parent_id
                while parent:
                    ancestor = budget_by_id.get(parent)
                    if ancestor and ancestor.remaining is not None:
                        shown = ancestor
                        break
                    parent = c.categories.get(parent).parent_id
            impacts.append({"name": budget_line.name, "remaining": budget_line.remaining,
                            "covered_by": shown.name if shown is not budget_line else "",
                            "covered_remaining": shown.remaining if shown is not budget_line else None,
                            "month": txn.date[:7]})
        return impacts

    def _claims_for(self, transaction_id: int) -> list[dict]:
        """The reimbursement claim this expense opened, or the claims this receipt paid back."""
        service = getattr(self.c, "reimbursements", None)
        if service is None or not self.db.has_table("reimbursement_claims"):
            return []
        found = self.db.all(
            "SELECT id FROM reimbursement_claims WHERE expense_id=? UNION "
            "SELECT claim_id FROM reimbursement_receipts WHERE receipt_id=?", (transaction_id, transaction_id))
        if not found:
            return []
        wanted = {int(row["id"]) for row in found}
        return [claim | {"role": "expense" if claim["expense_id"] == transaction_id else "receipt"}
                for claim in service.list_claims() if claim["id"] in wanted]

    def _rule_for(self, txn, counterparty: dict | None) -> dict | None:
        """The rule that files this transaction in its category today, when one does. Which rule set a past
        category is not stored, so a rule shows only while it still gives the category the transaction has."""
        c = self.c
        categories = {line.category_id for line in txn.lines if line.category_id}
        cash = [line for line in txn.lines if c.assets.get_asset(line.asset_id).is_cash and line.quantity]
        if not categories or not cash or not c.rules.list():
            return None
        names = [txn.counterparty or "", counterparty["name"] if counterparty else ""]
        amount = sum((line.quantity for line in cash if line.owner_id is None), ZERO)
        outcome = c.rules.outcome(names, txn.notes, amount, cash[0].account_id)
        if not outcome.rule_id or outcome.category_id not in categories:
            return None
        rule = c.rules.get(outcome.rule_id)
        return {"id": rule.id, "when": c.rules.describe(rule)["when"]}

    # ------------------------------------------------------------------ 7T2 a counterparty
    def counterparty(self, counterparty_id: int, as_of: date | None = None, months: int = 12) -> dict:
        """One counterparty's page: money with them by month, plans, reserves, claims, money held, aliases, rules."""
        c = self.c
        party = c.counterparties.get(counterparty_id)
        if not party:
            raise NotFoundError("That counterparty no longer exists.")
        party = dict(party)
        day = as_of or today()
        first = day.replace(day=1)
        for _ in range(months - 1):
            first = (first - timedelta(days=1)).replace(day=1)
        by_month = c.reporting.counterparty_months(party["id"], first, day)
        money_out = sum((row["money_out"] for row in by_month), ZERO)
        money_in = sum((row["money_in"] for row in by_month), ZERO)
        months_seen = [row for row in by_month if row["money_out"] or row["money_in"]]
        # They are someone you pay, or someone who pays you (an employer): the page leads with the larger side.
        side = "money_in" if money_in > money_out else "money_out"
        latest, earlier = (by_month[-1], by_month[:-1]) if by_month else (None, [])
        active_earlier = [row for row in earlier if row[side]]
        usual = (sum((row[side] for row in active_earlier), ZERO) / len(active_earlier)) if active_earlier else None
        aliases = [dict(row) for row in c.counterparties.aliases_for(party["id"])]
        names = [party["name"], *(row["alias"] for row in aliases)]
        plans = []
        for item in c.planning.items():
            if item.counterparty_id != party["id"]:
                continue
            upcoming = next((p for p in c.planning.payments(item, fmt_date(day + timedelta(days=400)), day)
                             if p.status.value in ("DUE", "UPCOMING")), None)
            plans.append({"id": item.id, "name": item.name, "kind": item.kind.value, "kind_label": item.kind_label,
                          "amount": item.amount, "next_due": upcoming.due_date if upcoming else None,
                          "href": "/plan/loans" if item.kind.value == "LOAN" else "/plan/recurring"})
        reserves = [row for row in c.reserves.list_active() if row.get("counterparty_id") == party["id"]]
        claims = []
        if getattr(c, "reimbursements", None) is not None and self.db.has_table("reimbursement_claims"):
            claims = [claim for claim in c.reimbursements.list_claims() if claim.get("payer_id") == party["id"]]
        held = [row for row in c.money_from_others.by_owner(fmt_date(day)) if row["owner"] == party["name"]]
        rules = []
        for rule in c.rules.list():
            if any(cond.field == "counterparty" and engine.holds(cond, {"counterparty": names})
                   for cond in rule.conditions):
                described = c.rules.describe(rule)
                rules.append({"id": rule.id, "when": described["when"], "then": described["then"]})
        default = (c.categories.get(party["default_category_id"]).name
                   if party.get("default_category_id") else "")
        return {"party": party, "aliases": aliases, "default_category": default,
                "months": by_month, "months_seen": len(months_seen), "first_month": by_month[0]["month"] if by_month else "",
                "money_out": money_out, "money_in": money_in, "side": side,
                "total": money_in if side == "money_in" else money_out,
                "this_month": latest[side] if latest else ZERO, "usual_month": usual,
                "plans": plans, "reserves": reserves, "claims": claims,
                "owed": sum((claim["outstanding"] for claim in claims), ZERO),
                "held": held, "rules": rules}

    # ------------------------------------------------------------------ 7T3 an account
    def account(self, account_id: int, as_of: date | None = None) -> dict:
        """What depends on an account: plans it pays or receives, circles it funds, certificates paying into it,
        reserves held in it, and the first day scheduled payments take it below zero."""
        c = self.c
        account = c.accounts.get(account_id)
        day = as_of or today()
        plans = [{"id": item.id, "name": item.name, "kind": item.kind.value, "kind_label": item.kind_label,
                  "amount": item.amount, "href": "/plan/loans" if item.kind.value == "LOAN" else "/plan/recurring"}
                 for item in c.planning.items() if item.account_id == account.id]
        circles = [dict(row) | {"installment": from_e6(row["installment_e6"]), "payout": from_e6(row["payout_e6"])}
                   for row in self.db.all(
            "SELECT g.id,g.name,t.installment_e6,t.payout_e6,t.funding_account_id,t.payout_account_id "
            "FROM gameya_terms t JOIN accounts g ON g.id=t.account_id "
            "WHERE g.active=1 AND ? IN (t.funding_account_id,t.payout_account_id) ORDER BY g.name COLLATE NOCASE",
            (account.id,))]
        certificates = [dict(row) | {"principal": from_e6(row["principal_e6"])} for row in self.db.all(
            "SELECT c.id,c.name,c.account_id,c.maturity_date,c.principal_e6,c.payout_frequency FROM cd_certificates c "
            "JOIN transactions p ON p.id=c.purchase_transaction_id AND p.status='POSTED' "
            "WHERE c.destination_account_id=? AND NOT EXISTS (SELECT 1 FROM cd_redemptions r "
            "JOIN transactions t ON t.id=r.transaction_id WHERE r.certificate_id=c.id AND t.status='POSTED') "
            "ORDER BY c.maturity_date,c.id", (account.id,))]
        reserves = [row for row in c.reserves.list_active() if row.get("account_id") == account.id]
        shortfall = None
        if account.account_type.value in ("CASH", "BANK", "BROKERAGE") and account.active:
            dated = getattr(c.forecaster.forecast(day), "dated", None)
            shortfall = next((item for item in getattr(dated, "account_shortfalls", ()) or ()
                              if item.account_id == account.id), None)
        users = len(plans) + len(circles) + len(certificates) + len(reserves)
        return {"account": account, "plans": plans, "circles": circles, "certificates": certificates,
                "reserves": reserves, "shortfall": shortfall, "count": users}

    # ------------------------------------------------------------------ 7T4 a tag
    def tag(self, raw_tag: str) -> dict:
        """One tag's total across categories and accounts, and the reserve that shares its name or its payments."""
        c = self.c
        tag = normal_tag(raw_tag)
        if not tag:
            raise NotFoundError("That is not a tag.")
        ids = c.transactions.tag_transaction_ids(tag)
        rows = c.reporting.flows_by_account_and_category(ids) if ids else []
        money_in = sum((row["money_in"] for row in rows), ZERO)
        money_out = sum((row["money_out"] for row in rows), ZERO)
        by_category: dict[int, dict] = {}
        by_account: dict[int, dict] = {}
        for row in rows:
            category = by_category.setdefault(row["category_id"], {
                "name": c.categories.get(row["category_id"]).name, "money_out": ZERO, "money_in": ZERO,
                "href": f"/transactions?tag={tag}&category_id={row['category_id']}"})
            category["money_out"] += row["money_out"]
            category["money_in"] += row["money_in"]
            account = by_account.setdefault(row["account_id"], {
                "name": c.accounts.get(row["account_id"]).name, "money_out": ZERO, "money_in": ZERO,
                "href": f"/accounts/{row['account_id']}?tag={tag}"})
            account["money_out"] += row["money_out"]
            account["money_in"] += row["money_in"]
        dates = sorted(txn.date for txn in (c.transactions.get(i) for i in ids)) if ids else []
        reserves = []
        linked = {int(row["reserve_id"]): from_e6(row["amount_e6"]) for row in self.db.all(
            "SELECT l.reserve_id,SUM(l.amount_e6) AS amount_e6 FROM reserve_transaction_links l "
            "JOIN transactions t ON t.id=l.transaction_id AND t.status='POSTED' "
            f"WHERE l.transaction_id IN ({','.join('?' * len(ids))}) GROUP BY l.reserve_id", tuple(sorted(ids)))} if ids else {}
        for reserve in c.reserves.list_active() + c.reserves.list_completed():
            named = normal_tag(str(reserve["name"]).replace(" ", "-")) == tag or normal_tag(
                str(reserve["name"]).replace(" ", "")) == tag
            if named or reserve["id"] in linked:
                reserves.append(reserve | {"from_tag": linked.get(reserve["id"], ZERO),
                                           "left_after": reserve["target"] - money_out})
        return {"tag": tag, "count": len(ids), "money_in": money_in, "money_out": money_out,
                "net": money_in - money_out, "first": dates[0] if dates else "", "last": dates[-1] if dates else "",
                "categories": _four_then_other(by_category), "accounts": _four_then_other(by_account),
                "reserves": reserves}
