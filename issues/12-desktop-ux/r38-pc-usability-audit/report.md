# Audit r38: PC usability audit, "Strong parts, scattered"

Date: 2026-11-22 · Source: an 18-page PC usability audit the owner supplied (dated 2026-11-21: the demo household at 1440 × 900, every PC section, with proposed mockups) · Dispositions: Claude, checked against the guideline and the code
Repository: app · Reviewed commit: c8642ef
Code: r38

## Assessment

The audit is right that the PC's explanations are its best part (Safe to spend's breakdown, the budget pace chart, the holdings table) and that friction comes from what leads a page, how many controls sit above it and actions with no obvious home. About half of its fixes are rules the guideline already has; the rest either contradict an owner decision or the guideline, or need the owner. Nothing here is wrong money.

## Owner direction (asked in this session, 2026-11-22)

| Question | Answer |
| --- | --- |
| What to build | Every fix the guideline already asks for, in two or three PRs |
| Overview's Lead | **Net worth stays** (A09.1); Next 7 days becomes a named list |
| A PC Add button or window | **No Add button**: adding lives in the account (Transactions keeps "Choose an account") |
| "In your accounts" names two figures | The phone's Home hero becomes **Cash and banks**; In your accounts keeps the Glossary meaning |
| Needs you's count | **Every item** (A09.2), not rows |
| The period control's month | **"Nov 2026"**, opening the month picker |

## Findings and dispositions

| # | Finding (audit page) | Disposition |
| --- | --- | --- |
| F1 | No Add button outside Transactions (p.1, 13) | Owner: no Add button; adding lives in the account |
| F2 | Overview should lead with Safe to spend (p.3-4) | Owner: Net worth stays the Lead (A09.1; Safe to spend left Overview in 2.5) |
| F3 | Headline figures explained by plain-text links (p.3, 5, 15) | Built under NF-12AB: each Lead opens How it adds up in place |
| F4 | Cash planning opens on next month while a bill is due this month (p.8) | Fixed (A05): `tests/test_pc_audit_fixes.py` |
| F5 | Budget's header holds two page actions (p.7) | Fixed (A05): Next month is in More actions |
| F6 | Buys shown red like spending (p.12) | Fixed (A03): no tone on a buy or sale |
| F7 | Needs you says 3 and holds 5 (p.3) | Fixed: the count is every item (owner pick, 2026-11-22; A09.2) |
| F8 | Day by day, Cash flow, Month by month folded on Spending (p.5) | Not done: the answer fits one screen and the rest opens on request (owner, IV-12Z) |
| F9 | Replace the treemap with labelled bars (p.5-6) | Not done: A12 and A13 set the treemap; seven bars break A16 "four, then Other" |
| F10 | Whole EGP in Transactions (p.12) | Not done: A06.1, rows show piastres when there are any |
| F11 | Remove the floating round button (p.3, 16) | Not done: the page jump (A10.6) shows only on scroll or near the corner; full-page captures scroll |
| F12 | Month names, not 2026-11, in period chips (p.16) | Fixed: the control reads "Nov 2026" and opens the picker (owner pick); A05 and A10.2 drawings updated in both repos |
| F13 | Page titles differ from the sidebar (Safety › Reserves, Settings › Your data) and Settings shows the version twice (p.10, 15) | Fixed: the first tab carries the section's name (A05); one version line |
| F14 | The phone's Home calls cash only In your accounts (p.16) | Fixed: Cash and banks (owner pick); Glossary row |
| F15 | Next 7 days is seven boxes, six empty (p.3-4) | Fixed: a list by name with Pay (owner pick), three then "+n more" |
| F16 | Cash planning's Free cash, Due before payday and Lowest point repeat its Lead (p.8) | Not done: A13.1 sets Cash planning's four KPI cards |
| F17 | Notes column, truncated names, empty chart areas, the 400 gap, the afford form (p.5, 7, 8, 11, 12) | Fixed in the follow-up (owner: "fix all small elements", 2026-11-22): names get the width (Notes stays the spare column, IV-12W), Rows per page one quiet line, treemap names wrap, Average payment and Everyday spending get their visual, Not yet given a job opens on its rows, Brokerage cash says it is not in Portfolio value, the afford form on one line |
