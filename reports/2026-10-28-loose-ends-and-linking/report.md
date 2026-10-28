# Audit 9: loose ends after themes and sync, linking sections, and how the plan is filed

Date: 2026-10-28 · Author/reviewer: Claude
Repository: app · Reviewed commit: 9ca53bd994adfef49301b90cc4b924c39ff1cac5
Historical ID: audit-9

## Scope and method

The owner asked four things after the theme, multi-device sync and pairing work:
1. Are there loose ends?
2. What should be refactored?
3. Which smart features could link the sections together?
4. How are reports and issues categorised?

**How it was checked:**
- Read the source of `lightning/ui/themes.py`, `ui/entitlements.py`, `security/cosmetic_*.py`, `ui/static/theme-*` and `theme-kit/`.
- Read the source of `lightning/sync/`, `sync/journal/`, `runtime/journal_*.py` and `runtime/devices.py`.
- Mapped the links between records: the schema's foreign keys, the matchers, and the pages that link to each other.
- Ran `ruff check lightning tools --select F401,F841,F811,B023,B018`.
- Read `issues/README.md`, `reports/README.md`, the report template and the front matter of every item.

Every finding below was checked against the code at the commit above. Nothing was run on a phone or a PC.

## Findings

### A. Themes and paid themes (8J, 8L)

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| A1 | high | A licence fails unless its `asset_version` equals the app's exactly, so raising a paid theme's version in a release locks out every buyer until they redeem again. It should accept versions up to the app's own and say "Update" only for newer ones. One unknown item also rejects the whole licence. | `security/cosmetic_license.py:77-78`; `ui/entitlements.py:43` | 8U1 |
| A2 | medium | `tests/theme-runtime-profile.test.cjs` never runs. It is the only test that a paid theme being tried is never stored, and that another tab cannot put on an unowned theme. It passes when run by hand. | `tests/test_theme_build.py:28` runs only `theme-runtime.test.cjs` | 8U2 |
| A3 | medium | The "follow night" switch is kept in `localStorage`. The PC binds a random port at each launch, so every launch is a new origin and the switch resets. | `ui/static/theme-runtime.js:106-108`; `runtime/http.py:208` | 8U3 |
| A4 | medium | The held colour on themes is fixed at `#7FB2FF`. That is about 1.9:1 on the light Cotton and Dendera-day cards; the default `.held` is about 3.6:1 on dark cards. | `theme-surfaces.css:58,88`; `themes.generated.css:47,210` | 8U4 (with 8J §3) |
| A5 | low | PC stylesheets use hand-bumped `?v=` numbers while the phone bundle is content-hashed. Static files are cached for 24 h, so a forgotten bump mixes old CSS with new theme code. | `templates/base.html:13-16`; `partials/theme_head.html:3-4`; `ui/web.py:446` | 8U5 |
| A6 | low | `themes.generated.json` is re-read on every call. Licences are verified 1–3 times per page (reading the file, settings and signatures each time). | `ui/entitlements.py:50,148`; `ui/web.py:455-456` | 8U5 |
| A7 | low | Some unlock messages are wrong. Any non-409 error, including 5xx and rate limits, reads "code used or expired". "Unlocked for its other devices" shows even when sharing failed. | `ui/entitlements.py:175,203`; `ui/routes/settings.py:230` | 8U6 |
| A8 | low | The marketplace URL is written in four places and always opens the English page. | `settings/index.html:24`; `theme-runtime.js:45`; `desktop/window.py:154`; `MainActivity.java:81` | 8U6 |
| A9 | low | A paid theme's tier exists only in a test dict, the guideline and the website migration. Manifests have no `tier`. `compose_parts` is called only by tests, and it would miss `dendera-night`. | `tests/test_theme_build.py:181`; `security/cosmetic_parts.py:83` | 8U7 |
| A10 | low | Architecture and the theme kit still say entitlement, activation and the atomic cache are "still to build", but they are built. | `docs/ARCHITECTURE.md:526,532`; `theme-kit/README.md:133` | 8U7 |

### B. Multi-device sync and pairing (4A, 4B)

