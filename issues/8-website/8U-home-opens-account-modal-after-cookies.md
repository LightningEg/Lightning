---
title: Home covers the page with an account invitation right after the cookie choice
type: polish
area: website
status: ready
created: 2026-10-28
by: Claude
repo: website
commit: e8153a1
---

## Report

A first visit to `index.html` (English and Arabic, phone and PC) answers the cookie bar, then 800 ms later `js/site-membership.js` (`invite()`) opens a full-screen modal: "Make Lightning a little more yours … Create a free account". On a phone it covers everything below the hero. The visitor came for a finance app that needs no account (the hero says "No account"), and is asked for one, about Cotton and website themes, before seeing a single product section. It returns every seven days. Two interruptions in a row is the first impression of the site.

## Fix

No modal on arrival. Offer the account where it is earned: a quiet card after the last product section, or after a download, or on a second visit. Keep "Maybe later"'s seven-day memory. Check B-rules for modals with `python ../Lightning/tools/guideline.py --dir guideline B`.
