---
title: PC quick add - Enter after a known name skips the empty Account field, and the next word typed replaces the category
type: polish
pillar: capture
size: S
status: new
created: 2026-11-06
by: Claude
---

## Report

Audit r26 F3 ([report](r26-user-test-pc-and-phone/report.md), [evidence](r26-user-test-pc-and-phone/evidence/03-pc-quick-add-category-overwritten.png)). Transactions, Every account view, the add row: type "Koshary El Tahrir", press Enter. The category fills (Eating Out) but focus goes to Category, skipping the required, empty Account field under the name; typing "Cash" sets the category to "Cash", and Save stops on the browser's "Choose an option from the list". Every earlier Koshary row used Cash wallet, yet no account is suggested (the phone's Add remembers the last account). Code: `lightning/ui/static/app.js` (counterparty picker), `templates/register.html` (add row).

## Fix

After a name is picked, focus goes to the first empty required field; a known name fills its usual account (the most recent one used with it) as well as its category. Test (browser): type a known name, Enter, type an account and Enter, amount, Enter saves with the right account and category.
