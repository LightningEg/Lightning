# Release notes

What changed in each version, in plain words. Generated from `ai/changelog/` by `python tools/release_notes.py`; do not edit by hand. The full detail for each version is in the same folder.

## 2.0.1 · 2026-11-05

**Capture**

- The Import statement button sits beside Money actions, and ticked import rows can be edited together.
- A new counterparty typed during import is saved at once, and same-named rows in the group adopt it.
- Same-named categories (Personal and Work Transportation) are never guessed between during import: you choose.
- Merge into… on a counterparty moves its history, rules and plans to the name you keep; the old name becomes an alias.
- On the phone, swipe a transaction to the side to set its category or delete it.
- Find names and confirmed aliases across search, pickers and transaction history, including near spellings.
- Import Excel and text CIB statements, or copy an AI prompt to prepare an image PDF as CSV.
- Record a currency transfer from exact statement amounts and link the other statement to it.
- Search pages, names and transaction history with the same Arabic-aware matching.
- Review Excel and text CIB statements, match currency transfer legs, and prepare unreadable PDFs with a local AI prompt.
- Choose clearly when an account and a counterparty share a name; the selected counterparty stays an expense.
- Searching on the phone no longer shows old results when a slow answer arrives after a newer one.

**Plan**

- Budget now shows how much of your income no plan, goal or emergency top-up has claimed, with a link to assign it.
- When you set up your first budget, the limits Lightning suggests are round numbers (650, not 671), and you can still type any amount.
- Act from where you look: buy more from a holding, give money back to its owner, see a bill or a gam'eya instalment in one sheet, and read the register month by month.
- Give a rule a name and change one category limit without editing the whole budget.
- Compare income delays, purchases and bill changes, and review unusual bill charges in Needs you.
- Name rules, change one category limit, compare scheduled-cash scenarios and review unusual bill charges.
- Review received salary and pay bills from their saved reserves.
- Reserve-funded expenses and extra loan principal stay outside the monthly spending plan, with gross spending still shown.
- Safe to spend breakdowns add up to their displayed total on PC and phone.
- Needs you now shows the remaining financial-health alerts with review and snooze controls.

**Understand**

- Every AI hand-off is a Copy prompt and Edit prompt pair that says why it helps; the text is never open on the page.
- Overview now shows why net worth changed (what you kept, market moves, other changes) and your net worth in US dollars and grams of 21K gold.
- Accounts, the sidebar and More now show the same In your accounts total, and Accounts explains how it adds up to what you own; on the phone, rent and loan payments already paid say Paid for this month instead of Ahead of pace.
- Open any spending category as one sheet from Budget, Spending or Transactions, and type "120 uber" in Ctrl-K to add it.
- KPI cards on Loans, Recurring, Spending and Currencies now say what each figure compares with, including your own limits.
- See which old or pending inputs affect Free cash and the cash forecast.
- See how old the cash you spend is and open spending by calendar date.
- Read FIFO cash age, spending by calendar date and stale or pending inputs behind financial figures.
- Returning income reduces Money in consistently across reports and Budget.
- Donut charts keep four named parts and group the rest as Other.
- The currency chart says when it shows cash only.
- The Planner chart groups smaller allocations into Other while keeping every detail.
- Financial health trends show a zero baseline and leave missing months blank.
- What you own now says which prices and exchange rates behind it are old or missing, and where to update them.
- When two prices exist for one day, one written order decides which value you see: your own price, then a buy or sell, then the market pack, then online quotes.
- Investment pages use shared read models for class and currency figures.

**Own**

