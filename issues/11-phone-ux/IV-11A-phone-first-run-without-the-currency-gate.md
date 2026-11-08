---
title: Phone first run - every Add is greyed out until "Save currencies" is pressed, and an empty Transactions says "Nothing matches"
type: polish
pillar: everywhere
size: M
model: sonnet
status: ready
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F7 ([report](../12-desktop-ux/r26-user-test-pc-and-phone/report.md), [evidence](../12-desktop-ux/r26-user-test-pc-and-phone/evidence/10-phone-first-run.png)). A new profile's Home lists bank, cash, certificates, brokerage and gold, each with Add greyed out, under "Save your currencies first.", though EGP is already selected: the first thing a new user does is press a button that changes nothing. With no transactions, Transactions says "Nothing matches.", as if a filter hid rows. Cash planning shows Free cash 0 and Safe to spend 0 twice each. (r20 P11 named day-one zeros on other tabs; these three were not covered.)

2026-11-08, checked against main after IV-3AY (#390, #394):
- **Currency gate: still true.** The phone router serves its own Home at `/` only once an account exists (`lightning/ui/phone/router.py` `phone_router`, the `started` route class); with no account `/` still reaches `dashboard_page` in `lightning/ui/routes/dashboard.py` (~line 66), which renders the shared `dashboard/welcome.html` on PC and phone. Its Add rows are `<span class="setup-row is-off">` until `setup_currencies_done` is "1" (welcome.html lines 32 and 48). The gate guards nothing: EGP is registered in every fresh profile (migration `0049_currency_registry.sql` ~line 205) and `/setup/currency` only changes the base while the profile has no account. The PC welcome has the same gate.
- **"Nothing matches": changed.** The bare phone `/transactions` now redirects to `/activity` (`phone_router`, `to_activity`). An empty Activity shows "In 0 · Out 0" and "Nothing recorded this month." (`phone/activity_home.html` lines 14-16): no Add, no Import, and the zeros remain. The old phone register (`phone/register.html` line 102) still says "Nothing matches." when reached with `?month=`, but no tab links there on an empty profile.
- **Cash planning zeros: 11A3 complete.** A profile without accounts shows one empty-account message and an Add an account link. Zero-value hero and debt-sheet leads are hidden; nonzero planned obligations and profiles with accounts keep their existing figures. Evidence: [phone cash-planning regression tests](../../tests/test_phone_cash_planning.py).

## Fix

The Add rows work at once (the currency form stays above them, optional); an empty Activity says "No transactions yet." with Add and Import; Cash planning with no account says so once instead of four zeros. One PR per step.

## How to work on this item

Each step is one pull request. Read only the files a step names; never open guideline HTML whole (`python tools/guideline.py C11` prints one section). Run the step's test command, then `python -m pytest tests/test_mohab_year.py -q` and check A16 on a phone screenshot; delete the step's heading in the same commit.

## 11A1 Add works before "Save currencies" · S · sonnet · #432
Files: `lightning/ui/templates/dashboard/welcome.html` (lines 32 and 48), `tests/test_demo_and_visuals.py` (`test_setup_currency_registers_the_base_and_the_others_held`, ~line 247).
Do: in welcome.html delete line 32 (`{% if not currencies_done %}<p ...>Save your currencies first.</p>{% endif %}`) and make line 48 always render the link: `<a class="setup-row" data-popup-open href="/accounts/new?type={{ kind }}">…</a>` with no `currencies_done` branch and no `is-off` span. Leave the currency form and `/setup/currency` unchanged (the form still shows until saved; the account form defaults to the profile currency, EGP). Do not touch `dashboard.py` or the journal workflow. In the test, replace the first two asserts with: `'href="/accounts/new?type=BANK"' in before and "is-off" not in before and "Save your currencies first." not in before`; keep the rest.
Done when: a new test `test_a_fresh_profile_adds_an_account_without_saving_currencies` in `tests/test_demo_and_visuals.py` gets `/` on a fresh `c`, asserts all five `href="/accounts/new?type=` links (BANK, CASH, DEPOSIT, BROKERAGE, PHYSICAL_ASSET) and no `is-off`, then posts `/accounts/new` with `{"name": "CIB", "account_type": "BANK", "currency": "EGP", "opening_balance": "0", "opening_balance_date": "2026-09-01"}` (the form as `tests/test_audit_forms_people.py` ~line 92 posts it, with a name) and asserts `c.accounts.list()[0].currency == "EGP"`. `python -m pytest tests/test_demo_and_visuals.py -q`.

## 11A2 An empty Activity says "No transactions yet." with Add and Import · S · sonnet · #433
Files: `lightning/ui/phone/screens/activity.py` (`ActivityScreen`, `build`), `lightning/ui/templates/phone/activity_home.html` (lines 14-16), `tests/test_phone_activity.py`.
Do: add a field `ledger_empty: bool` to `ActivityScreen`, set in `build` as `c.reporting.first_activity_date() is None`. In the template's `all` tab, when `s.ledger_empty`: draw neither the month chip nor the `phone-money-line`; instead `<p class="phone-note">{{ 'No transactions yet.'|tr(locale) }}</p>` and two buttons, `<a class="btn primary phone-save" href="/add-transaction" data-popup-open>{{ 'Add transaction'|tr(locale) }}</a>` and `<a class="btn phone-save" href="/import">{{ 'Import a statement'|tr(locale) }}</a>`. All three strings already have Arabic in `lightning/ui/i18n.py`. Otherwise the page is unchanged ("Nothing recorded this month." stays for an empty month in a used ledger).
Done when: a new test `test_an_empty_ledger_offers_add_and_import_instead_of_zeros` in `tests/test_phone_activity.py` builds a fresh profile (`build(tmp_path / "e.db")`, `mount_phone(app)` as the `client` fixture does, no sample) and asserts `/activity` contains "No transactions yet.", `href="/add-transaction"`, `href="/import"` and not `phone-money-line`; the existing tests still pass. `python -m pytest tests/test_phone_activity.py -q`.
