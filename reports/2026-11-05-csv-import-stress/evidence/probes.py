"""Follow-up probes for report 2026-11-05-csv-import-stress, with the columns matched by hand. Dummy data only.
Run from the repo root:  python reports/2026-11-05-csv-import-stress/evidence/probes.py"""
from __future__ import annotations

import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lightning.core import dates  # noqa: E402

dates._local_now = lambda: datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
from lightning.bootstrap import build  # noqa: E402


def stage(c, account, text, mapping):
    batch, _ = c.bank_imports.stage(account, "p.csv", text.encode(), mapping | {"amount_model": "SINGLE"})
    return c.bank_imports.preview(batch)[1]


with tempfile.TemporaryDirectory() as tmp:
    c = build(Path(tmp) / "p.db")
    nbe = c.account_flows.open_account("NBE Current", "BANK", "2025-01-01", "10000", institution="NBE").id
    print("P1 month-first file read day-first:")
    for r in stage(c, nbe, "Date,Amount\n10/01/2026,-250\n10/02/2026,15000\n10/13/2026,-80\n", {"Date": "Date", "Amount": "Amount"}):
        print("   ", r["_line"], r["Date"] or "-", r["_errors"])
    print("P2 a USD row into an EGP account (currency column has no field to map to):")
    for r in stage(c, nbe, "date,amount,currency\n2026-10-03,-40,USD\n", {"Date": "date", "Amount": "amount"}):
        print("   ", r["Date"], r["Amount"], "-> will post as", c.accounts.get(nbe).currency)
    print("P3 Arabic-Indic digits and the Arabic decimal mark:")
    for r in stage(c, nbe, "التاريخ,المبلغ\n٠١/١٠/٢٠٢٦,-٢٥٠٫٥٠\n٠٢/١٠/٢٠٢٦,\"١٥٬٠٠٠\"\n", {"Date": "التاريخ", "Amount": "المبلغ"}):
        print("   ", r["Date"], r["Amount"], r["_errors"])
    print("P4 a DR/CR column the suggestion maps to Category:")
    print("   ", c.bank_imports.suggested_mapping(nbe, ["Date", "Description", "Amount", "Type"]))
    print("P5 seeded categories sharing a name (each asks 'Which one?' when a file names it alone):")
    names = Counter(cat.name for cat in c.categories.pickable())
    print("   ", sorted(n for n, k in names.items() if k > 1))
    print("P6 description column goes to Notes, never to Counterparty:")
    print("   ", c.bank_imports.suggested_mapping(nbe, ["Date", "Description", "Debit", "Credit", "Balance"]))
    c.db.close()
