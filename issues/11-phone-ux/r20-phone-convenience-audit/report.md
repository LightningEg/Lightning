# Audit 13: the phone for quick jobs - convenience, taps and the look

Code: r20

Date: 2026-11-01 · Author/reviewer: Claude (guideline-audit skill)
Repository: app · Reviewed commit: 4ba2732c28cf13f02478425adcb75713e0b638d3
Historical ID: audit-13

## Scope and method

The owner (2026-11-01): the phone's flow, clutter and visuals are not set for a phone user; audit it from UX and UI and
build a visual plan only for the phone, based on convenience and quick actions. Audit 10 judged each tab alone; this
audit follows the jobs a person opens the phone for and counts the taps each takes.

The phone app (`profile_app(..., phone=True)`) ran on a dummy profile with the sample household in Chromium with touch,
at 360 × 800 and 320 × 700, in English and Arabic, on 2026-11-01 (the first day of a month, so empty-month states show).
Pages were captured with Audit 10's [capture.py](../r17-phone-tab-audit/evidence/capture.py) (output:
[metrics.json](evidence/metrics.json)); the five jobs were driven with [flows.py](evidence/flows.py) (output:
[flows.json](evidence/flows.json); a second argument `ar` adds the Arabic shots). Rules: guideline Part C and A16.

| Page | Screens long | Figures | Targets | Under 40 px |
| --- | --- | --- | --- | --- |
| Overview | 1.8 | 14 | 56 | 0 |
| Budget | 1.7 | 16 | 20 | 0 |
| Transactions (this month) | 1.0 | 5 | 27 | 0 |
| More | 1.7 | 5 | 18 | 0 |
| Cash planning | 3.1 | 29 | 13 | 1 |
| Investments | 2.9 | 30 | 23 | 0 |
| An account | 5.5 | 82 | 72 | 3 |
| Financial health | 2.8 | 8 | 22 | 9 |
| Spending | 6.0 | 70 | 69 | 15 |
| Settings | 4.0 | 0 | 46 | 14 |

## Findings

The findings (P1-P15), the tap budget for the five jobs and the visual plan are one item, so they are kept in one place:
[IV-3AN](../IV-3AN-phone-visual-plan-quick-actions.md). Screens are in [evidence/](evidence/),
numbered as the item cites them.

The owner then asked why the app is slow and whether it needs another language than Python. The timing, the
answer (no rewrite: most of the wait is the phone's browser reloading the whole page on each tap) and the steps are
IT-3AO ([the item as finished](https://github.com/LightningEg/Lightning/blob/6600e86a2279a0b2b8b97df8557d28f3a22f123e/issues/3-polish-and-arabic/3AO-phone-feels-slow-full-page-reloads.md); regression test `tests/test_phone_nav_browser.py`).

## Validation and limits

Browser evidence only. Not checked: a real phone's keyboard (where Save lands while typing), the Android shell and its
back gesture, dark and paid themes, a profile with years of data. Tap counts start on Overview and count each tap,
choice and scroll. Figures counted by a pattern, so approximate. No code was changed.

## Dated follow-ups

- **2026-11-01, IT-3AO built and closed** (owner: "fix it then", then "nevermind measuring on a real phone, finish the
  rest"). Every phone page now swaps its content instead of reloading (`lightning/ui/static/phone-nav.js`): a tab switch
  at 4x CPU went from about 1.0 s to 0.25-0.3 s, and on all 30 phone pages a swap shows the same content as a full load.
  Settings, categories, payer names and aliases are read once per request; two forced layouts at load are gone.
  Tests: `tests/test_phone_nav_browser.py`, `tests/test_settings_memo.py`, `tests/test_phone_sheets_browser.py`.
- **2026-11-02, IV-3AN built** (owner: guideline 3.38 lines 1-5, the stepper keeps its pill; "finish the whole thing").
  Re-run of `evidence/flows.py` and `tools/phone_check.py` on the sample at 360 × 800:

  | Job | Before | After |
  | --- | --- | --- |
  | J1 Record a payment | 6 and a scroll | **3**: Add, a category chip, Save (amount typed; Save in view while typing) |
  | J2 Bank SMS to a transaction | 3 from Add | **2**: Add, Paste SMS (then check and Save) |
  | J3 Pay the next bill | 3 from More | **2** from Overview: "Landlord 12,000 tomorrow" in Needs you, Mark paid |
  | J4 Left for groceries | a scan of 9 A-Z rows | **1**: the row at 382 px, ordered by need; it opens its sheet |
  | J5 Find or fix a payment | pages only; 6 to sort | **1** to search (live, payments first); **3** to sort, the next row opens by itself |

  Overview's first Latest row: 583 px (target under 600). Nothing scrolls sideways at 360 or 320, sheets included.
  Left: Accounts tab first (3AN12, needs the owner), and the owner's one end-to-end check on a phone.
