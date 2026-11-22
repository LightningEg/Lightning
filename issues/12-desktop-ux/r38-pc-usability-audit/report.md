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

## Findings and dispositions

| # | Finding (audit page) | Disposition |
| --- | --- | --- |
| F1 | No Add button outside Transactions (p.1, 13) | Owner: no Add button; adding lives in the account |
| F2 | Overview should lead with Safe to spend (p.3-4) | Owner: Net worth stays the Lead (A09.1; Safe to spend left Overview in 2.5) |
| F3 | Headline figures explained by plain-text links (p.3, 5, 15) | Built under NF-12AB: each Lead opens How it adds up in place |
| F4 | Cash planning opens on next month while a bill is due this month (p.8) | Fixed (A05): `tests/test_pc_audit_fixes.py` |
| F5 | Budget's header holds two page actions (p.7) | Fixed (A05): Next month is in More actions |
| F6 | Buys shown red like spending (p.12) | Fixed (A03): no tone on a buy or sale |
| F7 | Needs you says 3 and holds 5 (p.3) | Counts rows by design (IV-12AA3); asked the owner |
| F8 | Day by day, Cash flow, Month by month folded on Spending (p.5) | Not done: the answer fits one screen and the rest opens on request (owner, IV-12Z) |
| F9 | Replace the treemap with labelled bars (p.5-6) | Not done: A12 and A13 set the treemap; seven bars break A16 "four, then Other" |
| F10 | Whole EGP in Transactions (p.12) | Not done: A06.1, rows show piastres when there are any |
| F11 | Remove the floating round button (p.3, 16) | Not done: the page jump (A10.6) shows only on scroll or near the corner; full-page captures scroll |
| F12 | Month names, not 2026-11, in period chips (p.16) | A06.1 says "November 2026" while A05 draws "2026-09": asked the owner |
| F13 | The rest: page titles vs sidebar, one version line, repeated cards, the 400 gap, the Notes column, truncation, empty chart areas, Next 7 days as a list | Fixed in the follow-up PRs where listed in `issues/INBOX.md` until then |
