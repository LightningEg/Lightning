---
title: In Arabic the borrowed and lent line stays English and slides off the phone screen
type: bug
area: arabic
status: new
created: 2026-10-15
by: Claude
github: 37
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
repo: app
---

## Report
Same two-profile setup with both profiles in Arabic (`/settings/locale` ar, Chromium ar-EG).
PC: "Borrowed from Mohab’s phone" stays English beside «رجّع للهاتف». Phone (360 px): the "Lent to Office PC · read only" box sits past the left edge, only "read only" visible.
`runtime/app.py` `device_line` builds the sentence with an f-string, so `tr` never finds it. The website keeps English pairing screens on its Arabic pages until this is fixed. Severity: low.
