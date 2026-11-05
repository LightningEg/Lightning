"""CSV import stress test (report 2026-11-05-csv-import-stress). Dummy data only.

Run from the repo root:  python reports/2026-11-05-csv-import-stress/evidence/stress_import.py [--json OUT]

Each scenario is a file a real person might bring. It goes through what the app does: the upload route reads it,
the column suggestion is accepted as is, the review is built, and "Post ready rows" posts the rows the review
calls ready with the review's own defaults. Nothing is fixed here; the script only measures.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from lightning.core import dates  # noqa: E402

dates._local_now = lambda: datetime(2026, 11, 5, 12, tzinfo=timezone.utc)

from lightning.bootstrap import build  # noqa: E402
from lightning.ui.web import create_app  # noqa: E402


def csv(text: str) -> bytes:
    return text.strip("\n").replace("\n", "\r\n").encode("utf-8") + b"\r\n"


def many(n: int) -> bytes:
    lines = ["Date,Amount,Counterparty,Category,Notes,Reference"]
    shops = ["Seoudi", "Uber", "Talabat", "Vodafone", "Carrefour", "Salary", "Fawry", "Breadfast"]
    for i in range(n):
        day = f"2025-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}"
        amount = "25000" if shops[i % 8] == "Salary" else f"-{100 + (i * 37) % 900}.{i % 100:02d}"
        lines.append(f"{day},{amount},{shops[i % 8]},,row {i},REF{i:06d}")
    return ("\n".join(lines) + "\n").encode()


S = []  # (id, case, title, filename, data)
def add(sid, case, title, data, filename="statement.csv"):
    S.append((sid, case, title, filename, data))


# A. Bank statements people download or type
add("A1", "bank", "Lightning's own template, ISO dates", csv("""
Date,Amount,Counterparty,Category,Notes,Reference
2026-10-01,-250.50,Seoudi,Food & Groceries,,R1
2026-10-02,15000,Employer,Salary,,R2
2026-10-03,-80,Uber,Transportation,,R3"""))
add("A2", "bank", "Debit and Credit columns, day-first dates, Balance column", csv("""
Transaction Date,Description,Debit,Credit,Balance
01/10/2026,POS SEOUDI DOKKI,250.50,,9749.50
02/10/2026,SALARY TRANSFER,,15000.00,24749.50
03/10/2026,UBER TRIP,80.00,,24669.50"""))
add("A3", "bank", "Value Date and Posting Date both present", csv("""
Posting Date,Value Date,Narrative,Amount
05/10/2026,03/10/2026,CARD PURCHASE TALABAT,-175.66
06/10/2026,06/10/2026,ATM WITHDRAWAL,-2000"""))
add("A4", "bank", "Positive amounts with a DR/CR column", csv("""
Date,Description,Amount,Type
2026-10-01,SEOUDI,250.50,DR
2026-10-02,SALARY,15000,CR
2026-10-03,UBER,80,DR"""))
add("A5", "bank", "Thousands separators, currency codes and brackets", csv("""
Date,Description,Amount
2026-10-01,Rent,"(12,500.00)"
2026-10-02,Salary,"EGP 25,000.00"
2026-10-03,Fee,-1.50 EGP
2026-10-04,Refund,"1.234,56"
"""))
add("A6", "bank", "Arabic headers and Arabic-Indic digits", csv("""
التاريخ,البيان,المبلغ
٠١/١٠/٢٠٢٦,سعودي,-٢٥٠٫٥٠
٠٢/١٠/٢٠٢٦,مرتب,١٥٠٠٠"""))
add("A7", "bank", "Bank preamble lines above the header", csv("""
National Bank statement
Account: ****1234
Period: 01/10/2026 - 31/10/2026
Date,Description,Amount
2026-10-01,SEOUDI,-250.50
2026-10-02,SALARY,15000"""))
add("A8", "bank", "Totals footer and blank lines", csv("""
Date,Description,Amount
2026-10-01,SEOUDI,-250.50

