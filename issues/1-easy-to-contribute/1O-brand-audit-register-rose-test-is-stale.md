---
title: The brand audit still says register amounts must not be rose, but the owner decided money out reads rose
type: bug
look: technical
severity: low
pillar: build
size: S
status: ready
created: 2026-10-31
by: Claude Sonnet 5.5
---

## Report
`tests/test_brand_audit.py::test_register_amounts_are_not_strong_rose` fails on `main` when the audit is run with Playwright installed: `/transactions` and `/accounts/1` show money-out amounts in rose (`SPAN.num.amount −15.00` and others). The owner decided on 2026-10-30 that register money out reads in rose (guideline A03, changelog 1.5.4 follow-up #213 and website #145), so the test is out of date, not the screen.

CI does not notice because `pytest.importorskip("playwright")` skips the whole audit there (no Playwright in the lock). A person running `pip install playwright` and `pytest tests/test_brand_audit.py` sees the failure on a clean checkout.

## Fix
1. Change the test to the current A03 rule: register money out is rose, money in is green, and a strong rose is still reserved for what needs you (check `python tools/guideline.py A03`).
2. Decide whether CI should run the brand audit (it needs `playwright` and a Chromium); if not, say in `tests/test_brand_audit.py` and the guideline-audit skill that it runs by hand.
3. `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python -m pytest tests/test_brand_audit.py -q` passes.
