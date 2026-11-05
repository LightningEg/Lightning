---
title: Read real bank exports: Arabic headers, Windows Arabic encoding, title lines and total rows
type: polish
look: technical
pillar: capture
size: M
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
Scenarios in [the import scenarios report](../../reports/2026-11-05-import-scenarios/report.md) (F3-F6):
- **Arabic headers** (`التاريخ, البيان, مدين, دائن, الرصيد`) match nothing; the person maps every column by hand.
- **Windows Arabic CSV** (cp1256, what Excel's "CSV" saves on an Arabic Windows) is refused with "Save the statement as a
  UTF-8 CSV file". Most people do not know what that means.
- **Title lines before the header** (bank name, account number, period, an empty line, as CIB and NBE exports have) make the
  first line the header: the only column offered is "Commercial International Bank", a dead end.
- **Total and closing-balance rows** at the end become rows to fix.
- Common English names are missed: `Txn Date`, `Narration`, `Withdrawal`, `Deposit` (some are there), `Value Date` order.

## Fix
- Aliases in `suggested_mapping` (`lightning/bank_imports.py`): Arabic (`التاريخ`, `تاريخ الحركة`, `البيان`, `الوصف`,
  `مدين`, `دائن`, `المبلغ`, `المرجع`) and the English ones above.
- `decode_csv` tries UTF-8, then UTF-16 (BOM), then cp1256, and says which it used only when it guessed.
- Find the header row: the first line in the first 30 whose cells include a date-like and an amount-like column name; the
  lines above it are kept out. Rows whose date cell is empty and whose text says Total, Opening/Closing balance, الإجمالي or
  الرصيد are dropped with a count shown in the review ("2 summary lines left out").
- The same for `.xlsx` (`lightning/statement_files.py`), which shares the CSV path.
- Tests with dummy files for each case.
