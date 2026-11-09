---
title: Certificates read as certificates: their own holding page, payouts as the bank pays them, value that grows, and a nudge at maturity
type: polish

pillar: own
size: L
model: opus
status: new
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

## 12J2 Payouts forecast the way Egyptian banks pay them · M
A monthly payout is forecast as principal x rate x actual days / 365 (`_certificate_events`): the demo certificate
expects 1,808.22 then 1,868.49 while the bank pays 1,833.33 every month (principal x rate / 12). Receipt matching hides
the gap with a 15% tolerance. Forecast a periodic payout as rate x months / 12; keep day-count only for a broken first
or last period. **Done when:** the demo's expected and received interest agree to the piastre and the tolerance can
return to 5%.

## 12J3 A certificate paid at maturity gains value as it earns · M
A compound or at-maturity certificate stays at its principal for years, then its whole interest lands as *Gain from
sales* on the redemption day. Value it at principal plus interest earned to date (from its terms, labelled an estimate),
so net worth and return rise evenly; the redemption then settles the estimate. Money rule: owner decision needed on
whether accrued interest counts in Holdings value before it is paid (ask in the question dialog before building).
**Done when:** Mohab's compound certificate shows a rising value and the period report reconciles.

## 12J4 Maturity and notices · S
Nothing tells you a certificate matured: the only reminder is "interest expected tomorrow" (`workflows/reminders.py`),
and Needs you has no row. Add a Needs you row and a reminder for maturity and for the unlock date, with *Record what
the bank paid* prefilled. Drop "These prices are old ... NBE 3-year certificate (2026-09-01)" for certificates
(`investments/report.py` `explain_period` treats the purchase as a stale price). A rate change (variable certificates)
is dated, not a rewrite of the whole schedule.
