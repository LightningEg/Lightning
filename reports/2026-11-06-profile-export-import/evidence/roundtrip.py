"""Reproduce the profile export/import audit (2026-11-06) on dummy sample data only.

Run from the repo root:  python reports/2026-11-06-profile-export-import/evidence/roundtrip.py
Optional: LibreOffice on PATH (soffice) adds the spreadsheet re-save case.
"""
import io
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from lightning.bootstrap import build  # noqa: E402
from lightning.samples import load_mohab_2026  # noqa: E402
from lightning.ui.web import create_app  # noqa: E402
from lightning.workflows.data_export import export_all, export_tables, readable_relations  # noqa: E402
from lightning.workflows.workbook_import import prepare_import, read_workbook  # noqa: E402


def attempt(label, target, data):
    try:
        prepare_import(target, data)
        print(f"  {label}: imports")
    except ValueError as exc:
        cause = f" (cause: {exc.__cause__!r})" if exc.__cause__ else ""
        print(f"  {label}: FAILS: {exc}{cause}")


def main():
    work = Path(tempfile.mkdtemp(prefix="lightning-audit-"))
    try:
        source = build(work / "source.db")
        load_mohab_2026(source)
        data, _, _ = export_all(source, "xlsx")
        sheets = read_workbook(data)
        empty = sum(1 for name, rows in sheets.items() if len(rows) == 1)
        print(f"Export of Mohab's 2026: {len(sheets)} sheets, {empty} of them empty, {len(data):,} bytes")

        print("F1 shape:")
        tables = {name: headings for name, headings, _, _ in export_tables(source)}
        print("  ledger_entries headings:", tables["ledger_entries"])
        bare = [(name, h) for name, headings in tables.items() if name != "Read me"
                for h in headings if h.endswith("_id") and h not in readable_relations(source, name)
                and name != "ledger_entries"]
        print(f"  id columns with no readable name beside them: {len(bare)}: {bare}")

        print("F2 clean room (fresh database, nothing touched):")
        attempt("blank target", build(work / "blank.db"), data)

        print("F3 a new profile after the welcome screen's currency step:")
        for i, form in enumerate(({"currency": "EGP"}, {"currency": "EGP", "extra": "USD"}, {"currency": "USD"})):
            target = build(work / f"welcome{i}.db")
            TestClient(create_app(target)).post("/setup/currency", data=form, follow_redirects=False)
            attempt(f"welcome {form}", target, data)

        print("F4 the same file after a spreadsheet app saves it:")
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(data))
        resaved = io.BytesIO()
        book.save(resaved)
        attempt("re-saved by openpyxl", build(work / "openpyxl.db"), resaved.getvalue())
        if shutil.which("soffice"):
            (work / "lo").mkdir()
            (work / "lo" / "in.xlsx").write_bytes(data)
            subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML",
                            "--outdir", str(work / "lo" / "out"), str(work / "lo" / "in.xlsx")],
                           capture_output=True, timeout=180, check=False)
            attempt("re-saved by LibreOffice", build(work / "lo.db"), (work / "lo" / "out" / "in.xlsx").read_bytes())
        else:
            print("  LibreOffice not installed; skipped")

        print("F5 a file from an older Lightning (one table it did not have yet):")
        older = [(name, rows[0], [tuple(r) for r in rows[1:]], [22] * len(rows[0]))
                 for name, rows in sheets.items() if name != "other_asset_details"]
        from lightning.reporting.xlsx import tabular_workbook_bytes
        attempt("no other_asset_details sheet", build(work / "older.db"), tabular_workbook_bytes(older))

        print("F6 the CSV choice on the export page:")
        zipped, name, _ = export_all(source, "csv")
        attempt(f"{name}", build(work / "csv.db"), zipped)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
