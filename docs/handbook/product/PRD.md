# Product Requirements (as built)

Source of truth for decisions: [`docs/PROJECT_OVERVIEW.md`](../../PROJECT_OVERVIEW.md). This page
restates it in PRD shape and adds status. IDs link to [FUNCTIONAL_REQUIREMENTS](../requirements/FUNCTIONAL_REQUIREMENTS.md).

## 1. Overview and vision

Lightning shows **where money is held**, **what it is invested in**, **how spending compares with
the plan**, and **how net worth changes**. The core loop is: record or import activity → resolve
unclear names/categories → read the analysis → save towards goals.

Vision (owner decisions, Overview §1–2): every number has one name and one formula; the app needs
no account and no server; people may use it with their real money.

## 2. Problem and context

Salaried Egyptians hold money across banks, wallets, cash, gold, certificates, savings circles
(gam'eya) and brokerages, often in EGP and USD. Generic budgeting apps do not model Egyptian
instruments or bank formats, and cloud apps require handing data to a server. Competitor research
is in [`docs/COMPETITION.md`](../../COMPETITION.md).

## 3. Audience, personas, stakeholders

| Persona | Needs |
|---|---|
| **Mohab** (reference user: 31, salaried, Cairo) | Monthly budget, safe-to-spend, savings, a few investments, a gam'eya, some USD. Lives a full year in `tests/test_mohab_year.py`. |
| Partner / household member | Same ledger from the phone (multi-device edit journal). |
| Contributor | Fixes issues via forks and PRs ([CONTRIBUTING.md](../../../CONTRIBUTING.md)). |

Stakeholders: the **owner** (decides product, merges, releases); AI contributors (Claude, Codex, Luna) coordinating through `NOW.md`; users via the feedback process (`feedback/`).

## 4. Roles and permissions

There are no user accounts. Access is by **profile password** (one profile = one encrypted database). Session *roles* are about devices, not people (`lightning/runtime/roles.py`):

| Role | Can write? | Meaning |
|---|---|---|
| home | yes | The device that owns the ledger (normally the phone). |
| borrower | yes | A PC working on a borrowed copy, handing back later. |
| reader | no | A real read-only SQLite connection. |

## 5. Scope

**In scope:** accounts and cash; transactions and transfers; categories, counterparties and rules; budgets and reserves; scheduled bills, income and loans; certificates and gam'eya; investments with prices; physical gold; FX; zakat estimate; CSV/SMS import; reports and exports; encrypted profiles, backups; multi-device sync.

**Out of scope (owner decisions):** credit-card and loan-interest accounting, money owed *to* you, any functional paywall, comparison pages naming other apps on the website, cloud accounts.

## 6. Features

Each has a status. "Implemented" means code plus tests exist; the owner still holds some acceptance checks (Overview §9).

| Feature | Purpose | Users | Rules that matter | Depends on | Status | FR |
|---|---|---|---|---|---|---|
| Profiles and encryption | Keep data private and local | All | One password opens; two secrets change it | `security/`, `runtime/session.py` | Implemented | FR-001–004 |
| Accounts and balances | Say *where* money is | All | One currency per account; cash asset per currency | `accounts/`, `assets/` | Implemented | FR-010–012 |
| Transactions ledger | Single source of real money | All | Only `TransactionService` writes postings | `transactions/`, `core/ledger.py` | Implemented | FR-020–025 |
| Categories, counterparties, rules | Sort activity consistently | All | Used categories archive, never delete; never silently merge names | `categories/`, `counterparties.py`, `rules/` | Implemented | FR-030–033 |
| Import (CSV, SMS) | Get a month in minutes | Mohab | Nothing posts unreviewed | `bank_imports.py`, `sms_imports.py` | Implemented; PDF/Excel planned (NF-7B) | FR-040–042 |
| Budget and reserves | Plan spending, set money aside | All | Reserve lowers Free cash; budget limit does not | `budgeting/`, `reserves.py` | Implemented | FR-050–053 |
| Cash planning | Bills, income, loans, forecast, Safe to spend | All | Obligations count, forecasts never do | `planning/` | Implemented | FR-060–064 |
| Investments and prices | Positions, returns, valuation | Investors | Typed price beats fetched | `investments/`, `market/`, `assets/` | Implemented; lots/ROI planned (5A–5E) | FR-070–074 |
| Certificates, gam'eya, gold | Egyptian instruments | Mohab | CD interest is an estimate | `deposits/`, `physical_items.py` | Implemented | FR-080–082 |
| Foreign currency | USD etc. cash with dated rates | Mohab | Stored values never rewritten when rates change | `fx.py` | Implemented | FR-090–091 |
| Reports, health, zakat, exports | Read the whole picture | All | Routes never compute figures | `reporting/`, `zakat.py`, `workflows/data_export.py` | Implemented | FR-100–104 |
| Multi-device edit journal | Edit on phone and PC | Households | One home confirms every change | `sync/journal/` | Partial (building; NF-4A) | FR-110–113 |
| Cosmetic themes | Optional support purchase | All | Appearance only; features stay free | `security/cosmetic_*.py` | Partial (owner steps open) | FR-120 |
| Arabic / English | Egyptian Arabic RTL | All | Numbers/dates keep natural order | `ui/i18n*.py` | Implemented | FR-130 |

## 7. User stories (selection)

- **US-1** As Mohab, I record my salary and see Safe to spend update, so I know what I can spend today.
- **US-2** As a user, I import a bank CSV and review each row before anything posts.
- **US-3** As a user, I see what I own, net of what I owe, in whole pounds.
- **US-4** As a user, I lock the app and nobody can read my data without the password.
- **US-5** As a household, we edit on two devices and nothing is lost.
- **US-6** As a user, I see my gam'eya turn and my certificate's unlock date.

## 8. Journeys and workflows

Step-by-step versions with diagrams: [WORKFLOWS](../architecture/WORKFLOWS.md). Month-in-the-life of Mohab: Overview §5.

## 9. Business rules (headline)

One ledger; plan ≠ money; held-for-others money is excluded from *What you own*; obligations count, forecasts never; whole pounds in summaries, cents in inputs; archive instead of delete. Full list: Overview §2.

## 10. Constraints, assumptions, risks

- Windows app is **unsigned**; WebView2 Runtime required (Architecture › Desktop app).
- Never open one live database on two computers (no cross-PC lock).
- Prices from some sources cannot be redistributed; each app fetches its own.
- Assumption: users on Android/Windows trust their device (no protection from malware on an unlocked device).
- Risks and open items: [GAP_ANALYSIS](../analysis/GAP_ANALYSIS.md).

## 11. Success metrics

**Pending Clarification** (D-001): no product KPIs (installs, retention, time-to-first-month) are defined in the repository. The only acceptance measure found is Mohab's test passing without `known_gap` markers.

## 12. Implementation status and future

See [`issues/INDEX.md`](../../../issues/INDEX.md) for the full plan by milestone. Largest open areas: edit journal (4), investment lots/ROI (5), more import formats (7), cosmetic store (10).
