# Release notes

What changed in each version, in plain words. Generated from `ai/changelog/` by `python tools/release_notes.py`; do not edit by hand. The full detail for each version is in the same folder.

## 1.5.4 · 2026-10-30

**Capture**

- Skipping a loan payment can no longer drop a part payment, and a resent conversion, certificate purchase or gam'eya instalment saves once.

**Plan**

- Cash planning on the phone names the next payment after payday.

**Own**

- Convert asks once before saving a rate 20% or more from the day's market rate; swapped amounts used to value every dollar at 0.02 EGP.

**Protect**

- Unlocking with Enter and then a click no longer shows "This form expired".

**Everywhere**

- Pairing leads with nearby device discovery; address and code pairing stay as a second option.

**Feel**

- Every PC tab opens on its answer. Transactions, Budget, Overview, Spending, Loans, Investments, Accounts and more lose explanatory sentences and lone cards and gain shared charts; Transactions shows 11 rows on a 1366 x 768 screen.
- The PC shell gives back space: the sidebar's accounts list scrolls on its own, there is one header row, and Review activity moves into the ⋯ menu.
- Settings read as lists, not forms: Counterparties and Categories are one column, Data checks fold passed checks into one line, and the database path sits under Advanced.
- Reserves is titled Safety, Limits reads today's emergency fund the way Safety does, and Budget names its system group by what it holds.
- On the phone, Overview has one Needs you strip, Budget lists each category once, Transactions opens on this month, and More is a flat list.
- Settings opens on Your data first, with Data checks last.

**Reach**

- Version 1.5.4 carries everything prepared for 1.5.2; 1.5.2 and 1.5.3 were never published.

## 1.5.1 · 2026-10-29

**Understand**

- One transaction page shows everything it touched, and counterparties, tags and an account's dependants have pages of their own.
- The net-worth bridge flags incorrect profile-currency cash values instead of hiding them.

**Own**

- Every wallet and fintech logo is linked, and 37 show on account tiles.

**Everywhere**

- Sync and pairing say what went wrong: the last sync error shows on Devices, a removed device learns it and stops, and devices whose clocks differ by 15 minutes can pair.

**Feel**

- New animated banners Felucca and Sand wind; Dendera becomes a premium theme with pointer light, press sheen and gold-leaf tabs at night.
- A paid theme unlocks once per profile and is shared with its other devices; unlock errors say busy or too many tries.
- The PC menu is regrouped by your questions into eight sections, with new Compare periods, Item analysis and Reports pages, and Settings as one card per topic.
- The Windows 11 title bar matches the page, and the phone start screen shows the lockup with a loading bar.
- On the phone, Add opens the last-used account with the amount focused, Paste bank SMS fills the sheet, rows swipe to open or delete with Undo, Today shows payments due today or tomorrow, and Budget flags Ahead of pace.
- In Arabic the budget move preview reads "من … إلى …" and compact figures drop a trailing .0 after rounding.

**Reach**

- Downloads leads with your platform and says real statements are welcome.

## 1.5.0 · 2026-10-26

**Capture**

- Bank CSV imports accept accounting negatives, currency wrappers and Arabic digits.
- Search treats Arabic spelling variants, diacritics, Arabic and Persian digits and Latin case alike.
- A resent add form saves once, and fifteen more write-path, loan, schedule and onboarding mistakes are fixed.

**Plan**

- A confirmed loan repayment is protected from edits that would leave stale debt.

**Understand**

- Needs you items can be reviewed, snoozed or restored, and resurface when the situation changes.

**Own**

- Distributions, withholding and realised gains follow the ledger owner, including changed ownership and closed holdings.

**Everywhere**

- An interrupted pairing can resume, device keys use Windows DPAPI and the Android Keystore, and the PC discovers nearby devices so you pick the home's number from three choices.

**Feel**

- Dendera, an animated theme with day and night, a zodiac ring, a winged disc and a lotus frieze, and the Cotton light theme; Nile Papyrus & Lapis Guilloché is redone. Anyone can try a theme and keep it with a signed licence.
- Settings explains that themes switch immediately and shows a confirmation for saved choices, in English and Arabic.
- On the phone, Overview answers first and review and price tasks lead with the decision.

**Reach**

- All Lightning features are free; optional in-app themes support development.

Earlier versions, and the detail behind every version: [ai/changelog/](ai/changelog/).
