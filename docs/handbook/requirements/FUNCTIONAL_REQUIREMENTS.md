# Functional Requirements (as built)

Status: **I** Implemented (code + tests found) · **P** Partial · **U** Unknown. Priority is MoSCoW and
is an inference from the Overview's decisions unless noted (decided, D-005).
Verification: test files are examples; run `pytest -q tests/<file>`.

## Profiles and security

| ID | Requirement | Actor | Behaviour | Rules | Code | Pri | Stat | Verified by |
|---|---|---|---|---|---|---|---|---|
| FR-001 | Create a password-protected profile | User | Setup shows suggested password, recovery key (once), security question | Password of any length; 12-digit key | `security/keys.py`, `runtime/session.py` | Must | I | `tests/test_profile_session.py` |
| FR-002 | Unlock/lock/switch profile | User | Password opens; idle lock 15 min | Wrong tries throttled: 5 free, then 1/5/15/60 min | `runtime/session.py`, `runtime/app.py` | Must | I | `tests/test_profile_session.py` |
| FR-003 | Recover access | User | Recovery key + answer set a new password | Any two of three secrets restore the third | `security/keys.py` | Must | I | `tests/test_profile_session.py` (U: exact file) |
| FR-004 | Fingerprint unlock (phone) | User | Opt-in third wrapping of data key | Invalidated when fingerprints change | `security/biometric.py` | Should | I | `tests/test_biometric_unlock.py` |
| FR-005 | Backup and restore | User | Daily encrypted backup; restore to same-named profile | Verified snapshot; promotion P0–P5 | `database/backup.py`, `runtime/restore.py` | Must | P (restore safety in progress, 03a) | `tests/test_database_promotion*.py` |

## Accounts and ledger

| ID | Requirement | Behaviour / rules | Code | Pri | Stat |
|---|---|---|---|---|---|
| FR-010 | Manage accounts | Types: cash, bank, deposit, brokerage, physical asset, etc.; one currency each | `accounts/`, `workflows/accounts.py` | Must | I |
| FR-011 | Opening balances | Atomic account + opening workflow | `workflows/accounts.py` | Must | I |
| FR-012 | Check an account against the bank | Small difference posts one adjustment (ADJ); checked months lock | `reconciliation.py`, migration 0056 | Should | I |
| FR-020 | Record money in/out | One-time submission token; cannot overdraw cash/bank | `transactions/`, `ui/routes/register.py` | Must | I |
| FR-021 | Transfer between own accounts | Two-sided, nets to zero | `transactions/` | Must | I |
| FR-022 | Edit, void, undo | Audited; recoverable | `transactions/`, `undo.py`, `/history/{operation}` | Must | I |
| FR-023 | Search transactions | Free text + filters; saved views | `ui/routes/search.py`, `saved_views.py` | Must | I |
| FR-024 | Merge / find-replace / bulk apply | Preview and one undo | `ui/routes/merge.py`, `workbench.py` | Should | I |
| FR-025 | Currency conversion | Executed rate; fee as OUTFLOW | `transactions/conversion.py` | Must | I |

## Names, categories, rules

| ID | Requirement | Rules | Code | Pri | Stat |
|---|---|---|---|---|---|
| FR-030 | Category tree | Used ones archived not deleted | `categories/` | Must | I |
| FR-031 | Counterparties and aliases | Similar names are suggestions; never silently merged | `counterparties.py` | Must | I |
| FR-032 | Rules | Condition ranking; splits must add up; apply to past with one undo | `rules/` | Should | I |
| FR-033 | Reimbursements | Claims linked to ledger lines and receipts | `reimbursements.py` | Could | I |

## Import

| ID | Requirement | Rules | Code | Pri | Stat |
|---|---|---|---|---|---|
| FR-040 | CSV bank import | Map, stage, review, post; duplicates detected | `bank_imports.py` | Must | I |
| FR-041 | SMS import (phone) | READ_SMS; never phone-number senders; reviewed | `sms_imports.py` | Should | I |
| FR-042 | PDF/Excel statements | — | — | Could | Not implemented (NF-7B) |

