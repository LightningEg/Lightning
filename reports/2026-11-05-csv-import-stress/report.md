# CSV import stress test: where it breaks and how to rebuild it

Date: 2026-11-05 · Author/reviewer: Claude Opus 5.5 (owner-requested audit; findings only, no fixes)
Repository: app · Reviewed commit: cff8be1 (branch `claude/import-other-app-exports`, which adds the group column, balance rows and the category-name list)

## Scope and method

The question: across the files real people bring, how often does the CSV import do the right thing on its own, where
does it silently do the wrong thing, and what should change? Started by the owner's 377-row export
([feedback FB1](../../feedback/2026-11-05-csv-import-and-phone-update.md)).

Thirty-four dummy files, built to cover seven kinds of user, went through the same path as the app:
`POST /accounts/{id}/import`, the column suggestion accepted as offered, the review built, then **Post ready rows**
with the review's own defaults, in a fresh profile each (NBE, CIB and THNDR accounts). Six probes then matched
columns by hand to look past the column step. Excel and PDF readers, multi-file uploads, the phone layout and
SMS were out of scope.

- Harness: [`evidence/stress_import.py`](evidence/stress_import.py) → [`evidence/results.json`](evidence/results.json)
- Probes: [`evidence/probes.py`](evidence/probes.py) → [`evidence/probes.txt`](evidence/probes.txt)

## Who imports, and what they bring

| User | What they bring | What they expect |
| --- | --- | --- |
| U1 Monthly bank downloader | NBE/CIB/QNB CSV: Debit/Credit or signed Amount, a Description, often a Balance, a preamble and a totals footer | Merchants recognised, categories from last month, no duplicates with the overlap |
| U2 AI-to-CSV user | Lightning's template, filled by an AI tool from a PDF | Rows post with no column step |
| U3 Mover from another app | Money Manager, Wallet, Masareef, Excel tracker: their own categories, groups, accounts, splits, opening balances, positive amounts with a type column | One upload brings their history in, mapped once |
| U4 Arabic Excel user | Arabic headers, Arabic-Indic digits, a file Excel saved as cp1256 or UTF-16 | It opens |
| U5 Several accounts in one file | Account column with two banks and a wallet | Each row lands in its account |
| U6 Years of history | 1,000–20,000 rows | It finishes, and the page does not freeze |
| U7 Repeat importer | This month's file overlapping last month's | Overlap recognised, nothing posted twice |

## Scoreboard

"Ready" is what posts with one click; "needs" waits for a choice; "err" must be fixed; "dup" defaults to skip.

