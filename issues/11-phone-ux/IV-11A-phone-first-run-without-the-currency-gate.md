---
title: Phone first run - every Add is greyed out until "Save currencies" is pressed, and an empty Transactions says "Nothing matches"
type: polish
pillar: everywhere
size: S
model: sonnet
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F7 ([report](../12-desktop-ux/r26-user-test-pc-and-phone/report.md), [evidence](../12-desktop-ux/r26-user-test-pc-and-phone/evidence/10-phone-first-run.png)). A new profile's Home lists bank, cash, certificates, brokerage and gold, each with Add greyed out, under "Save your currencies first.", though EGP is already selected: the first thing a new user does is press a button that changes nothing. With no transactions, Transactions says "Nothing matches.", as if a filter hid rows. Cash planning shows Free cash 0 and Safe to spend 0 twice each. (r20 P11 named day-one zeros on other tabs; these three were not covered.)

## Fix

The profile currency is saved as EGP when the first account is added, and the Add buttons work at once (other currencies stay optional below). Empty Transactions says "No transactions yet" with Add and Import. Empty Cash planning shows each zero once. Tests on a fresh phone profile: Add works without Save currencies; the empty-state text.