The older lending stack in `lightning/sync/*.py` is **not** dead. The Devices, Connect, Borrowed and Hand-back routes use it (`runtime/devices.py:21-24`, `runtime/app.py:760-800`), and `sync/identity.py` is shared with the journal. Retiring lending after J6 has no item.

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| B1 | high | Background sync swallows every error every 30 s, and Android reports any exception as "offline". There is no journal logging. As a result, a revoked or refused device, or one after a generation change, looks forever like "home offline". The last error should be kept and shown on Devices. | `runtime/journal_profile.py:281-284`; `runtime/journal_android.py:58`; `sync/journal/device.py:334-337` | 4J1 |
| B2 | high | "Paired" is decided from the device's own membership copy. A revoked device cannot receive the rotated list, so it keeps saying "paired, reconnects automatically". Inferred from the code, not run. 4A §7 promises that devices learn of a revocation on contact. | `runtime/journal_pairing.py:52`; `journal_views/devices.html:38`; `journal_pairing.py:169-177` | 4J2 |
| B3 | medium | An offer is valid only if `expires` is at most 600 + 60 s ahead of the joiner's own clock. A phone more than about a minute behind, or ten minutes ahead, can never pair, and is told "offer expired or home identity changed". | `sync/journal/pairing.py:25,76-78`; `tests/test_pairing_clocks.py:23` | 4J3 |
| B4 | medium | When pairing expires part-way, the poll route swallows the errors from `resume()` and `finish()`, so the joiner stays "pending". Any `screen()` failure reads "pairing disabled". A failed bind of the discovery port is silent. | `runtime/journal_ui_routes.py:47-49,150-159`; `journal_profile.py:278` | 4J4 |
| B5 | medium | Production imports the lab module: `LabServer` and `open_lab`. The production join says "This preview joins compatible dummy replicas". | `journal_profile.py:259`; `journal_setup.py:18`; `journal_pairing.py:96-97` | 4K1 |
| B6 | low | Canonical JSON plus hash is rebuilt in about ten places outside `codec`. The pairing limits (12, 3, 600) are bare numbers. `screen()` reads `time.time()` and `desk._state()` instead of the desk clock. | `finance.py:462`; `journal_move.py:29-32`; `backups.py:263,281,315`; `cutover.py:68-164`; `pairing.py:77,191,260` | 4K2 |
| B7 | low | `cloud.py` and `local.py` import each other's error classes inside functions. They need one `journal/errors.py`. | `cloud.py:127,150`; `local.py:239`; `ui/journal.py:300` | 4K3 |
| B8 | low | There are two pairing clients: `NewJournalReplica` and `NearbyPairing`. They already differ on the "waiting" stage. | `runtime/journal_enrollment.py`; `runtime/journal_pairing.py` | 4K4 |
| B9 | low | Whether a profile is a journal profile is decided by the presence of a marker file. A stray or deleted marker silently changes the role it opens in. | `runtime/devices.py:130,171` | 4K5 |
| B10 | low | Dead or misplaced code: a cancel branch that can never run, guards placed above docstrings, a stale `sync/__init__` docstring, unused `code_by_id` and `offer`. | `journal_pairing.py:204,222`; `devices.py:139,171,190`; `cutover.py:150`; `journal_enrollment.py:66` | 4K5 |

### C. Whole codebase

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| C1 | low | Ruff reports 58 findings: 32 unused imports, 16 unused variables, one name defined twice, and B023/B018. The B023/B018 ones checked here are false positives, for example `node.model` deliberately reads the record. Ruff is not in CI or `pyproject.toml`, so unused imports keep coming back. | the ruff command above | 1J |
| C2 | low | About 48 remote branches are more than two weeks old. Squash merges hide which of them are merged. | `git for-each-ref refs/remotes` | stale-check skill |
| C3 | low | NOW.md claims are old. The journal claim dates from 2026-10-16 and the restore claim from 2026-10-05. | `NOW.md` *Claimed* | owners of the claims |

### D. Linking the sections together

What is linked today:
- **Stored links:** transaction → counterparty, plan → transaction, reserve ↔ transaction (partial amounts), reimbursement claims ↔ receipts, certificate interest → receipt, import row → transaction, gam'eya funding and payout accounts, and broker pockets.
- **Worked out on read:** a transaction's budget line, and budget lines that come from bills and loans.

The gaps:
- A transaction has two half pages: `/transactions/{id}` shows its budget line and reserve, while `/activity/{id}` shows its source, plan and claim.
- Counterparties are only a list (`ui/routes/counterparties.py`).
- An account never shows what depends on it.
- A reserve cannot name the bill it saves for.

