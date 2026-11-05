"""Upload each scenario file to a running demo and print what the import does with it.

Run from the repo root, with the demo running (`python -m lightning --demo --no-browser`):
    python reports/2026-11-05-import-scenarios/evidence/run_scenarios.py
Dummy files only. Each upload stages a review; nothing is posted. Restart the demo to clear them.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8766"
FILES = Path(__file__).resolve().parent / "files"
# (file, account id in the demo: 1 CIB Payroll, 4 THNDR)
SCENARIOS = [("s1_cib_full.csv", 1), ("s2a_arabic_utf8.csv", 1), ("s2b_arabic_cp1256.csv", 1),
             ("s2c_preamble.csv", 1), ("s2d_drcr.csv", 1), ("s2f.csv", 1), ("s3a_one_sheet_multi.xlsx", 1),
             ("s3b_sheet_per_account.xlsx", 1), ("s3c_formula_and_notes.xlsx", 1), ("thndr.csv", 4)]


def main() -> None:
    session = requests.Session()
    for name, account in SCENARIOS:
        response = session.post(f"{BASE}/accounts/{account}/import",
                                files=[("file", (name, (FILES / name).read_bytes()))], data={"__session": ""})
        page = response.text
        error = re.search(r'role="alert"[^>]*>(.*?)</', page, re.S)
        mapped = {}
        for part in page.split('name="map_')[1:]:
            chosen = re.search(r'<option value="([^"]*)" selected', part.split("</select>")[0])
            if chosen and chosen.group(1):
                mapped[part.split('"')[0]] = chosen.group(1)
        model = re.search(r'name="amount_model" value="(\w+)" checked', page)
        if model:
            mapped["amounts"] = model.group(1)
        if error:
            print(f"{name}: refused: {html.unescape(re.sub(r'<[^>]+>', '', error.group(1))).strip()}")
        elif "Match your columns" in page:
            print(f"{name}: map step; suggested {mapped or 'nothing'}")
        else:
            print(f"{name}: review at {response.url}")


if __name__ == "__main__":
    main()
