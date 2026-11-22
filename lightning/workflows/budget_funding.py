"""Derive how posted spending is funded without changing ledger cash flow."""
from collections import defaultdict
from types import SimpleNamespace

from lightning.core.dates import fmt_date
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, from_e6
from lightning.reporting.service import flow_of



def _allocate(amount, weights):
    """Split ``amount`` over ``weights`` by largest remainders: the parts keep the total and never exceed a weight."""
    weight_total = sum(weights.values())
    if not weight_total:
        return {cid: 0 for cid in weights}
    parts = {cid: divmod(amount * weight, weight_total) for cid, weight in weights.items()}
    out = {cid: part[0] for cid, part in parts.items()}
    remainder = amount - sum(out.values())
    for cid in sorted(weights, key=lambda key: (-parts[key][1], key))[:remainder]:
        out[cid] += 1
    return out


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
            principal_parts = _allocate(principal, amounts)
            remaining_weights = {cid: amount - principal_parts[cid] for cid, amount in amounts.items()}
            reserve_parts = _allocate(reserve, remaining_weights)
            for cid in amounts:
                result[(dates[txn_id], txn_id, cid)] = {'principal': from_e6(principal_parts[cid]),
                                         'reserve': from_e6(reserve_parts[cid])}
        result.update(self._refunds_to_reserves())
        return result

    def _refunds_to_reserves(self):
        """NF-12AK4 (owner, 2026-11-13): money back for a reserve-funded purchase returns to the reserve first, so the
        refund's month takes that part off monthly-plan spending's reduction: a negative reserve adjustment, spread
        over the refund's own money-back lines in its purchase's categories."""
        back = {int(row['refund_id']): int(row['amount_e6']) for row in self.db.all(
            "SELECT refund_id,SUM(amount_e6) amount_e6 FROM reserve_refunds GROUP BY refund_id")}
        if not back:
            return {}
        marks = ','.join('?' * len(back))
        rows = self.db.all(
            "SELECT t.id,t.date,le.category_id,SUM(le.amount_base_e6) total_e6 FROM transactions t "
            "JOIN ledger_entries le ON le.transaction_id=t.id JOIN refund_links rl ON rl.refund_id=t.id "
            "WHERE t.status='POSTED' AND le.owner_id IS NULL AND le.effect IN ('INFLOW','OUTFLOW') "
            "AND le.amount_base_e6>0 AND le.category_id IN (SELECT category_id FROM ledger_entries "
            f"WHERE transaction_id=rl.expense_id) AND t.id IN ({marks}) GROUP BY t.id,le.category_id",
            tuple(back))
        weights, dates = defaultdict(dict), {}
        for row in rows:
            weights[int(row['id'])][int(row['category_id'])] = int(row['total_e6'])
            dates[int(row['id'])] = row['date']
        result = {}
        for refund_id, lines in weights.items():
            amount = min(back[refund_id], sum(lines.values()))
            for cid, part in _allocate(amount, lines).items():
                result[(dates[refund_id], refund_id, cid)] = {'principal': ZERO, 'reserve': -from_e6(part)}
        return result

    def by_category(self, start, end):
        totals = defaultdict(lambda: {'principal': ZERO, 'reserve': ZERO})
        for (_, cid), amounts in self.adjustments(start, end).items():
            for key in ('principal', 'reserve'):
                totals[cid][key] += amounts[key]
        return dict(totals)