| ID | Idea, best value for effort first | Builds on | Size | Follow-up |
| --- | --- | --- | --- | --- |
| D1 | **What this touched.** One page per transaction showing its budget line and what is left, the bill or loan it settled, its reserve, claim, source, rule and history. Suggested links are one tap away. | `workflows/activity.py` `summary`; `ui/routes/transactions.py` `transaction_detail`; `reserves.py` | S–M | 7T1 |
| D2 | **A page per counterparty.** Spending by month, planned items, reserves, what they owe you, money held for them, aliases and rules. | `counterparties.py`; `ReportingService.spending_by_counterparty`; `money_from_others` | M | 7T2 |
| D3 | **What depends on this account.** The bills it pays, gam'eyas, certificate interest it receives, reserves, and the first date it goes below zero. Archiving warns first. | account columns on `planned_items`, `gameya_terms`, `cd_certificates`, `cash_reserves`; `planning/dated_cash.py` | S–M | 7T3 |
| D4 | **Tag totals.** `#umrah2026` gives one total across categories and accounts, compared with its reserve. | `transactions/tags.py`; `reserve_transaction_links`; `saved_views.py` | S | 7T4 |
| D5 | **Salary-day cascade.** Posting the real salary opens one Needs you card: bills before the next payday, reserves to refill, goal top-ups and safe to spend. The payday allocation opens pre-filled. | `workflows/salary_setup.py`; `planning/funding.py`; `workflows/review.py` | M | 7T5 (with 7L2) |
| D6 | **A reserve tied to its bill.** A yearly bill shows how much is saved toward it. Paying it uses the reserve. Plans still move no money. | `cash_reserves`; plan matching; `CashForecaster.goal_needs` | M | 7T6, after 7M and 7R |
| D7 | Pair reimbursements in Needs you. | `reimbursements.py` | S–M | already 7L4 |
| D8 | A budget row links to its bill and its transactions. | `BudgetService.scheduled_payments` | S | already 3G §4.6 |

D1–D4 use only what is already stored and add no financial rule. Every figure stays in Python services.

### E. How reports and issues are categorised

What works:
- Coded items with one file each.
- A generated index checked by a test.
- Dated report folders with a template.

What does not:

| ID | Observation | Evidence | Suggested rule |
| --- | --- | --- | --- |
| E1 | `type` mixes **what** an item is with **who** must act. 7M, 7R and 7S are bugs (wrong money, or a link silently dropped) but filed as `owner`. 12 of 72 items are `owner`, and only 10 are `bug`. | front matter of 7M, 7R, 7S, 3AH, 9L | Keep `type` for the nature of the item. Add `needs: owner` (and a reason) for items waiting on the owner. The index shows a marker. |
| E2 | Bug severity is free text in the body. Three of the ten bugs have none (2U, 3U, 5I). The index cannot sort by it. | `issues/*/2U*`, `3U*`, `5I*` | Make `severity: high/medium/low` required for bugs and show it in INDEX. |
| E3 | `area` has 23 values that overlap: `phone`/`android`, `product`/`ui`, `architecture`/`tools`, `devices`/`desktop`, `appearance`/`website`, `performance`. `product` (7 items) is a catch-all. | front-matter count | Use a fixed list in `tools/issues.py`, checked like `TYPES`. |
| E4 | Six items say `building` with no claim in NOW.md: 2B, 3H, 5G, 6A, 8J and 8L (4B may sit under the journal claim). The README says `building` means a claim or a `/take`. | NOW.md *Claimed* has only 4A and 2A | `tools/issues.py --check` warns when a `building` item has no claim. |
| E5 | Some items sit in the wrong milestone. The app's theme features (8J, 8K, 8L and 8T, area `appearance`) are in Website. 9L (legacy mode opens a plaintext database on real-data paths) is a real-money safety concern parked in Later. 6E (logos, area `accounts`) is in Market data. | INDEX | Move them with new codes (`was:`), only after the owner agrees. |
| E6 | Several items are designs or audits, not items: 4B is 99 KB, 3H 48 KB, 4A 42 KB, 3G 30 KB, 5G 28 KB and 6A 24 KB. 3S says it holds "18 places not yet filed". 3J, which folds the v1.1 review into Architecture, has been open since 10-13. | file sizes | Move the parts that are built into Architecture. Split the rest into numbered steps. |
| E7 | The `done:` lists are not in order. Milestone order is "worked in order", but milestone 8 moves while 2 is still open. | milestone READMEs | Sort `done:` in the generator. State that milestones mean priority, not strict order. |
| E8 | Of 14 reports, 9 lack the template's "Reviewed commit" line, 5 have no `evidence/` folder (which the README requires), and only 6 have dated follow-ups. | `grep -L 'Reviewed commit' reports/*/report.md` | Add a docs-structure test for the header lines, or relax the README where the evidence is in the text. |
| E9 | The report catalogue is not in date order. Its IDs mix `audit-N` with slugs. Audit 5 (10-21) comes after Audit 4 (10-23). It has no kind column (audit, review, release record, research) and no status column (open follow-ups or closed). "Users' main questions" is reference material, not an audit. | `reports/README.md` | Sort by date. Add **Kind** and **Open follow-ups** columns. Move reference material to `docs/`, which the owner must agree to (`docs/` holds only the map and four references). |

## Validation and limits

- Lint ran with `ruff check lightning tools --select F401,F841,F811,B023,B018` and found 58 issues. A1–A3, B1–B3 and D1's two-page split were re-read at the lines cited.
- B2 is inferred from the code and was not run against a revoked device. A4's contrast ratios are computed from the hex values, not measured on screen. A3's Android behavior was not checked.
- No phone or PC was used. No financial figure was changed, so the Mohab and number audits do not apply.

## Dated follow-ups

None yet.