- Update prices matches Egyptian fund names in any word order and suggests the nearest names when none match.
- Add silver you hold by the gram and type its price yourself.
- Record what you paid for a flat or a car, see the change since, and link the car to its loan.
- Compare a holding's return with a T-bill or certificate rate you type.
- A brokerage with more than one currency opens on a short summary in your main currency, with a tab for each currency; a single-currency brokerage looks as before.
- Saudi, Gulf and European shares you hold now get their prices automatically, in their own currency.
- A separate dollar brokerage account can be moved into your broker as its dollar pocket, keeping its history and holdings.
- With the USD view on, the allocation, brokerage cash and biggest holdings are shown in dollars too.
- When you add a trade at a broker that trades the Gulf or Europe, you can pick from about 1,700 Saudi, Gulf and European shares and funds.
- Import an Interactive Brokers activity statement: trades, currency conversions, dividends with tax, interest and fees are recorded once, and the open positions are checked against your holdings.
- Download shared prices now brings the latest exchange rates again.
- Investment returns explain when several annualized rates fit, or why a rate is unavailable.
- Record bonus shares, a split or a reverse split without a fake purchase, and see on each holding what every purchase and sold piece has returned, per year too.
- Choose, per brokerage account, whether a sale takes its cost from the average of your purchases or from the oldest purchase first.

**Protect**

- Undo remains available beside a phone success message until you leave the page.
- Starting from source opens password-protected profiles by default.
- Starting from source requires encrypted profiles or explicit sample data and leaves existing legacy files untouched.
- Settings now has Save a copy, so the newest encrypted backup can leave the phone.
- The Checks screen now confirms that every holding's units and sale proceeds agree with the ledger and that nothing was sold that was not held.
- Saves and automatic bill matching now succeed or roll back together across the remaining write screens.

**Everywhere**

- Finding the PC or phone on the network is more reliable: the search announces on every local network, three times.
- Dated Other asset estimates save correctly on a linked device.

**Feel**

- Undo, Redo and every save keep your place on the page and which sections were open.
- Only one action menu is open at a time; scrollbars are thin and themed; import review no longer stalls under heavy themes.
- On a PC, the tabs of a section now sit beside the page title, so the first card starts higher.
- On a laptop screen the Overview now shows your savings rate, safe to spend and plan without scrolling, Accounts lists every group in one column, and Investments and Cash planning open on their answer.
- Payday amounts read cleanly, and a property or car page leads with its value, change since purchase and loan.
- On PC, each page now says what its figures mean under the title, and Certificates shows one line per interest payout.
- On the phone, Spending's analysis reads cleaner, Currencies shows the same total as the PC, and Left in plan says what it is out of.
- Keep your chosen field focused and retain Undo after a popup saves.
- Rule split fields keep their numeric parts on the phone.
- Undo now reverts your last money action instead of switching the language back.
- Loans show what you paid in blue and what you still owe in rose, and Currencies reads as one clean card per currency.
- Posting a bank import now posts the rows you resolved and keeps the rest in review; charts, phone controls and PC actions fit and read better.
- Investment charts and actions use colours that match their meaning.
- Counterparty alias and merge controls fit the phone screen.
- Phone settings and inner pages have a clear way back, and Latest shows money movements.
- Phone picker choices are easier to tap and fit the screen.
- Search closes on Escape and an unplanned month has clearer wording.
- Month arrows on Overview and Transactions are easier to tap.
- Phone entry fields are easier to read and chart dates are less crowded.
- Focused phone fields stay within the active theme.
- Data checks remains available from Settings on the phone.
- Phone loan and reserve actions are easier to tap, with clearer device wording.
- Settings keeps links to rules, categories and counterparties on the phone.
- Review activity shows money out with a minus and inline links read clearly.
- From SMS links back to Accounts.
- Chart number disclosures are easier to tap on a phone.
- Investment Planner choices remain readable on narrow phones.
- Recurring payment due actions are easier to tap.
- Transaction details use a readable heading and plain labels for ledger effects.
- Transaction details show readable recorded and updated times.
- Transaction details name the action while keeping the reference visible.

**Build**

- Lightning is a full release; the phone app is named Lightning and its file is Lightning-<version>-<build>-<commit>.apk.
- Transaction entry and editing share balance checks while keeping their existing money rules.
- Keep the cash-check scaling guard independent of method placement.
- Pull requests now check core financial behavior on the minimum supported Python version.

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
