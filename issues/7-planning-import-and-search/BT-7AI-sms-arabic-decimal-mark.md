---
title: A bank message with the Arabic decimal mark is read as the wrong amount (147.87 becomes 87)
type: bug
look: technical
severity: high
pillar: capture
size: S
model: sonnet
status: ready
created: 2026-11-09
by: Claude
skills: bug-hunt
app_version: 2.1.2
commit: 90f0190
repo: app
---

## Report
[r31](r31-logging-entries/report.md) S1. `parse_sms("تم خصم ١٤٧٫٨٧ جم من بطاقة الخصم المباشر رقم ١٢٣٤ عند كارفور يوم ٠٦/١١/٢٦")`
returns amount 87: Arabic-Indic digits are translated (`_DIGITS`) but the Arabic decimal mark `٫` (U+066B) is not, so the
number pattern starts after it. The Arabic thousands mark `٬` (U+066C) has the same gap. The row is marked "check this",
but the amount shown is wrong. Reproduce: `python issues/7-planning-import-and-search/r31-logging-entries/evidence/sms_battery.py` (last line).

## Fix
Translate `٫` to `.` and drop `٬` where the digits are translated (`parse_sms`, `_clean`, `prefill`). Test (the SMS tests): the message above reads 147.87; `١٬٢٥٠٫٥٠` reads 1250.50.
