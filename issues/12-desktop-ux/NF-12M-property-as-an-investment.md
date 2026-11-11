---
title: Property as an investment: its own kind, gain from what you paid, instalments, rent and costs
type: feature

pillar: own
size: L
model: opus
status: parked
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r30](r30-investments-beyond-stocks/report.md) P1-P7. Evidence: [flat account](r30-investments-beyond-stocks/evidence/flat-account.png),
[Investments after](r30-investments-beyond-stocks/evidence/investments-after.png). A flat can be entered two ways and neither fits: an
"Other" account (a bank register with a value box) or an *Other Investments* holding, which is only accepted inside
the stock broker.

## 12M1 Real estate is its own class, with the gain from what you paid · M
A flat entered with value 2,500,000 and purchase details "bought for 1,800,000" shows +700,000 on its account page but
Cost 2,500,000 and gain "—" on Investments: the purchase price never reaches the holdings table, Total gain or return.
Both flats land in "Other Investments" (95.8% of the portfolio); `Exposure.REAL_ESTATE` exists but nothing creates it.
A property counts in *Holdings after sale* as if it sold today. Add a Real estate class; cost = purchase price (plus
recorded costs), gain = value less cost; mark it not sellable at short notice. Refuse a property-like holding in a
brokerage, or move the *Other Investments* holding to its own place.
**Done when:** the flat shows Cost 1,800,000, Value 2,500,000, +700,000 under Real estate on Investments.

## 12M2 A property page, not a bank register · M
The page offers "Record your first Money out, Money in, or Transfer", category bulk-edit and *Import statement*. Show
the answer first: value now, since you bought it, value history, the loan and what is left, then *Update value*.
**Owner, 2026-11-09:** property (flat, land, car) lives under Investments, PC and phone.

## 12M3 Paying by instalments (off-plan) · L
Most new flats are bought with a down payment and years of instalments to the developer. Today there is no way to say
"paid 600,000 of 3,000,000": each payment either is household spending or needs a hand-made transfer into the account.
Model the contract (price, paid so far, schedule) on the certificate/gam'eya backbone: instalments are internal
transfers that raise cost. **Owner, 2026-11-09:** you own only what you paid (re-appraisable); the unpaid part is not
a debt and stays out of What you owe; coming instalments are in the forecast and Safe to spend.

## 12M4 Rent and running costs · M
Rent received and maintenance, tax or broker fees belong to the property's return (as dividends and fees do for a
stock). Let a money-in or money-out row name the property; show yield and net return on its page.
