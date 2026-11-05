---
title: Statements with a Dr/Cr column import every debit as money in
type: bug
look: technical
severity: high
pillar: capture
size: M
status: ready
created: 2026-11-05
by: Claude Opus 5.5
skills: bug-hunt
app_version: 2.0.3
commit: 75d63ae
repo: app
---

## Report
Many Egyptian and Gulf exports print a positive amount plus a separate marker column (`Dr/Cr`, `D/C`, `Type`, `مدين/دائن`).
The map step offers no place for that column, so every row keeps a positive sign. Reproduced with
`Txn Date,Narration,Amount,Dr/Cr` (`UBER TRIP,145.50,DR`): after choosing Transportation, the row posted as an **IN**
transaction of +145.50 and the balance went up. Nothing warned that an expense category was put on money in.
Evidence: [the import scenarios report](../../reports/2026-11-05-import-scenarios/report.md), F1.

## Fix
- The map step offers an optional "Debit/credit marker" column; values DR, D, Debit, مدين (case and spaces ignored) make the
  amount negative, CR, C, Credit, دائن positive; any other value marks the row to fix. Suggest it when a column holds only
  such values. Save it with the column map like the other choices.
- The review marks a row whose category is a spending category while its amount is money in (and the reverse) with a
  plain note, so a wrong sign is caught before posting.
- Tests: a Dr/Cr file posts the right signs; the mismatch note shows.
