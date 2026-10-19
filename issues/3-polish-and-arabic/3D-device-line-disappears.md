---
title: The borrowed and lent line, with Hand back, disappears after five seconds
type: bug
area: accounts
status: new
created: 2026-10-15
by: Claude
github: 36
skills: website-sync
app_version: 1.1.0b1
commit: f5f551c
repo: app
---

## Report
Found while recapturing the website's phone-to-PC screens (two real profiles, the PC borrowing).
`base.html` and `phone/base.html` render the device line as `<div class="flash device-line">`; `static/app.js` `initFlashMessages` removes every non-error `.flash` after 5,000 ms.
So "Borrowed from Mohab's phone" and its **Hand back** button vanish from each page five seconds after it loads; on the phone, "Lent to Office PC · read only" and **Devices** do too.
While it shows, it floats over the page title on the phone (360 px) instead of sitting in the flow.
Expected: a lasting status (not a toast) while the ledger is borrowed or lent, in the flow, with its action. Severity: medium (the way to hand back hides itself).