| ID | User | File | Outcome | Ready / rows |
| --- | --- | --- | --- | --- |
| A1 | U2 | Lightning template | Works; "Transportation" alone is ambiguous (seed has two) | 2 / 3 |
| A2 | U1 | Debit/Credit, day-first, Balance | Columns right; Description → Notes, so no counterparty and every row needs a category | 0 / 3 |
| A3 | U1 | Posting and Value date | Posting date chosen, no question | 0 / 2 |
| A4 | U1 | Positive amounts + DR/CR | **DR/CR column mapped to Category; spending would post as income** | 0 / 3 |
| A5 | U1 | `(12,500.00)`, `EGP 25,000.00`, `1.234,56` | All read correctly | 0 / 4 |
| A6 | U4 | Arabic headers, Arabic digits | Column step suggests nothing; digits read fine once matched (P3) | blocked |
| A7 | U1 | Preamble above the header | Refused: "Could not determine delimiter" | blocked |
| A8 | U1 | Totals footer, blank line | Footer rows are errors the person must skip | 0 / 4 |
| A9 | U1 | Semicolons, comma decimals | Works | 0 / 2 |
| A10 | U4 | Saved as cp1256 | Refused: save as UTF-8 | blocked |
| A11 | U4 | Saved as UTF-16 | Refused: save as UTF-8 | blocked |
| A12 | U1 | Month-first dates | **10/02/2026 silently read as 10 February; only 10/13 errors** (P1) | 0 / 2 |
| A13 | U1/U3 | Dates with a time | Every row an error | 0 / 2 |
| A14 | U1 | `01-Oct-2026`, `2 Oct 26` | Errors; `03/10/26` works | 0 / 3 |
| A15 | U1 | Zero amount (waived fee) | Error instead of skip | 0 / 2 |
| A16 | U1 | Future-dated hold | Error instead of skip | 0 / 2 |
| A17 | U1 | Balance column only | Blocked: no amount | blocked |
| A18 | U1 | Newest first, same-day salary | Same-day order handled | 0 / 3 |
| B1 | U3 | Money Manager | **No Amount suggested ("EGP" column); positive amounts + Income/Expense have no correct mapping; month-first dates** | blocked |
| B2 | U3 | Wallet | ISO timestamps fail every row; **a USD row would post as EGP** (P2) | 0 / 3 |
| B3 | U3 | `Personal:Food`, `Work > Transportation` | Only `›` is understood | 0 / 3 |
| B4 | U3 | Group + unknown names (owner's case) | Group resolves; balance row skipped; one name to set | 2 / 5 |
| B5 | U5 | Account column, two banks | **Account column ignored: the CIB row lands in NBE** | 2 / 3 |
| B6 | U3 | Split lines | Each line flagged as the other's duplicate; split column ignored | 0 / 2 |
| B7 | U3 | Transfer written twice, ownership pair | Second copy flagged duplicate; pair needs two choices | 0 / 4 |
| C1 | U7 | Same file again | Both rows duplicates, skipped | 0 / 2 |
| C2 | U7 | Overlapping month | Overlap caught; new row posts | 1 / 4 |
| C3 | U1 | `UBER *TRIP HELP.UBER.COM` | No clean name, nothing suggested | 0 / 3 |
| D1 | — | Formula-looking text | Stored as text, shown escaped | — |
| D2 | — | Duplicate headers | Refused with a clear message | blocked |
| D3 | — | 20,000-character cell | Accepted | — |
| D4 | U6 | 1,000 rows | Review 1.1 s, **4.9 MB page** | — |
| D5 | U6 | 5,000 rows | Review 4.8 s, **25 MB page**, post 6.5 s | — |
| D6 | U6 | Over 5 MB | Refused with a clear message | blocked |

In D4–D5 the duplicate counts come from the generator repeating date-and-amount pairs; the times and page sizes stand.

## Findings

| ID | Severity | Observation and expected behaviour | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Month-first files are read day-first, silently.** Rows where both parts are 12 or less become wrong dates; only rows with a 13+ first part error. The file as a whole proves its order; read it once per file, ask once when unclear. | A12, B1, P1 | IT-7AA1 |
| F2 | high | **Direction columns are not understood.** Positive amounts with DR/CR, Debit/Credit text or Income/Expense have no correct mapping; "type" is even an alias for Category, so DR/CR becomes a category name. Spending would post as income. | A4, B1, P4 | IT-7AA2 |
| F3 | high | **Currency column ignored.** A USD row posts its USD figure into an EGP account. A row in another currency must never post as the account's own. | B2, P2 | IT-7AA3 |
| F4 | high | **Account column ignored.** Rows for another account post into the one being imported. | B5 | IT-7Z2 |
| F5 | high | **Large files make a page the app cannot hold.** 5,000 rows render a 25 MB page in 4.8 s; the Windows WebView and the phone stall long before. | D4, D5 | IT-7AA8 |
| F6 | medium | **Bank descriptions never become counterparties.** Description goes to Notes, so history, aliases, the per-name grouping and "use this category next time" cannot work on bank statements, the most common file. A cleaned merchant name ("UBER *TRIP…" → Uber) should fill Counterparty, with the raw text kept in Notes. | A2, C3, P6 | IT-7AA4 |
| F7 | medium | **Files are refused or fail on their layout, not their content:** preamble lines (cryptic delimiter error), cp1256 and UTF-16 encodings, Arabic headers, dates with times or month names, balance-only statements. | A6, A7, A10, A11, A13, A14, A17 | IT-7AA5 |
| F8 | medium | **Rows that are clearly not transactions are errors, not skips:** totals footers, zero amounts, future holds. | A8, A15, A16 | IT-7AA6 |
| F9 | medium | **Category paths in one column** (`Food:Groceries`, `Work > Transportation`, `Food/Groceries`) are not split; only `›` works. Subcategory columns are not used. | B3, B1 | IT-7AA7 |
| F10 | medium | **Splits and paired movements** arrive as duplicates of each other or two separate choices. | B6, B7 | IT-7Z3, IT-7AA7 |
| F11 | low | The seed has two categories called Transportation, so a plain file naming it always asks. | A1, P5 | IT-7AA7 |
| F12 | low | No check against the statement's Balance column, though it would prove nothing was missed or doubled. | A2 | IT-7AA9 |
| F13 | low | Choices made in the review are not remembered for the next file from the same source. | B4 | IT-7Z1 |

What held up: amount formats (brackets, codes, thousands, European decimals, Arabic digits), semicolons, repeat and
overlap detection, the owner-case fixes, unique headers, the size limit and formula text.

## Proposed architecture

Today one function reads a file and the review guesses per row. The failures above are decisions about a **whole
file** made row by row, or not made at all. The proposal is a profiling stage between reading and reviewing:

```
bytes ─▶ 1 Read ─▶ 2 Profile the file ─▶ 3 One question screen ─▶ 4 Normalise rows ─▶ 5 Resolve ─▶ 6 Review ─▶ 7 Post + reconcile
```

1. **Read** (`statement_files`): detect the encoding (BOM, UTF-8, then cp1256 with a visible preview), the delimiter,
   and the header row as the first row with two or more known column names; keep preamble lines as file notes.
2. **Profile** (new, pure, no database): one pass over every row builds a `FileProfile`: date order
   (ISO / day-first / month-first / with time / month names, with the evidence counts), amount model (signed,
   in/out, amount plus direction column with its values, balance only), currency per row, account per row,
   category path separator, footer and zero rows, and a source guess (bank, a named app, Lightning's own). It is
   stored with the batch so the review and posting read the same decisions.
3. **One question screen** replaces the column step. It shows what the profile decided, each with two sample rows,
   and asks only what the profile could not decide ("Is 10/02/2026 the 10th of February or the 2nd of October?",
   "In the Type column, which value means money out?"). Answers are saved per header signature, as mappings are now.
4. **Normalise** applies the profile to every row: date, signed amount, currency, account, merchant name cleaned
   from the description (a small rules table, kept with the counterparty aliases), category path split into group
   and name. Footer, zero and future rows become skip rows with a reason, not errors.
5. **Resolve** keeps one ordered chain per row and records which step answered: rule → group › name → saved name
   map → counterparty default → history → suggestion only. Foreign-currency rows wait for the account's amount;
   rows for another account move to that account's batch.
6. **Review** is paged by name group and renders rows on demand, so the page stays small at any size; the
   "Your file's categories" list and the bulk bar act on the whole batch on the server, not on the rendered rows.
7. **Post and reconcile**: posting runs in chunks with progress; when the file has a Balance column, the account's
   balance after each statement day is compared and gaps or doubles are shown before the person leaves.

Per-app presets (IT-7C) then become saved profiles, not separate code.

## Order of work

By rows saved and harm avoided: F1, F2, F3 and F4 first (they post wrong money silently), then F5 (large files
cannot be used at all), then F6 (most bank files), then F7–F8, then the rest.

## Validation and limits

Run on Linux with dummy files only, clock fixed to 2026-11-05: `python reports/2026-11-05-csv-import-stress/evidence/stress_import.py`
and `.../probes.py`. Times are one run on a cloud container, not a Windows PC or phone; page weight is measured,
WebView behaviour at that weight is inferred. Excel and PDF readers, multi-file upload, the phone layout and Arabic
review screens were not exercised.

## Dated follow-ups

- 2026-11-05: the owner asked for a better flow for large files ("smarter buttons and features"); planned only, as IT-7AB (summary first, post in rounds, group by question, smart buttons, quick mode, undo).
- 2026-11-06: IT-7AA1 built; the harness's A12, A13 and A14 now read every date correctly (B1 still blocked at the column step until 7AA2).
- 2026-11-06: IT-7AA2 built; A4 (DR/CR beside positive amounts) now posts spending as money out.
- 2026-11-06: IT-7AA3 built; B2's USD row is now an error row and posts nothing (reference amounts and the account column, F4, remain).
- 2026-11-06: IT-7Z2 safe part built; B5's CIB row no longer posts into NBE (it is an error row). The split into one batch per account remains.
- 2026-11-06: IT-7AA8 part built; D5 (5,000 rows) review page 25 MB to 0.8 MB and 4.7 s to 2.8 s (the preview computation, about 1.6 s, and posting in chunks remain).
- 2026-11-06: IT-7AA6 built; totals footers, zero amounts and future holds open as skipped rows with a reason (A8, A15, A16 have no error rows).
- 2026-11-06: IT-7AA5 built; A6, A7, A10, A11 and A17 reach the review (cp1256 is read without a visible preview yet).
