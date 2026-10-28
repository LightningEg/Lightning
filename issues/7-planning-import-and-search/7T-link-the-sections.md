---
title: Link the sections - every transaction, person and account shows what it touches
type: feature
area: planning
status: new
created: 2026-10-28
by: Claude
commit: 9ca53bd
repo: app
---

## Report

The links are stored but each screen shows only part of them. A transaction has two half pages: `/transactions/{id}` (budget line, reserve) and `/activity/{id}` (source, plan, claim; `workflows/activity.py` `summary`). Counterparties are a list only. An account never shows what depends on it. Audit 9 part D: `../../reports/2026-10-28-loose-ends-and-linking/report.md`. Related: 7L4 (pair reimbursements), 3G §4.6 (budget row to its bill), 3AD (phone transaction sheet). Every figure is computed in a Python service; plans move no money.

## 7T1 What this transaction touched

One page and one shared PC/phone partial: budget line and what is left, the bill or loan it settled, reserve, claim, import or SMS source, the rule that set its category, history, and one-tap suggested links. Merge the two detail pages. Nothing new stored.

## 7T2 A page per counterparty

`/counterparties/{id}`: spending by month (`ReportingService.spending_by_counterparty`), planned items, reserves, claims they owe, money held for them (`money_from_others`), aliases and rules.

## 7T3 What depends on this account

Bills it pays, gam'eyas it funds, certificate interest it receives, reserves, the first date it goes below zero (`planning/dated_cash.py`); archiving warns first.

## 7T4 Tag totals

A tag such as `#umrah2026` gets one total across categories and accounts, compared with its reserve (`transactions/tags.py`, `reserve_transaction_links`).

## 7T5 Salary-day cascade

When the real salary settles its planned income, Needs you shows bills before next payday, reserves to refill, goal top-ups and safe to spend, opening the payday allocation filled in (`workflows/salary_setup.py`, `planning/funding.py`). Builds with 7L2.

## 7T6 A reserve tied to its bill

Nullable `cash_reserves.planned_item_id`; the bill shows how much is saved, paying it draws the reserve. Waits for the owner's calls on 7M and 7R.
