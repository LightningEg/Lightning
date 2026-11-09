---
title: One door to add an investment: ask what it is first, and list only what can be chosen
type: polish

pillar: capture
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
[r30](r30-investments-beyond-stocks/report.md) E1-E4. The Investments page has no Add button; the only way in is an account page or an
unlabelled gear. Each kind then has its own door: stocks on the broker's page, certificates on a CD portfolio's page
(after creating that account under Transactions › Accounts), jewellery under a physical-asset account, a flat as an
"Other" account. `/investments/new` lists choices it then refuses: the certificate ("Certificates must be held in a
bank-specific CD portfolio."), the gold price references ("only supplies a price"), jewellery items; its Cash account
list offers CD portfolios, the gam'eya and the gold account as places to pay from.

## Fix
*Add investment* on Investments (PC top action, phone sheet) opens five choices: Stock or fund · Certificate · Gold ·
Property · Something else. Each goes to its own short form, creating the holding place (CD portfolio, gold account)
on the way when none exists. Pickers list only valid choices: no price references, no certificates or items in the
trade form; Cash account lists bank, cash and wallet accounts only. Tests: each choice reaches a saved holding from
`/investments` without visiting Accounts; a posted form with a refused asset is still refused by the service.
