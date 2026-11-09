---
title: The three "explain this figure" pages have no way in - /explain/owned, /explain/free-cash and /explain/flow are built and tested, and nothing links to them
type: polish
pillar: understand
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude
app_version: 2.1.2
commit: 24e3cf8
---
## Report
Found by [r32](../1-easy-to-contribute/r32-code-review-and-loose-ends/report.md) F13. `lightning/ui/routes/dashboard.py:585` serves `/explain/{kind}` for `owned`, `free-cash` and `flow`: the figure's parts as rows, its meaning from `core/figures.py`, freshness notes (`c.freshness.for_what_you_own`, `for_free_cash`) and a way back. `grep -rn "explain/" lightning/ui --include=*.html --include=*.js` prints nothing, and the link graph of 162 PC pages and 182 phone pages has no link to them. `tests/test_ui.py` and `tests/test_freshness.py` are their only visitors. `lightning/ui/sections.py` still lists `/explain` under the Overview tab.
Pull request #460 (not merged when this was written) proposes NF-12J, "every headline figure explains itself in place". If it has merged, do this item as its first step and say so there.
## Fix
Smallest useful change: give each page its one way in, from the figure it explains.
1. `lightning/ui/templates/dashboard/index.html`: the Lead or KPI that shows What you own, Free cash and Net flow each gets the guideline's quiet link (run `python tools/guideline.py A09` and `A08` for the allowed form: a text link under the figure, never a button) to `/explain/owned?<the page's query>`, `/explain/free-cash?...`, `/explain/flow?...`. Find the three figures with `grep -n "what_you_own\|free_cash\|net_flow" lightning/ui/templates/dashboard/index.html`.
2. Phone: only if `lightning/ui/templates/phone/` has a template for `dashboard/explanation.html`; if not, leave the phone alone (a phone route never draws a PC template) and note it in the item's commit.
3. Tests: `tests/test_ui.py`: the Overview's HTML contains the three addresses; each answers 200. Run Mohab and check A16 ("One figure on two pages: one home, a link" is satisfied: the explain page is the figure's parts, not a second home).
If the owner would rather remove them: delete the route, `dashboard/explanation.html`, the `/explain` prefix in `sections.py` and the tests, and move the freshness notes test to the planning inputs page that also shows them. Ask with the question tool before choosing (options: link them (recommended) / remove them).
## Done when
Each explain page is reachable in one click from its figure, or all three are gone. Release-note: `understand: What you own, Free cash and Net flow each open a page that shows their parts.`
---
