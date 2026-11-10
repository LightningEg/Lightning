---
title: Every error speaks plainly, in the person's language, on a branded page - no JSON, plain text, raw exceptions or half-English
type: polish
pillar: feel
size: M
model: sonnet
status: ready
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F4-F6.

- **Paths that skip translation and the brand:** JSON `{"error": exc.message}` (`web.py:670`); plain-text cross-origin block (`web.py:612`); `HTTPException(400)` in `routes/exports.py:37,109` falls to FastAPI JSON; `text/plain` at `exports.py:134,136,161` and `settings.py:342` ("Invalid value."); `budget.html:83` shows `e.message` raw with a hard-coded `'Active: '`.
- **No Arabic:** 87 of about 700 `ValidationError`/`NotFoundError` messages, plus 115 built with f-strings (e.g. `reimbursements.py:311`, `categories/service.py:223`, `transactions/service.py:813` which also exposes the record reference).
- **Half-English in Arabic:** "جرّب تاني بعد 5 minutes." (`runtime/session.py:84`), "احذف this category? …" (`categories/list.html:100`), "البند 2: price and exchange rate must be positive." (`core/ledger.py:164`).
- **Raw internals:** "Could not read this CSV: {exc}" (`bank_import_rows.py:277`), "CSV row {n}: fee: {exc}" (`bank_import_posting.py:50,127`), "Unknown investment event: {event}" (`investments/events.py:127`), developer wording at `money_from_others.py:28`; tooltip "OUT-2026-10-02-001 — edit in this list" (`register.html:217`).
- **One page for every validation error:** `validation_error.html:2-5` is titled "Check your setup" and always links Exchange rates, Recurring and Accounts.
- **A PC 500:** `GET /transactions/sorted` renders a template that exists only for the phone (`routes/transactions.py:161`).

## Fix

One error path: every 4xx/5xx renders the branded page (PC and phone), or for fetch callers a JSON body whose message is already localised; raw exception text is logged, never shown; the validation page names the field and the one action that fixes it. Add Arabic for every user-facing message and build counted ones with IV-3BC. The PC `/transactions/sorted` redirects to Transactions. Tests: extend `tests/test_arabic_no_english.py` to assert status codes, POST error responses and JSON error bodies; a test that no route returns `text/plain` or `{"detail":…}` to a page.

## How to work on this item

Each step is one pull request. Read only the files a step names. Run the step's test command and `python -m pytest tests/test_arabic_no_english.py -q`; delete the step's heading in the same commit. Never show a Python exception's text to a person; log it with `logging.getLogger("lightning")`.

## 3BD5 The validation page names the problem, not "Check your setup" · S · #413
Files: `lightning/ui/templates/validation_error.html`, `lightning/ui/templates/phone/` (its phone twin if one exists: `ls lightning/ui/templates/phone | grep -i error`).
Do: title "That did not save" (Arabic: "ما اتحفظش"); the message as the lead line; one Back button to `request.headers.referer` when it is a same-origin path, else Overview/Home; drop the three fixed links. Follows A09 (answer first) and A14.
Done when: `tests/test_error_pages.py` posts an invalid amount and finds the new title and a Back link, and no "Check your setup". Check A16 by eye on a screenshot.
