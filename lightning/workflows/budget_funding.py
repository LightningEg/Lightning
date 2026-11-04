"""Derive how posted spending is funded without changing ledger cash flow."""
from collections import defaultdict
from types import SimpleNamespace

from lightning.core.dates import fmt_date
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, from_e6
from lightning.reporting.service import flow_of


class BudgetFunding:
    def __init__(self, db):
        self.db = db

    def adjustments(self, start, end):
        """Current links: past periods reflect today's confirmed assignments, dated by the expense."""
        start = fmt_date(start) if not isinstance(start, str) else start
        end = fmt_date(end) if not isinstance(end, str) else end
        return {(txn_id, cid): amounts for (day, txn_id, cid), amounts in self._all_adjustments().items()
                if start <= day <= end}

    @request_cached(deep=True)
    def _all_adjustments(self):
        # Read only transactions with a confirmed link, once per request. Each line follows the
        # reporting spending rule: owned, categorised, not custody, and not income-class inflow.
        rows = self.db.all(
            "SELECT t.id,t.date,le.category_id,le.amount_base_e6,le.effect,c.income_class, "
            "COALESCE((SELECT SUM(l.amount_e6) FROM reserve_transaction_links l "
            "WHERE l.transaction_id=t.id),0) AS reserve_e6, "
            "COALESCE((SELECT SUM(p.principal_e6) FROM loan_extra_payments p "
            "WHERE p.transaction_id=t.id AND p.due_date IS NULL),0) AS principal_e6 "
            "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN categories c ON c.id=le.category_id WHERE t.status='POSTED' "
            "AND le.owner_id IS NULL AND le.effect IN ('INFLOW','OUTFLOW') "
            "AND le.amount_base_e6<0 AND c.code!='EXP.SYSTEM.CUSTODY' "
            "AND t.id IN (SELECT transaction_id FROM reserve_transaction_links "
            "UNION SELECT transaction_id FROM loan_extra_payments WHERE due_date IS NULL)")
        wanted, dates = {}, {}
        categories = defaultdict(lambda: defaultdict(int))
        for row in rows:
            _, spent = flow_of(row['effect'], from_e6(row['amount_base_e6']),
                               SimpleNamespace(income_class=row['income_class']))
            if spent <= ZERO:
                continue
            txn_id = row['id']
            wanted[txn_id] = (int(row['principal_e6']), int(row['reserve_e6']))
            dates[txn_id] = row['date']
            categories[txn_id][row['category_id']] -= row['amount_base_e6']
        result = {}
        for txn_id, (principal, reserve) in wanted.items():
            amounts = categories.get(txn_id, {})
            total = sum(amounts.values())
            if not total:
                continue
            principal = min(principal, total)
            reserve = min(reserve, total - principal)
            # Largest remainders preserve the total and never exceed a category's eligible spending.
            def allocate(amount, weights):
                weight_total = sum(weights.values())
                if not weight_total:
                    return {cid: 0 for cid in weights}
                parts = {cid: divmod(amount * weight, weight_total) for cid, weight in weights.items()}
                out = {cid: part[0] for cid, part in parts.items()}
                remainder = amount - sum(out.values())
                for cid in sorted(weights, key=lambda key: (-parts[key][1], key))[:remainder]:
                    out[cid] += 1
                return out
            principal_parts = allocate(principal, amounts)
            remaining_weights = {cid: amount - principal_parts[cid] for cid, amount in amounts.items()}
            reserve_parts = allocate(reserve, remaining_weights)
            for cid in amounts:
                result[(dates[txn_id], txn_id, cid)] = {'principal': from_e6(principal_parts[cid]),
                                         'reserve': from_e6(reserve_parts[cid])}
        return result

    def by_category(self, start, end):
        totals = defaultdict(lambda: {'principal': ZERO, 'reserve': ZERO})
        for (_, cid), amounts in self.adjustments(start, end).items():
            for key in ('principal', 'reserve'):
                totals[cid][key] += amounts[key]
        return dict(totals)