## Budget, plan, safety

| ID | Requirement | Rules | Code | Pri | Stat |
|---|---|---|---|---|---|
| FR-050 | Monthly budget with carry-over | Plan only | `budgeting/` | Must | I |
| FR-051 | Cash reserves | Lowers Free cash | `reserves.py` | Must | I |
| FR-052 | Emergency fund | Default months of spending | `reserves.py` | Should | I |
| FR-053 | Funded payday allocation | Optional | `ui/routes/payday.py` | Could | I |
| FR-060 | Recurring bills and income | Public-holiday shift not supported (NF-7I) | `planning/` | Must | P |
| FR-061 | Loans and instalments | Schedules, not debt accounts | `planning/` | Should | I |
| FR-062 | Cash forecast, Safe to spend | Obligations count, forecasts never | `planning/forecast.py`, `position.py` | Must | I |
| FR-063 | Financial health ratios | — | `planning/health.py` | Should | I |
| FR-064 | Weekly review and reminders | Computed on read | `workflows/weekly.py`, `reminders.py` | Could | I |

## Investments and instruments

| ID | Requirement | Rules | Code | Pri | Stat |
|---|---|---|---|---|---|
| FR-070 | Buy/sell/dividend | Atomic via workflow | `workflows/investment_entry.py` | Must | I |
| FR-071 | Positions and returns | One computation, shared | `investments/`, `planning/position.py` | Must | I |
| FR-072 | Prices: packs, live, manual | Typed beats fetched | `market/`, `workflows/live_prices.py` | Must | I |
| FR-073 | Month-end revaluation | Zero-quantity VAL journal | `reevaluations.py` | Must | I |
| FR-074 | Per-purchase lots, ROI, splits | — | — | Should | Not implemented (5A–5E) |
| FR-080 | Certificates of deposit | Terms, lock-up shown separately | `deposits/` | Should | I |
| FR-081 | Gam'eya | Instalments, payout | `deposits/`, `ui/routes/gameya.py` | Should | I (early-turn display bug BV-5I) |
| FR-082 | Physical gold | Weight × karat valuation | `physical_items.py` | Should | I |
| FR-090 | Foreign cash with dated FX | Stored values never rewritten | `fx.py` | Must | I |
| FR-091 | FX gain tracking | Average cost per currency | `reporting/fx_positions.py` | Should | I |

## Reporting

| ID | Requirement | Code | Pri | Stat |
|---|---|---|---|---|
| FR-100 | Overview (net worth, savings rate) | `ui/routes/dashboard.py`, `reporting/` | Must | I |
| FR-101 | Spending analysis and compare | `ui/routes/analysis.py` | Must | I |
| FR-102 | Zakat estimate | `zakat.py` | Could | I |
| FR-103 | Exports (CSV, AI workbook) | `ui/routes/exports.py`, `workflows/data_export.py`, `ai_analysis.py` | Should | I |
| FR-104 | Data integrity checks | `integrity.py` | Should | I |

## Devices, themes, language

| ID | Requirement | Code | Pri | Stat |
|---|---|---|---|---|
| FR-110 | Pair devices (number-match, password) | `sync/journal/pairing*.py` | Should | P (acceptance held: 2C, 4A) |
| FR-111 | Edit anywhere, one home confirms | `sync/journal/` | Should | P |
| FR-112 | Local-network sync with pinned TLS | `sync/journal/local.py` | Should | P |
| FR-113 | Free-tier cloud relay | `cloudflare/journal`, `sync/journal/cloud.py` | Could | P (live config deferred) |
| FR-120 | Cosmetic themes, optional purchase | `security/cosmetic_*.py`, `/settings/theme*` | Could | P |
| FR-130 | English and Egyptian Arabic (RTL) | `ui/i18n*.py` | Must | I |
