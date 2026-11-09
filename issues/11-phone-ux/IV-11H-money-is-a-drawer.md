---
title: Money is 21 plain rows under Net worth, wears the old More icon, and its Settings is the PC's
type: polish
pillar: everywhere
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T12-T14, shot `en-money-full.jpg`, `x-settings.jpg`. Under Net worth: Accounts
(underlined like a link), Coming up, then Report, What you owe, Investments, Goals and reserves, Financial health, Cash planning,
Spending, Weekly review, All settings, Categories, Counterparties, Rules, Devices, Data checks. The tab icon is "···" (More, retired).
Settings is the PC page: Sale factors, Target allocation, Price files, "another computer", no Privacy, no licences, no delete.

## Fix

Files: `lightning/ui/templates/phone/money.html`, `phone/base.html` (tab icon), the phone Settings template.
- Money keeps C11.3's order with figures on each row (What you owe 66,500, Investments 177,903, Goals 3 of 4 funded); the
  analysis rows (Report, Cash planning, Spending, Weekly review) become one "Reports and reviews ›" row; settings rows leave Money for ⚙.
- The Money tab gets a wallet or coins icon; "Accounts" is a plain heading with "See all ›".
- Phone Settings: Appearance, Language, This phone (lock, fingerprint, Recents), Bank SMS, Backup, Privacy, About and licences,
  Delete this profile; the rest "Best on your PC" (C11.3).
Done when: `/money` has at most 12 rows below the hero at 412 px and every row carries a figure or opens one place; tests updated.
