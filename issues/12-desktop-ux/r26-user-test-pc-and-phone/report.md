# Audit 14: using Lightning as a user, on the PC and the phone

Date: 2026-11-06 · Author/reviewer: Claude (bug-hunt and arabic-check skills)
Repository: app · Reviewed commit: 082a9117ac45d7b1ebd12d39d29f5a3c22f35ed5
Code: r26 · App version 2.0.3

## Assessment

Lightning holds up well when you use it. Every quick job finished, and every tab moved by exactly the amount
entered: a 250 cash expense, then a 350 bill marked paid. The forms refused bad input in plain words, and accepted Arabic
digits and the Unicode minus. No page threw a script error, failed a request or scrolled sideways at 1366 or 390 px. Arabic
covers nearly every word.

What a user would trip on is **figures that answer the same question differently**. These five matter most:

1. The daily allowance. The phone's Home says **2,057 a day**, the phone's Budget **278 a day** and the PC's Budget
   **219 a day**, all for the same 25 days.
2. Budget's headline says **2,227 over pace** while the same card says **59 below last month** at this point.
3. Pressing Enter in the PC's quick-add row skips the empty Account field, so the next word typed replaces the category.
4. In Arabic, every page header reads its date range **backwards**.
5. A new phone user cannot add a first account until they press **Save currencies**, even though EGP is already chosen.

Two findings repeat items that are still open in IV-3H (IN-4, and credit cards with money owed to you). They are
confirmed here and linked, not filed again.

## Scope and method

- **As a user:** the jobs a salaried user does in a week, done through the screens with mouse, keyboard and touch. Record a
  cash expense, mark a bill paid, check what is left, search a merchant, look at investments and safety, switch to
  Arabic. On a new phone profile: the first run, then the sample year.
- **The PC:** `python -m lightning --demo --no-browser` (the sample household, 2026-09-01 to 2026-11-06) in Chromium at
  1366 × 768. All 18 sidebar and tab pages were captured, `tools/bug_crawl.py` crawled 600 pages, and forms were posted
  directly with blank, zero, letters, huge, 3 decimals, Arabic digits, the Unicode minus and units.
- **The phone:** the phone app (`profile_app(..., phone=True)`) in Chromium with touch at 390 × 844 (r25 used 412 px).
  The run covered a fresh encrypted profile's first run and empty tabs, then the sample, 19 pages and the quick jobs.
- **Numbers:** before and after each change, Net worth, Kept, Left in plan, Everyday spending, Safe to spend, Free cash
  and Money out were read on Overview, Budget, Cash planning and Spending.
- **Read first, so nothing is repeated:** r19, r20, r24 and r25, and the open notes in IV-3H, IV-3AM, IV-3AN and IV-3AY.
  A finding that matches one of them says so.

## Findings

Severity: **high**, a figure that would lead the person to a wrong money decision; **medium**, daily friction or
two figures that disagree; **low**, polish.

