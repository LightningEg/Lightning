---
title: Phone Add: start on the amount, come back to the same Home, pay from the account that payee usually uses
type: polish
pillar: capture
size: M
model: sonnet
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) A1-A4. Evidence: [sheet](r31-logging-entries/evidence/phone-add-sheet.png),
[after Save](r31-logging-entries/evidence/phone-after-save.png).
- **Focus.** Add opens with the focus on the Out/In/Move radio, not Amount (r27 J1 reproduced again on 2026-11-09;
  IV-3BF4 covers the PC only). Typing a number right away types nowhere.
- **A different Home after Save.** Home shows "Home · Safe to spend · To do"; after Save the same address shows
  "Overview" with a month picker, "4 items need you", Net worth and Left in plan. Two home pages.
- **From.** The list offers the CD portfolio, the gam'eya and the broker for a shop payment. The default is the last
  account used; a payee always paid from the wallet (Vodafone, paid from Vodafone Cash) still defaults to the bank.
- **Validation** is the browser's bubble ("Choose an option from the list") over the category list.

## Fix
Focus Amount when the sheet opens (and after Paste SMS fails). Save returns to the page the sheet was opened over,
unchanged but for the toast. From lists accounts money is paid from; choosing a payee selects its usual account as it
selects its category (same 3-of-5 habit rule, `TransactionService.usual_categories`). Our own message for a missing
category. Tests: the phone Add tests for the focus marker, return page and the payee's account; Mohab's phone step.
