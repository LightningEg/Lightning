---
title: Visual flow acceptance on PC and phone
type: owner
area: product
status: ready
created: 2026-10-25
by: Codex
---

**Built.** Direct phone page picker, answer-first Overview, decision-first review and missing-price tasks, quieter recurring rows, budget and register labels. Existing calculations, brand, glossary and five bottom slots remain.

**Acceptance.** Review the real Windows/Android pages in English and Arabic, with keyboard/screen reader and existing themes; website screenshots need later recapture. Browser evidence is not physical-device acceptance.

**Read:** [Audit 7](../../reports/2026-10-25-app-visual-flow/report.md).

**Browser regression follow-up · 2026-10-26.** The documentation reorganization's full local suite found six existing failures in `tests/test_feedback_fixes_browser.py`: four `test_forecast_bars_share_baseline` variants expect a 12px bar but see a hidden 0px element, and two `test_savings_picture_browser` variants try to open a hidden summary. All six reproduce on clean main `3edd187`, with no documentation changes, using `python -m pytest tests/test_feedback_fixes_browser.py -k 'forecast_bars_share_baseline or savings_picture_browser' -q`. Reconcile these expectations with the new visual flow; do not count a CI skip without system Chromium as browser acceptance. Documentation and packaging checks pass independently.
