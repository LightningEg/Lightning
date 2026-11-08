---
title: Every error speaks plainly, in the person's language, on a branded page - no JSON, plain text, raw exceptions or half-English
type: polish
pillar: feel
size: M
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

## 3BD1 No raw responses: 403, 400 and plain text get the branded page · S
Files: `lightning/ui/web.py` (`same_origin_posts` line ~612, `http_problem` line ~679), `lightning/ui/routes/exports.py:37,109,134,136,161`, `lightning/ui/routes/settings.py:342`, `lightning/ui/routes/transactions.py:161`.
Do: (1) `same_origin_posts` returns `render(request, "error.html", status_code=403, message="This form came from outside Lightning, so it was not sent.")`. (2) `http_problem`: every status except 404 also renders `error.html` with a short message per code (400 "That request was not complete.", 403 as above, 405 "That page cannot do this."). (3) Replace `PlainTextResponse` and `HTTPException(400, …)` in exports and settings with `raise ValidationError("<plain sentence>")`. (4) `/transactions/sorted` on the PC (`not request.state.phone`) redirects to `/transactions`. Add Arabic for every new sentence in `ARABIC_UI`.
Done when: new `tests/test_error_pages.py` posts with a foreign `Origin` header and gets 403 HTML with the page title; `GET /transactions/sorted` on the PC app gets 303 to `/transactions`; and `grep -rn "PlainTextResponse\|HTTPException(" lightning/ui/routes lightning/ui/web.py` lists only allowed file downloads. `python -m pytest tests/test_error_pages.py -q`.

## 3BD2 Every validation message has Arabic · M
Files: a new test `tests/test_messages_translated.py`; `lightning/ui/i18n.py` (`ARABIC_UI`); the message sources it reports.
Do: (1) Write the test first: walk `lightning/**/*.py` with `ast`, collect every string literal passed as the first argument to `ValidationError(...)`, `NotFoundError(...)` or `ProfileError(...)`, and assert each is a key of `ARABIC_UI` (or matches a `{…}` pattern key). It fails with today's list (about 87). (2) Add the Arabic for each, in Egyptian colloquial per `guideline/brand-voice.md` (read its Arabic section only). (3) For an f-string message the test cannot read, add a pattern key with `{name}` placeholders to `ARABIC_UI` that matches it (e.g. `"Row {n}: the fee is not a number."`); `translate` already fills pattern keys.
Done when: `python -m pytest tests/test_messages_translated.py -q` passes with no allowlist longer than 10 entries, each with a reason.

## 3BD3 Half-English sentences and internal codes · S
Files: `lightning/runtime/session.py:84`, `lightning/ui/templates/categories/list.html:100`, `lightning/core/ledger.py:164`, `lightning/ui/templates/register.html:217`, `lightning/ui/templates/budget.html:83`.
Do: (1) session: build the wait with a `{n}` key: "Too many wrong tries. Try again in {n} minutes." and "… in 1 hour." (Arabic agreement from IV-3BC2 if merged; else write the forms). (2) categories confirm: move the whole sentence into one `|tr(locale)` key. (3) ledger: the row label and the message in one key "Row {n}: the price and the exchange rate must be above zero." (4) register tooltip: `title="{{ 'Edit in this list'|tr(locale) }}"` without `r.ref`. (5) budget.html: `'Active: '+` and `e.message` go through `t()`.
Done when: `tests/test_arabic_no_english.py` gains a case that renders the locked-profile page and the categories page in Arabic and finds no Latin word other than names; `grep -n "r.ref }} —" lightning/ui/templates/register.html` is empty. `python -m pytest tests/test_arabic_no_english.py -q`.

## 3BD4 Import errors never show Python's text · S
Files: `lightning/bank_import_rows.py:277`, `lightning/bank_import_posting.py:50,127`, `lightning/investments/events.py:127`, `lightning/money_from_others.py:28`, `lightning/deposits/service.py:296`, `lightning/transactions/service.py:813`.
Do: replace each `{exc}` with a fixed plain sentence that says what to do ("This file is not a CSV Lightning can read. Save it from your bank as CSV and try again."; "Row {n}: the fee is not a number."), log the exception, and rewrite the developer wording as A14 voice ("Record this from the transaction screen." / "You can take out at most {amount} from this certificate." / "That transaction no longer exists."). Add Arabic for each.
Done when: `grep -rn "{exc}" lightning --include=*.py` finds none in a message shown to people, and `tests/test_messages_translated.py` (3BD2) still passes. `python -m pytest tests/test_bank_import*.py -q`.

## 3BD5 The validation page names the problem, not "Check your setup" · S
Files: `lightning/ui/templates/validation_error.html`, `lightning/ui/templates/phone/` (its phone twin if one exists: `ls lightning/ui/templates/phone | grep -i error`).
Do: title "That did not save" (Arabic: "ما اتحفظش"); the message as the lead line; one Back button to `request.headers.referer` when it is a same-origin path, else Overview/Home; drop the three fixed links. Follows A09 (answer first) and A14.
Done when: `tests/test_error_pages.py` posts an invalid amount and finds the new title and a Back link, and no "Check your setup". Check A16 by eye on a screenshot.
