"""Optional cash funding. Actual cash, spending room and reserves remain distinct."""
from __future__ import annotations

from hashlib import sha256
from decimal import ROUND_DOWN, Decimal
import json

from lightning.accounts.domain import AccountType
from lightning.core.dates import month_of, now_iso, parse_month, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, check_places, from_e6, to_decimal, to_e6
from lightning.database.portable_ids import portable_ids
from lightning.planning.salary_day import review_identity, salary_review


WHOLE = Decimal("1")


class CashFundingService:
    def __init__(self, db, budgets, reporting, reserves, planning, categories, settings, schedules):
        self.db, self.budgets, self.reporting = db, budgets, reporting
        self.schedules = schedules
        self.reserves, self.planning, self.categories, self.settings = reserves, planning, categories, settings

    @property
    def enabled(self):
        return self.settings.get("cash_funding_enabled") == "1"

    def preview(self, on=None):
        day = on or today()
        month = month_of(day)
        stored = {r["category_id"]: from_e6(r["amount_e6"]) for r in
                  self.db.all("SELECT * FROM cash_funding WHERE month=?", (month,))}
        view = self.budgets.month_view(month, schedule=self.schedules.view())
        candidates = [line for section in view.sections for line in section.lines
                      if not line.covered and (line.direct is not None or line.from_loans or line.from_bills)]
        selected = {key: self.categories.get(key) for key in stored}
        for line in candidates:
            cat = self.categories.get(line.category_id)
            if any(cat.code.startswith(other.code + ".") or other.code.startswith(cat.code + ".") for other in selected.values()):
                continue
            selected[cat.id] = cat
        lines = {line.category_id: line for section in view.sections for line in section.lines}
        start, _ = parse_month(month)
        spent = self.budgets.plan_funded_spending(start, day)
        due, missing = [], set()
        bill_coverage = self.planning.bill_reserve_coverage(day, day)
        for payment in self.planning.all_payments(day, day):
            if not payment.outstanding or payment.item.is_income:
                continue
            account = self.reporting.accounts.get(payment.item.account_id) if payment.item.account_id else None
            rate = self.reporting.valuer.fx(account.currency if account else self.reporting.base_currency, day.isoformat())
            if rate is None:
                missing.add(account.currency)
            amount = (payment.still_owed * rate.rate).quantize(Decimal("0.000001")) if rate else ZERO
            due.append((payment, max(amount - bill_coverage.get((payment.item.id, payment.due_date), ZERO), ZERO)))
        rows = []
        for cid, cat in selected.items():
            ids = {cid, *(child.id for child in self.categories.descendants(cid))}
            actual = max(sum((spent.get(key, ZERO) for key in ids), ZERO), ZERO)
            remaining = max(stored.get(cid, ZERO) - actual, ZERO)
            line = lines.get(cid)
            target = max((line.remaining if line and line.remaining is not None else ZERO), ZERO)
            owed = sum((amount for p, amount in due if p.item.category_id in ids), ZERO)
            rows.append({"id": cid, "name": cat.name, "code": cat.code, "ids": sorted(ids), "actual": actual,
                         "remaining": remaining, "target": target, "due": owed,
                         "stored": stored.get(cid, ZERO)})
        reserves = self.reserves.list_active()
        assigned_reserves = sum((r["effective_allocated"] for r in reserves), ZERO)
        own_cash = self.reporting.owned_spendable_cash(day)
        for account in self.reporting.accounts.list():
            if account.account_type not in {AccountType.BANK, AccountType.CASH, AccountType.BROKERAGE}:
                continue
            owned = (self.reporting.account_balance(account.id, day)
                     - self.reporting.money_from_others.cash_total_for_account(account.id, day))
            if owned and self.reporting.valuer.fx(account.currency, day.isoformat()) is None:
                missing.add(account.currency)
        covered = {cid for row in rows for cid in row["ids"]}
        unfunded_due = (sum((max(row["due"] - row["remaining"], ZERO) for row in rows), ZERO)
                        + sum((amount for p, amount in due if p.item.category_id not in covered), ZERO))
        funded = sum((row["remaining"] for row in rows), ZERO)
        ready = own_cash - assigned_reserves - funded - unfunded_due if not missing else None
        pool = max(ready or ZERO, ZERO)
        # Essentials with bills due come first; no expected salary enters this pool.
        rows.sort(key=lambda row: (-row["due"], row["code"]))
        to_plan = ZERO
        for row in rows:
            # Unfunded bills already protect part of this category outside envelopes.
            protected = max(row["due"] - row["remaining"], ZERO)
            add = min(max(row["target"] - row["remaining"], ZERO), pool + protected)
            # A typed amount in whole pounds (IV-12Q1), never 60420.110000: the box shows what is suggested.
            add = max((row["remaining"] + add).quantize(WHOLE, rounding=ROUND_DOWN) - row["remaining"], ZERO)
            row["suggested"] = row["remaining"] + add
            # The part of this addition that covers its protected bills is already in Bills protected
            # (BT-12AD): only the rest is new money to the plan.
            pool -= max(add - protected, ZERO)
            to_plan += max(add - protected, ZERO)
        reserve_rows = []
        monthly = self._monthly_needs(reserves, month, day)
        for reserve in reserves:
            gap = max(reserve["target"] - reserve["allocated"], ZERO)
            # IV-12Q1 (owner, 2026-11-09): a reserve is topped up by what it needs this month (the emergency
            # top-up, a dated goal's monthly share), less what it was given this month, never with all free cash.
            need = monthly.get(reserve["id"], ZERO)
            add = ZERO if reserve.get("planned_item_id") else min(gap, need, pool).quantize(WHOLE, rounding=ROUND_DOWN)
            pool -= add
            reserve_rows.append({"id": reserve["id"], "name": reserve["name"], "allocated": reserve["allocated"],
                                 "effective": reserve["effective_allocated"], "gap": gap, "monthly": need,
                                 "suggested": add})
        ids = portable_ids(self.db, {"categories": [r["id"] for r in rows],
                                     "cash_reserves": [r["id"] for r in reserve_rows]})
        salary = salary_review(self.db, day)
        state = {"month": month, "cash": str(own_cash), "reserve": [(ids[("cash_reserves", r["id"])], str(r["allocated"]), str(r["effective"]), str(r["gap"])) for r in reserve_rows],
                 "rows": [(ids[("categories", r["id"])], str(r["stored"]), str(r["actual"]), str(r["due"]), str(r["target"])) for r in rows],
                 "unfunded_due": str(unfunded_due), "missing": sorted(set(missing))}
        if any(isinstance(value, str) for value in ids.values()):
            # SQLite ids and ties in local row order differ across devices.
            state["reserve"].sort(key=lambda entry: entry[0])
            state["rows"].sort(key=lambda entry: entry[0])
        if salary:
            state["salary_review"] = review_identity(salary)
        token = sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        # The proposal in four disjoint lines that add up to Cash available to assign (F12 r24, BT-12AD): the bills
        # kept, what goes to your plan beyond them, what goes to reserves and goals, and what stays unassigned.
        available = None if ready is None else ready + unfunded_due
        reserves_added = sum((row["suggested"] for row in reserve_rows), ZERO)
        proposal = {"bills": unfunded_due, "to_plan": to_plan, "reserves": reserves_added,
                    "assigned": unfunded_due + to_plan + reserves_added,   # IV-12Q1: what Confirm gives a job
                    "available_before": available,
                    "unassigned": None if available is None else available - unfunded_due - to_plan - reserves_added}
        return {"month": month, "rows": rows, "reserves": reserve_rows, "cash": own_cash,
                "funded": funded, "reserved": assigned_reserves, "unfunded_due": unfunded_due,
                "ready": ready, "left_after_preview": pool, "missing": sorted(set(missing)), "token": token,
                # Cash available to assign (BT-12AD, owner 2026-11-10): owned cash after reserves and funded
                # spending, before the bills due outside those funds, which are one of its parts.
                "available": available,
                "proposal": proposal}

    def _monthly_needs(self, reserves, month, day):
        """What each reserve asks of this month, less what it was already given since the month began: the
        Emergency fund top-up for the emergency fund, Saving for goals for a dated goal; an undated goal asks nothing."""
        from lightning.planning.schedule_view import reserve_goal_needs
        needs = {row["id"]: row["amount"] for row in reserve_goal_needs(self.reserves, month, day)}
        emergency = next((r for r in reserves if r["kind"] == "EMERGENCY"), None)
        if emergency:
            fund = self.budgets.emergency_fund(month, emergency["effective_allocated"], schedule=self.schedules.view())
            needs[emergency["id"]] = fund.top_up
        start, _ = parse_month(month)
        for reserve in reserves:
            if reserve["id"] not in needs:
                continue
            before = self.db.scalar("SELECT allocated_e6 FROM reserve_allocation_history WHERE reserve_id=? AND "
                                    "effective_date<? ORDER BY effective_date DESC,id DESC LIMIT 1",
                                    (reserve["id"], start.isoformat()))
            if before is None:   # set up this month: what it started with is not a top-up
                before = self.db.scalar(
                    "SELECT allocated_e6 FROM reserve_allocation_history WHERE reserve_id=? AND effective_date=("
                    "SELECT MIN(effective_date) FROM reserve_allocation_history WHERE reserve_id=?) "
                    "ORDER BY id DESC LIMIT 1", (reserve["id"], reserve["id"]))
            given = max(reserve["allocated"] - from_e6(before or 0), ZERO)
            needs[reserve["id"]] = max(needs[reserve["id"]] - given, ZERO)
        return needs

    def apply(self, fingerprint, amounts, reserve_additions):
        if not self.enabled:
            raise ValidationError("Turn on cash funding before assigning cash.")
        with self.db.transaction(undo_label="Fund the payday plan"):
            plan = self.preview()
            if fingerprint != plan["token"]:
                raise ValidationError("Cash or plans changed. Review the updated allocation before applying it.")
            if plan["ready"] is None:
                raise ValidationError("Add current exchange rates before assigning cash.")
            ids = {str(row["id"]) for row in plan["rows"]}
            reserve_ids = {str(row["id"]) for row in plan["reserves"]}
            if set(amounts) - ids or set(reserve_additions) - reserve_ids:
                raise ValidationError("Choose categories and reserves from the current preview.")
            total, protected = ZERO, ZERO
            targets = {}
            for row in plan["rows"]:
                amount = check_places(to_decimal(amounts.get(str(row["id"]), row["remaining"])), 6)
                if amount < ZERO:
                    raise ValidationError("Assigned cash cannot be negative.")
                targets[row["id"]] = amount
                total += amount
                protected += max(row["due"] - amount, ZERO)
            protected += plan["unfunded_due"] - sum((max(r["due"] - r["remaining"], ZERO) for r in plan["rows"]), ZERO)
            additions = {}
            for row in plan["reserves"]:
                amount = check_places(to_decimal(reserve_additions.get(str(row["id"]), "0")), 6)
                if amount < ZERO or amount > row["gap"]:
                    raise ValidationError("Reserve additions must fit the remaining goal.")
                additions[row["id"]] = amount
            after = plan["cash"] - plan["reserved"] - total - protected - sum(additions.values(), ZERO)
            if after < ZERO and after < plan["ready"]:
                raise ValidationError("This allocation needs more owned cash than is available.")
            for row in plan["rows"]:
                self.db.execute("INSERT INTO cash_funding(month,category_id,amount_e6,updated_at) VALUES(?,?,?,?) "
                                "ON CONFLICT(month,category_id) DO UPDATE SET amount_e6=excluded.amount_e6,updated_at=excluded.updated_at",
                                (plan["month"], row["id"], to_e6(row["actual"] + targets[row["id"]]), now_iso()))
            for row in plan["reserves"]:
                if additions[row["id"]]:
                    self.reserves.allocate(row["id"], row["allocated"] + additions[row["id"]])
            salary = salary_review(self.db, today())
            if salary:
                self.settings.set("review_item_" + review_identity(salary), json.dumps({"status": "reviewed"}, sort_keys=True))
