---
title: Money lent to others and costs split with others - who owes you what, counted honestly in what you own
type: feature
pillar: own
size: L
model: opus
status: new
created: 2026-11-06
by: Claude
---

## Report

The owner brought this into scope on 2026-11-06 (OW-12F, from audit r26 F9: [report](r26-user-test-pc-and-phone/report.md)); credit cards and receipt photos stay out. Lending to family and friends and splitting a dinner, a trip or a flat's bills are everyday money in Egypt, and today a person can only hide them in notes or a category. What exists to build on: Held for others (money in your account that is not yours), reimbursement claims (`reimbursements.py`: an owned expense someone will pay back, matched to the receipt), Needs you, and the phone's Add sheet. The decision row is in `ai/PROJECT_OVERVIEW.md` ("Obligations count, forecasts never do").

Rules to keep: one ledger records real money; lending moves money out of your account but not out of what you own until you decide it will not come back; a split records only your share as spending; nothing is assumed repaid until the repayment is posted; one person may owe you and you may owe them, shown as one net figure per person.

## Fix

Design first (a short section in this item for the owner), then the steps.

## 12G1 Design: the person, the loan, the split, and where they show · M

Where "Owed to you" sits in What you own and on Accounts, what a person's page shows, how a split looks in the Add sheet, how forgiving a loan moves it to spending; Arabic words. Done when the owner picks from the options.

## 12G2 Money lent and paid back · L

Record a loan to a person from an account; it stays in What you own as "Owed to you" until repaid, partly repaid or written off (then spending, in a category the person chooses). Done when Mohab lends 5,000, is repaid 3,000 and forgives 2,000, and every tab moves by exactly that.

## 12G3 A cost split with others · L

On Add and on a transaction: "Split" with people and shares; your share is spending, theirs is owed to you (reusing reimbursement matching for the repayment). Done when a 1,200 dinner split three ways shows 400 spent and 800 owed, and a repayment clears it once.

## 12G4 Who owes what, per person · M

One net figure per person on the PC and the phone, with "Remind" text to copy and "Settle" that posts the repayment. Done when a person who owes and is owed shows one net figure.

## 12G5 Mohab, Arabic and the guideline · M

Mohab steps for 12G2-12G4, Arabic for every new word, both themes and 320 px. Done when the Mohab year passes with the new steps.
