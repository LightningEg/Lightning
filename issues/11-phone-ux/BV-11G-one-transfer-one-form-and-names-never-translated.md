---
title: The same transfer reads two ways on Home and Activity, a day's net shows on one date only, and account names get translated
type: bug
look: visual
severity: medium
pillar: everywhere
size: M
model: sonnet
status: ready
created: 2026-11-09
by: Claude Opus 5.5
---

## Report

Report [r29](r29-google-play-readiness/report.md) T9, A3, A5. Home: "To Vodafone Cash −1,000"; Activity: "CIB Payroll → Vodafone
Cash 1,000" (A16: one figure, one form). Activity shows a day's net only on 2026-11-05 ("−2,500"). In Arabic the account "Cash
wallet" is "محفظة نقدية" on Home (the HTML translator matched "To Cash wallet") and "Cash wallet" on Activity: names the person
typed must never be translated. "داخل +٤٦٬٨٣٣ ، خارج" has a space before the comma.

## Fix

Files: `lightning/ui/templates/phone/partials/txn.html`, `lightning/ui/i18n.py` (`localize_html`, `_translate_piece`), the Activity template.
One transfer label for both lists (from → to, unsigned on all-account lists, as 3AN8 decided); a day header shows its net on every
day or on none; user-entered names are wrapped (`<bdi translate="no">` or a `data-name` marker) and `_translate_piece` skips them.
Done when: tests render Home and Activity in Arabic and the account's typed name appears unchanged in both, and the same transfer
has the same text on both pages.
