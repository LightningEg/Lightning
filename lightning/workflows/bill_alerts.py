"""Conservative, evidence-backed bill warnings; detection never changes money or plans."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json
from statistics import median

from lightning.core.money import from_e6


def bill_alerts(c, on):
    alerts = []
    for item in c.planning.items():
        if item.kind.value not in ('BILL', 'SUBSCRIPTION') or item.frequency.value != 'MONTHLY' or item.interval_count != 1:
            continue
        if not item.account_id or not item.counterparty_id or not item.category_id:
            continue
        currency = c.accounts.get(item.account_id).currency
        rows = c.db.all(
            "SELECT t.id,t.ref,t.date,SUM(l.quantity_e6) quantity,t.type FROM transactions t "
            "JOIN ledger_entries l ON l.transaction_id=t.id JOIN financial_assets f ON f.id=l.asset_id "
            "WHERE t.status='POSTED' AND t.type IN ('IN','OUT') AND l.account_id=? "
            "AND t.counterparty_id=? AND l.category_id=? AND l.owner_id IS NULL AND f.is_cash=1 "
            "AND l.effect IN ('INFLOW','OUTFLOW') AND t.date BETWEEN ? AND ? "
            "GROUP BY t.id ORDER BY t.date,t.id",
            (item.account_id, item.counterparty_id, item.category_id, str(on - timedelta(days=300)), str(on)))
        charges = [dict(r) | {'amount': -from_e6(r['quantity'])} for r in rows if r['quantity'] < 0 and r['type'] == 'OUT']
        if not charges:
            continue
        latest_month = charges[-1]['date'][:7]
        current = [r for r in charges if r['date'][:7] == latest_month]
        if current[-1]['date'] < str(on - timedelta(days=45)):
            continue
        # A refund in the current period makes a duplicate inference unsafe.
        if any(r['quantity'] > 0 and r['date'][:7] == latest_month for r in rows):
            continue
        by_month = defaultdict(list)
        for row in charges:
            if row['date'][:7] < latest_month:
                by_month[row['date'][:7]].append(row)
        history = [group[0] for _, group in sorted(by_month.items()) if len(group) == 1][-6:]
        variable = 'UTILITIES' in c.categories.get(item.category_id).code
        if len(history) < (6 if variable else 3):
            continue
        amounts = [r['amount'] for r in history]
        center = median(amounts)
        mad = median([abs(value - center) for value in amounts])
        stable = center > 0 and max(amounts) - min(amounts) <= center * Decimal('.2')
        if not variable and not stable:
            continue
        # Monthly history must establish a cadence, not just several isolated purchases.
        from datetime import date
        gaps = [(date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days for a,b in zip(history, history[1:])]
        if not all(21 <= gap <= 40 for gap in gaps):
            continue
        candidates = []
        threshold = max(center * (Decimal('.5') if variable else Decimal('.2')), mad * (6 if variable else 4))
        if len(current) == 1 and current[0]['amount'] > center + threshold:
            candidates.append(('drift', current, 'Bill amount changed',
                               'Latest {amount} {currency}; historical median {median}; review above {threshold}.',
                               {'amount': f"{current[0]['amount']:f}", 'currency': currency,
                                'median': f'{center:f}', 'threshold': f'{center + threshold:f}'}))
        if not variable and len(current) == 2:
            first, second = current
            if (date.fromisoformat(second['date']) - date.fromisoformat(first['date'])).days <= 3 and all(abs(r['amount'] - center) <= max(mad*3, center*Decimal('.05')) for r in current):
                candidates.append(('repeat', current, 'Possible repeated bill charge',
                                   'Two charges within three days; prior months show one charge near {amount} {currency}.',
                                   {'amount': f'{center:f}', 'currency': currency}))
        for kind, evidence, label, detail_key, values in candidates:
            # Stable references carry the identity across local database ids. New evidence reopens a handled warning.
            version = [(r['ref'], r['date'], str(r['amount'])) for r in history + evidence]
            key = sha256(json.dumps([kind, version, currency], sort_keys=True).encode()).hexdigest()
            alerts.append({'key': key, 'plan_id': item.id, 'label': label, 'name': item.name, 'detail_key': detail_key,
                           'values': values, 'detail': detail_key.format(**values), 'evidence': evidence,
                           'history': history, 'priority': 2, 'href': f'/plan/bill-alerts/{key}', 'action': 'Review',
                           'source_version': version})
    # Two plans naming the same merchant must not produce the same warning twice.
    return list({row['key']: row for row in alerts}.values())
