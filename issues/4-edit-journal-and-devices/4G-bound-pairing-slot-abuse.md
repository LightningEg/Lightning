---
title: Bound unauthenticated pairing work and pending slot occupation
type: tech
area: devices
status: building
created: 2026-10-26
by: Codex
skills: feedback-review
---

## Report
Three unauthenticated requests can exhaust a pairing window; a valid public number-match request can occupy its only slot until the window ends. Add bounded peer/global request budgets before the shared runtime mutex, short pending leases, deterministic cleanup, authenticated cancellation and safe retries. Preserve explicit approval, password verification and expiry; do not let admission retries or restart reset security budgets.

## Investigation
Owner authorized all improvements after backend review. No financial calculations or password/recovery-key scheme change.

## Fix
Design pending independent review.
