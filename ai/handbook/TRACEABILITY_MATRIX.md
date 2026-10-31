# Traceability matrix

Feature → requirement → component → data → entry point → tests. Tests are examples (nearest evidence found),
not a coverage claim. "—" means none identified (not that none exist).

| Feature (PRD) | FR / NFR | Component | Tables | Entry points | Tests |
|---|---|---|---|---|---|
| Profiles & encryption | FR-001–005, NFR-002–004 | `security/keys.py`, `runtime/session.py` | `profile_identity` (+ `keys.json` file) | `/profiles*` | `test_profile_session.py`, `test_biometric_unlock.py` |
| Accounts | FR-010–012 | `accounts/`, `workflows/accounts.py` | `accounts`, `institutions` | `ui/routes/accounts.py` | `test_accounts_categories.py` |
| Ledger | FR-020–025, NFR-006 | `transactions/`, `core/ledger.py` | `transactions`, `ledger_entries`, `audit_log` | `register.py`, `transactions.py`, `history.py` | `test_audit_numbers.py`, `test_amount_sums.py` |
| Names & rules | FR-030–033 | `categories/`, `counterparties.py`, `rules/`, `reimbursements.py` | `categories`, `counterparties*`, `rules*`, `reimbursement_*` | `categories.py`, `rules.py` | — (search `tests/test_*rules*`) |
| Import | FR-040–042 | `bank_imports.py`, `sms_imports.py` | `bank_import_*` | `bank_imports.py`, `sms.py` | `test_bank_imports.py`, `test_bank_import_matching.py` |
| Budget & reserves | FR-050–053 | `budgeting/`, `reserves.py` | `budgets`, `budget_carryover*`, `cash_reserves`, `reserve_*` | `budget.py`, `reserves.py`, `payday.py` | `test_bills_before_payday.py` |
| Cash planning | FR-060–064 | `planning/` | `planned_items`, `planned_payments`, `loan_extra_payments`, `installment_purchases` | `planning.py`, `weekly.py` | — |
| Investments & prices | FR-070–074 | `investments/`, `market/`, `assets/` | `financial_assets`, `price_history`, `investment_*` | `investments.py` | `test_broker_pockets.py` |
| Valuation | FR-073 | `reevaluations.py` | `reevaluation_*` | startup | — |
| Certificates / gam'eya / gold | FR-080–082 | `deposits/`, `physical_items.py` | `cd_*`, `gameya_terms`, `physical_item*` | `deposits.py`, `gameya.py`, `physical_items.py` | — |
| FX | FR-090–091 | `fx.py`, `reporting/fx_positions.py` | `fx_rates`, `registered_currencies` | `settings.py` | — |
| Reports | FR-100–104 | `reporting/`, `zakat.py`, `integrity.py` | derived (+ `zakat_settings`) | `dashboard.py`, `analysis.py`, `zakat.py` | `test_figures.py`, `test_mohab_year.py` |
| Devices & journal | FR-110–113 | `sync/journal/`, `runtime/journal_*` | journal store (separate encrypted store) | `/journal*`, `/profiles/journal/*` | `test_two_devices.py`, `test_journal_*.py`, `test_edit_journal.py` |
| Themes | FR-120 | `security/cosmetic_*.py`, `ui/themes.py` | — | `settings.py` | — |
| Language | FR-130, NFR-016 | `ui/i18n*.py` | — | all | `test_arabic_*.py` |
| Layering | NFR-011 | `pyproject.toml` contracts | — | — | `test_architecture.py` |

Rows with "—" in Tests: **Unknown** whether coverage exists under another name; use `grep -l <module> tests/`.
