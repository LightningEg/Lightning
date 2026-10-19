---
title: Search doesn't fold Arabic spelling variants and digits (احمد misses أحمد)
type: bug
area: search
status: ready
created: 2026-10-19
by: Claude
github: 51
---

## Report
`ui/routes/search.py` `_score` and `matches` only casefold. `احمد` scores 0 against "أحمد عادل", `٢٠٢٦` 0 against "2026 rent"; ة/ه and ى/ي match only as weak near-spellings. Part of 7D's step 1 (Arabic/English variants), small enough to do now.

## Fix
One folding helper for query and text: أ إ آ → ا, ة → ه, ى → ي, drop tashkeel and tatweel, digits through `core.money.ascii_digits`. Don't touch `counterparties.normalize` (stored). Tests call `_score` directly. GitHub #51.
