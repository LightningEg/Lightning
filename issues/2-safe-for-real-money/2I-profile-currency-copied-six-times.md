---
title: Changing the profile currency leaves the Currencies tab on the old one until the app restarts
type: bug
area: currencies
status: ready
created: 2026-10-21
by: Claude
app_version: 1.3.0
commit: 6e1c043
repo: app
---

## Report
Found by [Audit 4](../../reports/audit-4.md) §2. Severity: medium (a wrong list on a new profile).

The profile currency is copied into six service attributes. Two functions refresh them, and both miss
`reporting.fx_positions.base`:
- `bootstrap.py:115` (`set_profile_currency`)
- `sync/journal/areas/settings.py:21`

Reproduced: a new profile set to USD lists USD as a foreign currency until it is reopened. New-profile setup
(`runtime/session.py:298`) takes this path.

## Fix
One source for the currency: services read `settings.base_currency`, or one refresh function that both callers use. Test: set
USD, then the Currencies tab lists no foreign currency without a reopen.
