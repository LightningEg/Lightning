---
title: Extend local planning with scenario comparisons and bill-change alerts
type: feature
pillar: plan
size: L
status: building
post: no
created: 2026-11-03
by: Codex
app_version: 1.5.4
commit: 89848dc0e4ce35bb18f72e861c7c620d8052fae4
repo: app
---

## Report

[Smart-feature recommendations 2 and 3](../../reports/2026-11-03-code-quality-and-smart-features/report.md). The app already has forecasts, recurring suggestions, Needs you and import duplicate checks. These proposals extend those services; they do not replace them or authorize implementation automatically.

## Fix

Keep calculations in Python. Preview only; never post, delete or change a plan without a separate explicit user action. Integrate with NF-7L and retain dismiss/snooze behavior.

## 7X1 Specify scenario inputs and comparisons · M

Define salary-delay, purchase and bill-change inputs, baseline date, assumptions and lowest-balance/shortfall outputs. Done when examples cover insufficient history and pending/overdue income without counting it twice.

## 7X2 Calculate read-only scenarios · M

Needs 7X1 agreed first. Pass overrides into a pure forecast projection. Done when deterministic fixtures show expected differences and database/plan snapshots are unchanged.

## 7X3 Present scenario comparisons · M

Needs 7X2 merged first. Compare baseline and scenario with visible assumptions and an explanation. Done when PC/phone and Arabic workflows have acceptance tests and no preview writes occur.

## 7X4 Define and detect bill drift and repeated charges · M

Use merchant/account/currency identity and robust historical ranges. Exclude transfers/refunds and legitimate repeated purchases; treat variable utilities separately. Done when labelled synthetic fixtures measure both useful detections and false alerts.

## 7X5 Show reviewable alerts in Needs you · M

Needs 7X4 merged first. Show supporting transactions and explain the threshold. Done when confirm, dismiss and snooze are durable and no alert automatically deletes or posts money.

Owner requested implementation of Section 7 on 2026-11-04; migration alone is excluded.

## Implementation and contract · 2026-11-04

The 90-day comparison uses the existing dated scheduled-cash projection, not the variable-budget monthly estimate. Optional overrides delay one outstanding income occurrence, replace one bill occurrence amount, and add a dated purchase in an explicitly chosen cash account. It invents no income average; overdue income stays excluded unless explicitly rescheduled, paid/early-received income stays excluded, and missing FX makes combined values unavailable. Baseline/scenario lowest day-end cash and first shortfall include dates and assumptions. No preview writes occur.

Bill warnings require an active monthly bill/subscription with a confirmed merchant, account and category. Fixed bills need three single-charge monthly observations with a 21–40 day cadence and a historical range within 20%; drift exceeds max(20% of median, 4 MAD). Possible repeats require two charges within three days, each within max(5%, 3 MAD) of the usual amount. Utilities need six observations and exceed max(50%, 6 MAD); no repeated-utility inference. Refunds suppress current-period inference. Warning identity uses stable transaction references and evidence; Needs you retains reviewed/restore/snooze preferences. No charge is deleted or plan edited automatically. Labelled fixtures cover positive drift/repeats, ordinary changes, unstable/insufficient history and utilities; exact projection and bilingual frame tests pass. Full-suite and PR validation remain.
