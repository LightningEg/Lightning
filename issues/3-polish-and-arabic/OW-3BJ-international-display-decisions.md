---
title: Owner decisions for an international look - date display, the Arabic currency label, row decimals, percent sign, dark mode, how Arabic addresses the person
type: owner
pillar: feel
status: new
created: 2026-11-08
by: Claude
---

## Report

Report [r28](r28-international-polish/report.md) F21. The guideline fixes these today; widely used finance apps choose differently. Each needs the owner's pick before a guideline version changes (both repos, guideline rule):

1. **Dates.** A06.1: `2026-11-08`, "30 Sep 2026" crossed out. Revolut, Monzo and YNAB show "8 Nov", "November 2026", relative "Yesterday". ISO reads like a database; in Arabic it shows "٢٠٢٦-١٢-٠١". The phone already says Today/Yesterday; `workflows/review.py:31,251` already writes "%B %Y". Options: keep ISO; human dates on screens and ISO in fields and exports (recommended); human dates everywhere.
2. **Arabic period chip** shows "2026-11" in Western digits on an otherwise Arabic-Indic page ([shot](r28-international-polish/evidence/shots/pc-ar-home.png)): Arabic-Indic, or stays as a "code".
3. **Currency in Arabic:** "EGP" (243× on Arabic pages), جنيه (some translations) or ج.م.
4. **Row decimals:** A06.1 keeps ".00" on PC rows, C10 drops it on the phone; one rule for both?
5. **Percent sign in Arabic:** "%" (88) or "٪" (3).
6. **Dark mode:** A15 is light only; the app ignores the system setting ([shot](r28-international-polish/evidence/shots/pc-en-dark.png)). Keep, follow the system with a dark palette, or leave dark to themes.
7. **Arabic address:** always masculine (اختار 300×). Keep, or a neutral/feminine form in Settings.

## Fix

Record each answer in `ai/PROJECT_OVERVIEW.md` owner decisions; a guideline change lands in both repos the same session; then a polish item per change.
