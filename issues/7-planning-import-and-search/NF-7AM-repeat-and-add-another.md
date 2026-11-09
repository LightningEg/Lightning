---
title: Repeat an entry in one tap, and Save and add another
type: feature
pillar: capture
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) F1 (owner chose it, 2026-11-09). The same coffee, the same taxi, the same grocer: each is typed
again in full. A row's sheet offers edit and delete, not repeat; after Save the sheet closes, so five cash expenses
from a day out are five trips through Add.

## Fix
- **Repeat:** on a transaction's sheet (phone) and row menu (PC), *Repeat* opens Add filled with its kind, account,
  payee, category and amount, dated today; the amount is selected so a new figure replaces it.
- **Save and add another:** a second button on the Add sheet saves, shows the toast, and reopens the sheet keeping
  account and date, focus on Amount.
- **Usual entries:** the Add sheet's first row offers the three payees used most in the last 30 days as chips; a tap
  fills payee, category and account.
Tests: repeat prefill, the kept account and date, chips from history; double submit still refused.
