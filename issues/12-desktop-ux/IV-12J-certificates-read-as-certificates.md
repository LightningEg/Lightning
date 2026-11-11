---
title: Certificates read as certificates: their own holding page, payouts as the bank pays them, value that grows, and a nudge at maturity
type: polish

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
[r30](r30-investments-beyond-stocks/report.md) C2-C8. A certificate is stored as one unit of a stock priced at its principal, and the
screens show it that way. Evidence: [holding page](r30-investments-beyond-stocks/evidence/certificate-holding-page.png),
[certificates page](r30-investments-beyond-stocks/evidence/certificates-page.png).

## 12J1 The certificate's holding page and the certificates page · M
`/investments/holding/<cd>` shows "Price 100,000", "1 certificate", "Unrealized gain 0.0%", "Average cost", a flat
*Price against what you paid* chart, *Buy more* (which opens the stock buy form that then refuses it) and *Against the
risk-free rate* asking for "a T-bill or certificate rate". None of rate, next payout, interest received so far, unlock
date or maturity is on it. Show instead: rate and payout schedule, interest received against expected, next payout and
its date, days to unlock and to maturity, what the bank would pay today (the sale factor). Send *Buy more* to the
certificates page. On `/deposits/<id>` the table leads (name, rate, next payout, maturity, status) and the 12-field buy
form opens from a button; the phone page must not cut the table's last five columns.
**Done when:** no stock word (price, units, average cost, unrealized) is on a certificate's page, PC or phone.

## 12J3 A certificate paid at maturity gains value as it earns · M
A compound or at-maturity certificate stays at its principal for years, then its whole interest lands as *Gain from
sales* on the redemption day. Value it at principal plus interest earned to date (from its terms, labelled an estimate),
so net worth and return rise evenly; the redemption then settles the estimate. **Owner, 2026-11-09:** yes, the value grows as
interest is earned and counts in Holdings value, marked as an estimate.
**Done when:** Mohab's compound certificate shows a rising value and the period report reconciles.

## 12J4 A variable rate is dated · S
Maturity and unlock notices, the prefilled *Record what the bank paid* and the end of "These prices are old" for
certificates are built (`DepositService.attention`, `tests/test_deposit_certificates.py`). Left: a rate change
(variable certificates) is dated, not a rewrite of the whole schedule: store dated rates and let
`_certificate_events` use the rate in force for each period.