| ID | Severity | Observation and expected behavior | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| F1 | high | **Three daily allowances for one month.** Phone Home: "About 2,057 a day until payday", which is Safe to spend 51,420 ÷ 25 days, money *on top of* the plan. Phone Budget: "About 278 a day for 25 days", which is Left in plan 6,948 ÷ 25 and still counts the 1,480 of bills to pay. PC Budget: "5,468 for everyday, about 219 a day", the only correct one. IV-3H CP-1 (done) decided one daily figure, on Budget, and "on top of your plan" for Safe to spend. The PC follows that decision; the phone does not. Expected: 219 on both Budget screens; Home says "51,420 on top of your plan until 2026-12-01", with no per-day figure. | [08](evidence/08-phone-home.png), [09](evidence/09-phone-budget.png), [02](evidence/02-pc-budget.png); probe F1 | BV-12A |
| F2 | medium | **"Over pace" on a normal month.** On day 6 the PC Budget headline says "You are 2,227 over your plan's pace". Everyday spending says the same, yet its footer reads "−59 against 2026-10 by day 6", and October ended on plan (9,674 against 9,619). The plan's pace is a straight line, but this person's month starts heavy every time: the big grocery shop on the 2nd and the gym's 900 on the 4th. So the warning fires every month and stops meaning anything. The phone shows "Health 900 of 900 · Ahead of pace" for the gym (r24 F5 fixed this only for items set up as recurring). Expected: pace against the person's usual curve (the last months, day by day), or a monthly fixed payment taken out of "everyday" once it has been paid. Never "over pace" while below the usual month. IV-3H BU-4 asks for pace and does not cover this. | [02](evidence/02-pc-budget.png), [09](evidence/09-phone-budget.png); probe F2 | BV-12B |
| F3 | medium | **PC quick add: Enter skips Account and the next word replaces the category.** In the Every account view, type a known name ("Koshary El Tahrir") and press Enter. The category fills (Eating Out), but focus jumps to Category. The empty, required Account field below the name is skipped. Typing "Cash" next sets the category to "Cash", and Save then stops on "Choose an option from the list". The account is not suggested either, though every earlier row for this name used Cash wallet; the phone remembers the last account. Expected: Enter goes to the first empty required field. A known name fills its usual account and category. | [03](evidence/03-pc-quick-add-category-overwritten.png); probe F3 | IV-12C (done: `tests/test_counterparties.py`) |
| F4 | medium | **Investments' "Money and value by class" does not add up** (IV-3H IN-4, still open). November shows Money in +2,000. Under value moved it shows Money market fund **+3,033** for a fund bought for 3,000 from brokerage cash this month (its gain is +33). The class changes add up to 9,063, while the page says "Your holdings grew 7,896". No November purchase explains the +2,000 Money in. | [05](evidence/05-pc-investments.png); probe F4 | IV-3H (IN-4) |
| F5 | medium | **Neighbouring figures that disagree or read wrong** (each small; together they cost trust). (a) Free cash says "Cash you own 87,768", but Accounts' Cash & bank says what you own is 87,368. The 400 of brokerage cash is in one figure and not the other, and neither page says so. (b) Scenarios shows "Lowest scheduled cash 86,288.36", in cents, while Cash planning shows "Lowest point ahead 51,420": two lowest points ahead, with no hint why they differ. (c) Scenarios says "First shortfall: None None", which the bug crawler flags on every run; it should say "No shortfall". (d) Financial health says "4 of the 6 figures you set a limit for · 1 needs you", but the sixth (Debt to cash) shows "No limit". (e) Cash planning: "Bills due, loans apart: 0" sits under "Due before payday 1,480". (f) Accounts' "How it adds up" adds "Gam'eya still to pay **+**14,000" to what you own, so a debt reads as a gain. (g) Budget shows "Plan leaves to save 19,401" and "Not yet given a job 13,997" side by side, with no line linking them. (h) Overview puts "Investing rate 7.1% · −89.5 points on 2026-10 (96.6%)" beside Savings rate without saying that it is a share of what you kept, not of income. (i) Spending: "Against your usual month +1,410 · 6%" repeats "Against 2026-09 +1,410 · 6%" when there is only one month before (A16: a line that repeats). | [04](evidence/04-pc-cash-planning.png), [06](evidence/06-pc-financial-health.png), [01](evidence/01-pc-overview.png); probe F5 | BV-12D |
| F6 | medium | **Arabic: date ranges read backwards, and numbers are written two ways.** Every page header wraps "X لحد Y" in `<b dir="ltr">` (`partials/macros.html:129`), so a right-to-left reader meets the end date first: "6 Nov until 1 Nov". Compare periods has the same wrapper and a hard-coded English "to" (`analysis/compare.html:3`). Hero figures use a Latin comma ("١٩٧,٩٧١") while every other figure uses the Arabic separator ("٢٦٤٬٤٧١"). Counts do not agree with their nouns: "بعد ٣ يوم" (3 day), "٢ دفعة" (2 payment), "٠٫٨ شهور". The gold account's history shows "Investment revaluation" in English. Everything else on 21 pages was Arabic, apart from names the user typed. | [07](evidence/07-ar-date-range-reversed.png), [11](evidence/11-phone-ar-home.png); probe F6 | BV-3BA |
| F7 | medium | **Phone first run: an extra gate, then a wrong empty state.** A new profile's Home greys out every *Add* (bank, cash, certificates, brokerage, gold) behind "Save your currencies first.", though EGP is already chosen. The first thing a new user must do is press a button that changes nothing. On an empty profile, Transactions says "Nothing matches." as if a filter hid rows; it should say there are none yet and offer Add or Import. Cash planning shows Free cash 0 and Safe to spend 0 twice each. | [10](evidence/10-phone-first-run.png); probe F7 | IV-11A |
| F8 | low | **PC ledger noise.** In the Every account view each transfer is two rows (From… and To…): 10 of the first 50 rows in the sample. The save message shows the internal reference and cents: "Saved OUT-2026-11-06-002. Budget · Shopping: 999.00 EGP left this month". Marking a bill paid shows a toast with no Undo, while the phone's message carries one. | Transactions page; direct post in Validation | IV-12E |
| F9 | — | **What a user will look for and not find.** (1) Credit cards, the usual way salaried Egyptians pay in instalments. (2) Money lent to family or friends and expenses split with others. Both are out of scope by an earlier decision (Project Overview, "Obligations count") and are raised again in IV-3H item 8. (3) A photo of a receipt or a bill kept with its transaction (no template mentions one). These are product choices for the owner, not bugs. | `ai/PROJECT_OVERVIEW.md` line 59; template search | OW-12F (done), NF-12G |

