# HTTP surface (as built)

Lightning has **no public API**. It serves server-rendered pages and form posts to its own UI on
`127.0.0.1`. There is no OpenAPI document. The routes below were extracted from the `@router.get/post`
decorators in `lightning/ui/routes/*.py` and `lightning/runtime/*.py` (**326 route decorators**: 276 UI, 50 runtime).
Treat this as an internal map, **not a stable contract**: paths can change with the UI.

## Common rules (all routes)

| Rule | Detail |
|---|---|
| Binding | `127.0.0.1` only, random/chosen port (`runtime/app.py` `Host`). |
| Auth | Profile must be unlocked. Locked → profile chooser pages. No users, no tokens in headers. |
| Writes | Form `POST` with the session token (`__session`) or `csrf` on profile routes; a stale token is refused. |
| Limits | Per-path form field/part/file size limits (`_form_*_limit`). |
| Responses | HTML pages; redirects after success; plain-language error pages (`error.html`, `not_found.html`); a few JSON endpoints. |
| Read-only role | Writes explain "This is a read-only copy". |

## Route groups

Counts are decorators per file. Prefixes are set where each router is included (`ui/web.py` loops `include_router`; per-router prefixes **not extracted here**, so paths below are as written in the decorator).

| Group (file) | # | Examples | Purpose |
|---|---|---|---|
| `dashboard` | 17 | `GET /`, `POST /setup/salary`, `POST /setup/currency` | Overview, first-run setup |
| `accounts` | 27 | `GET /{id}/convert`, `POST /{id}/convert`, `GET /convert/quote`, `GET /currencies` | Accounts, conversion, currencies |
| `register` | — | per-account registers | Add/edit transactions with submission token |
| `transactions` | 24 | `GET/POST /transactions/{id}/edit-popup`, `.../ownership/edit` | Edit, convert, ownership |
| `activity` | 2 | `GET /{id}`, `POST /{id}/apply` | Review one activity item |
| `merge`, `workbench` | 3, 3 | `POST /transactions/merge`, `POST /transactions/find-replace`, `POST /import/{batch}/undo` | Bulk tools |
| `bank_imports` | 8 | `POST /{account}/import`, `.../import/map`, `GET .../ai-template.csv` | CSV import |
| `sms` | 5 | `POST /allow`, `/paste`, `/assign`, `/dismiss` | SMS review (phone) |
| `categories`, `counterparties`, `rules` | 8, 1, 7 | `POST /new`, `GET /{id}/past`, `POST /{id}/apply` | Naming and rules |
| `budget`, `reserves`, `payday` | 23, 6, 2 | `POST /tracking`, `POST /emergency`, `POST /apply` | Plan |
| `planning` | 18 | `GET /recurring`, `GET /loans`, `GET /purchases/new` | Bills, loans, forecast |
| `investments` | 28 | `GET /planner`, `GET /holding/{asset}`, `GET /targets` | Holdings and planner |
| `deposits`, `gameya`, `physical_items` | 10, 5, 6 | `POST /{account}/purchase`, `POST /{account}/instalment` | Instruments |
| `analysis`, `birdview`, `financial_health`, `weekly`, `zakat`, `integrity`, `history`, `search` | 4,4,1,5,3,—,1,1 | `GET /reports`, `GET /financial-health`, `GET /zakat`, `GET /search`, `POST /{operation}` (undo/redo) | Reports and checks |
| `exports` | 8 | `GET /all`, `POST /transactions`, `GET /views/{id}` | Data export |
| `settings` | 12 | `POST /currency`, `POST /fx-rate`, `POST /theme`, `POST /theme/unlock` | Settings |
| runtime `app` | 40 | `GET /profiles`, `GET /profiles/health`, `POST /profiles/locale`, `POST /__activity`, `POST /sync/hand-back` | Profiles, lock, health, device hand-back |
| runtime `journal_*` | 10 | `GET /journal`, `POST /journal/sync`, `GET/POST /profiles/journal/setup`, `GET/POST /journal/recover` | Edit-journal UI and setup |

### JSON endpoints worth knowing

| Route | Returns |
|---|---|
| `GET /profiles/health` | Liveness for the launcher |
| `POST /__activity` | Reports user activity for the idle lock; returns `{"ok": true, "locked": bool, "session": token}` |
| `GET /reminders/due.json` | Due reminders |
| `GET /{account}/import/ai-reference.json` | Import helper data |

**Decision D-009:** these routes are the bundled UI's internal surface with no stability promise, so per-endpoint request/response schemas are intentionally not documented; the path list can be regenerated with `grep -rnE "@\w+\.(get|post)\(" lightning/ui/routes lightning/runtime`.
