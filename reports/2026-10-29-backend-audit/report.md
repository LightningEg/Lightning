# Backend audit: exchange-rate date boundary

Date: 2026-10-29 · Author: Codex
Repository: app · Reviewed commit: `14be69fa0b89cad4e0e836ce4eee839d32fde593`

## Scope and method

Reviewed the prior engine audit and its open follow-ups, the exchange-rate lookup and date validation, and exercised the existing Mohab year and engine regression tests. The checkout predates remote main `81ca999df62d35ec4b9e815b4076a2b501ca24b1`; the intervening changes do not touch the exchange-rate implementation or its tests. All data used was dummy data.

## Finding

Low: date input accepts `0001-01-01`, but a foreign exchange lookup on that date raised `OverflowError` while calculating the 45-day search floor. Clamp the floor to the earliest supported date; preserve the ordinary 45-day cutoff. `tests/test_fx_rates.py::test_rate_lookup_at_start_of_calendar` checks missing, present and expired rates at this boundary.

The PC Mohab year passed on the reviewed checkout before the fix; `tests/test_fx_rates.py` passed with the fix. A later local test-client startup stalled; the full suite needs CI verification.

## Limits

This is a targeted audit, not proof that the whole engine is free of bugs. The journal and restore implementation were outside scope because those files were claimed. The earlier audit's open findings, including 2J, 2Z, 5J, 7R and 7S, remain; some require a product decision. Native device and power-loss behavior were not tested.