2026-10-02,SALARY,15000
,Total,14749.50
,Closing balance,24749.50"""))
add("A9", "bank", "Semicolon separated, comma decimals", csv("""
Date;Description;Amount
2026-10-01;SEOUDI;-250,50
2026-10-02;SALARY;15000,00"""))
add("A10", "bank", "Saved by Excel in Windows Arabic (cp1256)",
    "Date,Description,Amount\r\n2026-10-01,سعودي,-250.50\r\n".encode("cp1256"))
add("A11", "bank", "Saved as UTF-16 (Excel 'Unicode text')",
    "Date\tDescription\tAmount\r\n2026-10-01\tSEOUDI\t-250.50\r\n".encode("utf-16"))
add("A12", "bank", "Month-first dates (US export)", csv("""
Date,Description,Amount
10/13/2026,SEOUDI,-250.50
10/02/2026,SALARY,15000"""))
add("A13", "bank", "Dates with a time of day", csv("""
Date,Description,Amount
2026-10-01 14:33:00,SEOUDI,-250.50
2026-10-02T09:00:00,SALARY,15000"""))
add("A14", "bank", "Month names and two-digit years", csv("""
Date,Description,Amount
01-Oct-2026,SEOUDI,-250.50
2 Oct 26,SALARY,15000
03/10/26,UBER,-80"""))
add("A15", "bank", "Zero-amount rows (waived fees)", csv("""
Date,Description,Amount
2026-10-01,FEE WAIVED,0
2026-10-02,SALARY,15000"""))
add("A16", "bank", "Rows dated in the future (pending card holds)", csv("""
Date,Description,Amount
2026-10-01,SEOUDI,-250.50
2026-12-01,PENDING HOLD,-999"""))
add("A17", "bank", "Running balance only, no amount column", csv("""
Date,Description,Balance
2026-10-01,Opening,10000
2026-10-02,SEOUDI,9749.50
2026-10-03,SALARY,24749.50"""))
add("A18", "bank", "Newest first, salary and spending the same day", csv("""
Date,Description,Amount
2026-10-02,RENT,-12000
2026-10-02,SALARY,15000
2026-10-01,SEOUDI,-250.50"""))

# B. Other apps' exports
add("B1", "other-app", "Money Manager style: positive amounts, Income/Expense column, Subcategory", csv("""
Date,Account,Category,Subcategory,Note,EGP,Income/Expense,Description
10/01/2026,NBE,Food,Groceries,Seoudi,250.50,Expense,
10/02/2026,NBE,Salary,,Employer,15000,Income,
10/03/2026,NBE,Transport,Uber,Ride,80,Expense,"""))
add("B2", "other-app", "Wallet style: semicolons, ISO timestamps, currency column", csv("""
account;category;currency;amount;ref_currency_amount;payment_type;note;date;payee
NBE;Groceries;EGP;-250.50;-250.50;DEBIT_CARD;;2026-10-01T10:15:00.000Z;Seoudi
NBE;Salary;EGP;15000;15000;TRANSFER;;2026-10-02T09:00:00.000Z;Employer
NBE;Travel;USD;-40;-1960;DEBIT_CARD;;2026-10-03T12:00:00.000Z;Airline"""))
add("B3", "other-app", "Group and category in one column (Food:Groceries, Food > Groceries, Food/Groceries)", csv("""
Date,Amount,Counterparty,Category
2026-10-01,-250.50,Seoudi,Personal:Food & Groceries
2026-10-02,-80,Uber,Work > Transportation
2026-10-03,-60,Kiosk,Personal/Eating Out"""))
add("B4", "other-app", "Group column plus unknown names (the owner's case)", csv("""
Account,Date,Counterparty,Notes,Category_Group,Category,Amount,Split_Amount,Cleared
Bank,01/10/2026,Uber,Card,Work,Transportation,-120,0,Cleared
Bank,02/10/2026,Kiosk,Daily,Usual Expenses,Daily Expenses,-30,0,Cleared
Bank,03/10/2026,Kiosk,Daily,Usual Expenses,Daily Expenses,-45,0,Cleared
Bank,04/10/2026,THNDR,Transfer to THNDR,Investments and Savings,Savings,-5000,0,Cleared
Bank,01/09/2026,,Adjustment,Income,Starting Balances,1013.94,0,Not cleared"""))
add("B5", "other-app", "One file, two accounts (Account column)", csv("""
Account,Date,Amount,Counterparty,Category
NBE,2026-10-01,-250.50,Seoudi,Food & Groceries
CIB,2026-10-01,-99,Netflix,Subscriptions
NBE,2026-10-02,15000,Employer,Salary"""))
add("B6", "other-app", "Split transaction rows (parent row plus split lines)", csv("""
Date,Amount,Counterparty,Category,Split_Amount
2026-10-01,-1000,Carrefour,Food & Groceries,-700
2026-10-01,-1000,Carrefour,Home,-300"""))
add("B7", "other-app", "Transfers between two own accounts written twice", csv("""
Date,Amount,Counterparty,Category,Notes
2026-10-05,-5000,THNDR,Transfer,Transfer out
2026-10-05,-5000,,,Transfer out | duplicate line of the same transfer
2026-10-06,4000,,,Ownership to you
2026-10-06,-4000,,,Ownership from Mama"""))

# C. Repeat and overlap
add("C1", "repeat", "The same file a second time", csv("""
Date,Amount,Counterparty,Category,Reference
2026-10-01,-250.50,Seoudi,Food & Groceries,R1
2026-10-02,15000,Employer,Salary,R2"""), "repeat.csv")
add("C2", "repeat", "Overlapping month: 01-02 again plus 03-04, no references", csv("""
Date,Amount,Counterparty,Category
2026-10-01,-250.50,Seoudi,Food & Groceries
2026-10-02,15000,Employer,Salary
2026-10-03,-80,Uber,Transportation
2026-10-04,-36,Vodafone,Utilities & Bills"""), "overlap.csv")
add("C3", "repeat", "Bank's own name spellings of known counterparties", csv("""
Date,Amount,Counterparty
2026-10-07,-80,UBER *TRIP HELP.UBER.COM
2026-10-08,-250.50,SEOUDI MARKET DOKKI 0023
2026-10-09,-36,VODAFONE EG TOPUP 01001234567"""))

# D. Hostile and large
add("D1", "hostile", "Formula-looking text in notes", csv("""
Date,Amount,Counterparty,Notes
2026-10-01,-10,"=HYPERLINK(""http://x"",""click"")",+cmd
2026-10-02,-10,@SUM(A1),-2+3"""))
add("D2", "hostile", "Duplicate header names", csv("""
Date,Amount,Amount,Notes
2026-10-01,-10,-10,x"""))
add("D3", "hostile", "Very long text in one cell", csv("Date,Amount,Notes\n2026-10-01,-10," + "x" * 20000))
add("D4", "large", "1,000 rows", many(1000), "big1000.csv")
add("D5", "large", "5,000 rows", many(5000), "big5000.csv")
add("D6", "large", "Over the 5 MB limit", b"Date,Amount,Notes\r\n" + b"2026-10-01,-1," + b"y" * (5_100_000) + b"\r\n")


def run(sid, case, title, filename, data, c, client, account):
    out = {"id": sid, "case": case, "title": title, "bytes": len(data)}
    t0 = time.perf_counter()
    response = client.post(f"/accounts/{account}/import", files={"file": (filename, io.BytesIO(data), "text/csv")},
                           follow_redirects=False)
    out["upload_seconds"] = round(time.perf_counter() - t0, 2)
    text = response.text
    if response.status_code == 303 or response.status_code == 302:
        batch = int(re.search(r"/import/(\d+)", response.headers["location"]).group(1))
        out["path"] = "staged without the column step"
    elif 'class="import-map-form"' in text:
        from lightning.bank_import_rows import decode_csv
        headers, _ = decode_csv(data)
        mapping = c.bank_imports.suggested_mapping(account, headers)
        out["suggested"] = {k: v for k, v in mapping.items() if k != "amount_model"}
        out["path"] = "column step"
        missing = [k for k in ("Date",) if k not in mapping]
        if "Amount" not in mapping and not ("Inflow" in mapping and "Outflow" in mapping):
            missing.append("Amount")
        if missing:
            out["result"] = f"blocked at the column step: nothing suggested for {', '.join(missing)}"
            return out
        try:
            batch, _ = c.bank_imports.stage(account, filename, data, mapping)
        except Exception as exc:  # noqa: BLE001 - the stress test records every refusal
            out["result"] = f"refused at staging: {getattr(exc, 'message', exc)}"
            return out
    else:
        error = re.search(r'class="(?:flash error|alert alert-error)"[^>]*>([^<]+)', text)
        out["result"] = f"refused at upload ({response.status_code}): {error.group(1).strip() if error else 'no message'}"
        return out
    t1 = time.perf_counter()
    _, rows = c.bank_imports.preview(batch)
    page = client.get(f"/accounts/{account}/import/{batch}")
    out["review_seconds"] = round(time.perf_counter() - t1, 2)
    out["review_page_kb"] = round(len(page.content) / 1024)
    states = {"err": 0, "needs": 0, "dup": 0, "ready": 0}
    from lightning.ui.routes.bank_imports import _row_status, _row_ui
    errors, notes = {}, []
    form = {}
    for r in rows:
        state = _row_status(r)
        states[state] += 1
        for e in r.get("_errors") or []:
            errors[e[:90]] = errors.get(e[:90], 0) + 1
        ui = _row_ui(r)
        rid = r["_import_row_id"]
        form |= {f"counterparty_{rid}": ui["cp"], f"counterparty_pick_{rid}": ui["cp_pick"],
                 f"category_{rid}": ui["cat"], f"match_{rid}": ui["match"]}
        if ui["skip"]:
            form[f"skip_{rid}"] = "on"
    out["rows"] = len(rows)
    out["states"] = states
    out["errors"] = errors
    out["dates"] = sorted({r["Date"] for r in rows if not r.get("_errors")})[:4]
    out["amounts"] = [r["Amount"] for r in rows[:4]]
    out["labels"] = sorted({r.get("_file_label") for r in rows if r.get("_file_label")})[:6]
    before = c.reporting.account_balance(account)
    t2 = time.perf_counter()
    posted = client.post(f"/accounts/{account}/import/{batch}/confirm", data=form, follow_redirects=False)
    out["post_seconds"] = round(time.perf_counter() - t2, 2)
    after = c.reporting.account_balance(account)
    out["posted_status"] = posted.status_code
    out["balance_change"] = format(Decimal(str(after)) - Decimal(str(before)), "f")
    out["posted_rows"] = c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='POSTED'", (batch,))
    return out


def main():
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for sid, case, title, filename, data in S:
            # A fresh profile per scenario, except the repeat cases, which share one with a first import.
            c = build(Path(tmp) / f"{sid}.db")
            client = TestClient(create_app(c), base_url="http://127.0.0.1")
            account = c.account_flows.open_account("NBE Current", "BANK", "2025-01-01", "10000", institution="NBE").id
            c.account_flows.open_account("CIB Current", "BANK", "2025-01-01", "5000", institution="CIB")
            c.account_flows.open_account("THNDR", "BROKERAGE", "2025-01-01", "0", institution="THNDR")
            if case == "repeat":
                first = csv("""
Date,Amount,Counterparty,Category,Reference
2026-10-01,-250.50,Seoudi,Food & Groceries,R1
2026-10-02,15000,Employer,Salary,R2""")
                run("pre", case, "first import", "repeat.csv", first, c, client, account)
            results.append(run(sid, case, title, filename, data, c, client, account))
            c.db.close()
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
