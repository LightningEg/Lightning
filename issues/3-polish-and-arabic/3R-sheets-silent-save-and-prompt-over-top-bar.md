---
title: Phone sheets copy the page's undo pill and tabs, Save does nothing without a category, and the raise prompt covers the top bar
type: bug
area: phone
status: ready
created: 2026-10-20
by: Claude
skills: guideline-audit
app_version: 1.3.0
commit: 7591231
repo: app
---

## Report
Found by [Audit 1](../../reports/audit-1.md) (§4 Phone) in the real phone frame (`profile_app(phone=True)`) at 390 and 360 px. Severity: high (each is seen in the first minute of a demo).

1. **Every sheet shows a copy of the page chrome.** Add transaction, pay a bill and edit a transaction show the page's undo pill and a broken
   section-tab row (black glyphs, no track, one icon cut) above the form: a card in a card. Cause: `extract()` in `static/app.js` (about line 1771)
   copies all of `main.main`, including `.phone-page-actions` and the section tabs. Shot: [phone-sheet-copies-page-chrome.png](../../reports/audit-1/phone-sheet-copies-page-chrome.png).
2. **Save silently does nothing without a category.** The own-picker moves `required` from the hidden `<select>` to its text field
   (`app.js:207`), then `initTransactionForm` sets `category.required = true` on the hidden select again (`app.js:1880`); Chrome logs "An invalid
   form control with name='category_id' is not focusable" and blocks the submit with no message. The PC popup and register use the same code, so
   check PC too. Picking a counterparty (Carrefour) also never fills its learned category.
3. **"Your income went up" covers the top bar, then vanishes.** It is a `.flash`; on the phone that is `position:fixed; top:16px; z-index:100`, so it
   hides search, hide amounts, settings and the Budget title, and the 5-second flash timer deletes its buttons. Same cause as 3D. Its figure is also
   false (see 7L1). Shot: [phone-raise-prompt-covers-top-bar.png](../../reports/audit-1/phone-raise-prompt-covers-top-bar.png).
4. **The tab bar never hides for the keyboard or a sheet (C02.4).** `phone.css:47` hides it under `html.keyboard-open` / `html.sheet-open`, but no
   script sets either class, so the tab bar and add button sit above the keyboard on budget limits, reserves, SMS paste and search.

## Fix
1: copy only the form's own content. 2: leave `required` on the visible field (or set custom validity) and show the field message; prefill the learned
category. 3: render offers as page cards, never `.flash`; keep the flash timer for plain messages (with 3D). 4: set the classes on `visualViewport`
resize and on sheet open/close. Test: the phone popup tests, plus a Playwright step that saves without a category and expects the message.
