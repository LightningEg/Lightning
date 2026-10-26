---
title: The net-worth bridge check cannot fail - its valuation change is whatever is left over
type: tech
area: reporting
status: ready
created: 2026-10-26
by: Claude
skills: number-audit
app_version: 1.4.2
commit: 705945c
repo: app
---

## Report

Severity: medium. Found by [Audit 8](../../reports/2026-10-26-engine-audit/report.md) (A2). The bridge (`reporting/service.py`, `bridge`) computes each holding's revaluation as end value − start value − flows, so `expected_closing` equals `closing` minus internal lines, which `validate_posting` already keeps at zero. Corrupting a line's base amount ×10, or adding 5,000 to a valuation, still passes, and books the difference as "revaluation" on EGP cash. Audit 8 added an independent check (profile-currency cash at face value) and removed the other tautological check (categorized vs reported spending); the bridge check remains.

## Fix

Derive the valuation change independently: from posted VAL journals plus the change since the last checkpoint, or at least require zero revaluation on profile-currency cash. Test with a corrupted base amount and a patched valuer: both must show ISSUE.
