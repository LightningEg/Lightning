---
title: Bring existing investments in at once: a positions list and broker statement lines
type: feature
pillar: own
size: L
status: ready
created: 2026-11-05
by: Claude Opus 5.5
---

## Report
Scenario: someone with 8 EGX shares at THNDR and two money-market funds starts using Lightning. From [the
report](../../reports/2026-11-05-import-scenarios/report.md) (F20-F21):
- "Add a holding you already own" takes one holding per form; a new symbol first needs "+ New investment" on another page.
  Ten holdings are about twenty forms.
- The statement import on a brokerage account treats `Buy 100 COMI @ 85.20` and `Dividend ABUK` as ordinary money out and
  in that need a spending category. Only an Interactive Brokers Activity Statement is understood.

## 5N1 Positions list · M
On the brokerage account, "Add holdings from a list": paste or upload `Symbol, Units, Average cost` (THNDR's positions
screen gives these). Each line finds the instrument by symbol (EGX list), shows units × average cost = cost, and creates
missing instruments after the person confirms. One date for all ("As of").

## 5N2 Recognise trade lines in a cash statement · M
In the statement review on a brokerage account, rows reading Buy/Sell N SYMBOL @ PRICE, Dividend SYMBOL, شراء/بيع are
offered as a buy, sell or dividend of that holding instead of a category.
