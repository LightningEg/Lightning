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

## 3BD2 Every validation message has Arabic · M · #410
Files: a new test `tests/test_messages_translated.py`; `lightning/ui/i18n.py` (`ARABIC_UI`); the message sources it reports.
Do: (1) Write the test first: walk `lightning/**/*.py` with `ast`, collect every string literal passed as the first argument to `ValidationError(...)`, `NotFoundError(...)` or `ProfileError(...)`, and assert each is a key of `ARABIC_UI` (or matches a `{…}` pattern key). It fails with today's list (about 87). (2) Add the Arabic for each, in Egyptian colloquial per `guideline/brand-voice.md` (read its Arabic section only). (3) For an f-string message the test cannot read, add a pattern key with `{name}` placeholders to `ARABIC_UI` that matches it (e.g. `"Row {n}: the fee is not a number."`); `translate` already fills pattern keys.
Done when: `python -m pytest tests/test_messages_translated.py -q` passes with no allowlist longer than 10 entries, each with a reason.
