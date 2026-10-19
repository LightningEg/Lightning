---
title: CSV import rejects amounts like (1,250.00), 1,250.00-, EGP 1,250.00 and Arabic digits
type: bug
area: import
status: ready
created: 2026-10-19
by: Claude
github: 49
---

## Report
`bank_imports._decimal_amount` reads a leading minus only. Parentheses, a trailing minus, the true minus sign, a currency code or symbol around the number, and Arabic-Indic digits are rejected with "Enter a valid number.", so every such row is fixed by hand in the review.

## Fix
Read them all in `_decimal_amount` (digits through `core.money.ascii_digits`), keep today's readings, still reject two signs (`-(5)`) and non-numbers. One test per form in `tests/test_bank_imports.py`. Small and self-contained: GitHub #49.
