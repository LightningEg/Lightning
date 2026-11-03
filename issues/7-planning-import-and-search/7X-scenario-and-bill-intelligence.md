---
title: Extend local planning with scenario comparisons and bill-change alerts
type: feature
pillar: plan
size: L
status: new
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

Not posted: a proposal awaiting prioritization and threshold/product decisions.
