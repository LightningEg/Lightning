---
title: Gold: add a piece and its purchase in one step, pick the price by karat, and show bars with the jewellery
type: polish

pillar: own
size: M
model: sonnet
status: new
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r30](r30-investments-beyond-stocks/report.md) G2-G7. Evidence: [gold account](r30-investments-beyond-stocks/evidence/gold-account.png).
- **Two steps.** *Add item* saves an empty item ("0 pieces · No pieces held"); what you paid and when is a second form
  folded under the row, titled "Purchase, sale, or add an existing holding".
- **A field that is not a choice.** "Gold price reference" must be picked by hand though the karat decides it; 22K has
  no reference of its own, so the person must know to pick the 24K one.
- **Two kinds of gold.** A bar added as Gold (by the gram) lands under "Other tracked holdings" as one line of text,
  outside the table, valued at what was paid (6,200 a gram) while the 24K reference beside it says 5,314; a jewellery
  item follows the reference. The same bar could be either.
- **Labels.** "piece · MANUAL reference", "Coin ·", "0.000 g", amounts with piastres (A16: whole EGP), the page sits
  under Transactions in the sidebar, and its *Cash account* list offers CD portfolios and the broker.

## Fix
One *Add gold* form: what it is (bar, coin, jewellery), weight, karat, pieces, paid (with workmanship), date, paid
from or *I already own it*; it creates the item and posts the purchase together. The reference is chosen from the
karat (22K priced from 21K by purity, as 18K is). Bars and coins bought by the gram appear as rows of the same table
and are valued by the same dated karat price; workmanship is shown as what resale will not return. Plain valuation
labels ("21K price, 9 Nov" / "Your estimate, 9 Nov" / "At cost"). Tests: one post creates item and purchase; a 22K
item saves without a reference; a 24K bar and a 24K coin show the same value per gram.
