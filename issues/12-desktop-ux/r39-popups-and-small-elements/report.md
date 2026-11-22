# Audit r39: popups and small elements on the PC

Date: 2026-11-22 · Author/reviewer: Claude (owner request: "look thoroughly at the small elements, the popup pages… make them fully polished"; then "fix them immediately")
Repository: app · Reviewed commit: 346416f
Code: r39

## Assessment

One cause behind most of what looked unfinished in popups: a popup shows a page's main content outside `.main`, so the 1,270 style rules scoped to `.main` did not apply inside it. Sale factors, opened from the Investments gear, ran off the side with empty boxes where its % steppers belong. The rest were small: decimals and an internal code on screen, a raw radio, a missing space, a cut chip, a card in a card, page buttons under the popup's own.

## Scope and method

The demo household at 1366 × 768. A script opened every popup linked from every PC tab, plus the register's transaction details, Add transaction, Edit account, Buy, a new subscription and Deleted transactions: 27 popups. It screenshotted each and checked it for cut text, upper case, white fields, sideways scroll, ".00" outside fields, raw dates and errors. Each screenshot was then read by eye against A05, A06.1, A10, A16 and the Glossary.

## Findings and what was done

| # | Finding | Rule | Done |
| --- | --- | --- | --- |
| F1 | Popups lost every `.main` rule: Sale factors scrolled sideways, its % steppers were empty boxes, the page's full-screen toggle showed beside Close | A10.5 | Fixed: the popup content carries `.main` (not the page's box); the page-only toggle, gear and seam stay out of a dialog |
| F2 | A page's action (Budget, Add recurring item) sat under Open as a full page and Close | A10.5 | Fixed: the popup header keeps clear of its corner |
| F3 | Plan form's Type showed a raw radio dot above its segment (page and popup) | A10.2 | Fixed |
| F4 | Add transaction's Money out / Money in / Transfer were radio dots on buttons | A10.1 | Fixed: one segment |
| F5 | Fill this month: "4,666.00 fixed", "Personal › Food & groceries", "EGP" spilling into the next column, the limit repeated in Review | A06.1, A16 | Fixed |
| F6 | Transaction details: the code BUY-2026-11-14-001 under the title, "−18,450.00", "Effect · you", "20:36:40 UTC+00:00" | Glossary › Names, A06.1 | Fixed: date only, whole amounts, the time to the minute (full stamp in its title) |
| F7 | Pay a bill: "480.00 EGP" in the header | A06.1 | Fixed |
| F8 | "Notes containoptional", "Add a tagoptional" and two labels in Ownership missing a space | A14 | Fixed |
| F9 | Price files: "You hold somet…" chip cut in its table cell | A16 | Fixed |
| F10 | Edit account: the institution suggestions opened over the form on load; Starting balance a box inside the card | A16 | Fixed: autofocus only when adding; a section under a hairline |
| F11 | The rest | — | `issues/INBOX.md` line, 2026-11-22 |

Checked and fine: titles and Close on every popup, no upper case, no white fields, the yellow focus fill (the guideline's `--field-focus`), every `<select>` holds a fixed list, not your own data.