### What already works and should be kept

- **Figures stay in step:** a 250 cash expense moved Net worth, Kept, Free cash, Left in plan, Everyday spending and Money out
  by exactly 250. Safe to spend did not move, which is correct because the spend was inside the plan. Marking Vodafone
  350 paid moved Due before payday, Budget's bills to pay and Left in plan by 350 on every screen.
- **The amount field explains its refusals:** "Use at most 2 decimal places", "That amount is too large", "Use commas only as
  thousands separators". It accepts "−300" (Unicode minus) and "-٣٠٠" (Arabic digits).
- **The phone's Add sheet:** decimal keypad, the last account remembered, four category chips, Paste SMS, and Save pinned.
- **Tapping a bill on Home** opens one sheet: already in your transactions? record it now, or skip it.
- **Search** finds a merchant's payments first, then its name and category.
- **The pages are clean:** no script errors or failed requests, and no sideways scroll at 1366 or 390 px on all 37 page captures.

## Validation and limits

```
python -m lightning --demo --no-browser          # PC, sample household
python tools/bug_crawl.py                        # 600 pages crawled; only /plan/scenarios flagged ("None None", F5c)
python issues/12-desktop-ux/r26-user-test-pc-and-phone/evidence/probe.py   # re-checks F1-F7 on PC and phone
```

Probe output at the reviewed commit (abridged):

```
F1 PC Budget: 5,468 for everyday, about 219 a day
F2 PC Budget: You are 2,227 over your plan's pace. | −59 against 2026-10 by day 6
F5 Scenarios: Lowest scheduled cash 86,288.36 EGP | First shortfall None None
F5 Cash planning: Cash you own 87,768, less 20,400 set aside or due
F5 Accounts: Cash & bank 87,368
F4 Investments: Your holdings grew 7,896 | Money in +2,000 | Money Market Fund +3,033
F3 PC quick add: focus after Enter = 'Category'; account filled = ''
F6 Arabic header: <b dir="ltr">⁦‭٢٠٢٦-١١-٠١‬⁩ لحد ⁦‭٢٠٢٦-١١-٠٦‬⁩</b>
F7 phone first run: Save your currencies first.
F1 phone Home: About 2,057 a day until payday on 2026-12-01.
F1 phone Budget: About 278 a day for 25 days
F2 phone Budget: Health 900 of 900 · Ahead of pace
```

Direct posts to `/transactions/register` (amount field): blank, `abc`, `0`, `-99999999999999`, `-12.345`, `-1,2,3` and
`5 EGP` were refused with a message; `−300` and `-٣٠٠` were saved.

**Limits.** This was browser evidence from Chromium on Linux, not the Windows WebView2 app or a real Android phone. Native
keyboards, the status bar, file pickers and notifications were not checked. The plaintext demo server accepted posts
without the session field; the encrypted profile app checks it (`lightning/runtime/app.py:157`), but that was not tested
from outside. CSV and PDF import, backup and restore, pairing and the store were not exercised, since r23, r11 and the
open 2A/2C items cover them. The sample covers only two full months, so year views and the yearly Mohab year were not
re-run through the screens. The source of F4's +2,000 Money in was not traced. The full test suite was not run: this
change is documents only, and the documentation tests were run.

## Dated follow-ups

- **2026-11-06, F9:** the owner chose money lent and split with others (OW-12F, now done); credit cards and receipt photos stay out of scope. Recorded in `ai/PROJECT_OVERVIEW.md` (Obligations count) and planned as NF-12G.
- **2026-11-07, F1:** fixed (BV-12A). Home says "On top of your plan until <payday>" with no per-day figure; the phone Budget reads the PC's everyday per-day figure from `EverydayBudget.per_day`. Tests: `tests/test_one_daily_allowance.py`.
- **2026-11-07, F6:** fixed (BV-3BA). Each header date is its own left-to-right isolate (`isolate_dates`), so the start date is on the right; counted nouns agree with their count (`_agree_counts`: 1, 2, 3 to 10, 11 and more); "Investment revaluation" has Arabic entries. The "Latin comma" was not a different character: every figure uses U+066C, which the hero face draws like a comma and the body face like an apostrophe; nothing to unify in code. Tests: `tests/test_arabic_ranges_and_counts.py`.
