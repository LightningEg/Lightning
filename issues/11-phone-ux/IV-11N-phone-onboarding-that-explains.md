---
title: The phone's first launch explains Lightning and sets up a whole first day: intro, a four-card tour, a six-step setup and the first day's bills
type: polish
look: visual
pillar: feel
size: L
model: opus
status: building
created: 2026-11-20
by: Claude
---

## Report
The owner shared two outside mock-ups (a splash-and-welcome page and a light-user prototype, made by someone who did not know Lightning) as a direction, and asked first whether the setup covers what the app does. It does not.

What the phone does on a first launch today: the native start screen (lockup and a bar) cuts to Welcome (static); setup is "1 of 2" (name, currency, password, security question) and "2 of 2" (recovery key); the empty profile then opens the older welcome page (currencies asked a second time, five account kinds, samples); after one account, Home's first day shows three steps (salary account, payday, first payment).

| What a light user needs | Covered today | Gap |
|---|---|---|
| What Lightning answers (Safe to spend, where money went, net worth) | One sentence on Welcome | No example of any figure before an empty profile |
| Recording is quick (bank SMS, Add) | Only on Money › From SMS | Never offered in setup; the phone's main convenience is hidden |
| A first account with a real balance | Five kinds on one page | Balance is optional and folded; Safe to spend starts at 0 |
| Salary and payday | Home step 2 opens a long Recurring form | No step of its own |
| Cash | One of five kinds | Not made by default; how to keep cash without logging every coin is never explained |
| Bills before payday (Safe to spend needs them) | Not asked | Safe to spend appears without them |
| Fingerprint and SMS | Settings and From SMS only | Never offered |
| Currency | Asked in step 1 and again on the welcome page | Asked twice |
| The word | Password in the app | Guideline C11 still says passphrase |

The mock-ups' gaps against Lightning: no cash, budget or bills; "passphrase"; recovery flows the app already has; pure white setup pages.

## Fix
Owner decisions (2026-11-20, question dialog):
- **Intro:** the start screen opens into Welcome with one short animation that never delays a tap (CSS only, once per launch, skipped by a tap and by reduced motion).
- **Tour** ("How Lightning works", from Welcome; example figures from Python): 1 bank SMS logs itself, how quick; 2 where your money went; 3 Safe to spend; 4 Net worth. The last card ends on Set up Lightning.
- **Setup, six steps:** 1 Your profile, 2 Recovery key, 3 Your first account (name, institution, type, optional balance today; Skip), 4 Your salary (amount, payday, account; Skip), 5 Your cash wallet (made by default; the weekly count story), 6 This phone (bank SMS and fingerprint, each optional). Currency is asked once, in step 1.
- **Home's first day** after setup: Your regular bills (or "I have no regular bills") and Your first payment; a step setup skipped (account, payday) stays on the list.
- **Background:** a soft meadow wash on Welcome, the tour and setup only, never behind a figure; a new phone rule in the guideline, both repos.
- **Word:** password, never passphrase.

Done when: an empty phone profile goes Welcome → tour → six steps → Home's first day → Home; each step's tests pass; Mohab's year passes; Arabic is complete; A16 holds; the guideline copies match.

## 11N1 Intro and tour · M
Welcome's intro animation and the four-card tour with Python example figures. Done when: `tests/test_phone_onboarding.py` covers the tour's cards and figures, and the intro adds no wait before the first tap.

## 11N2 Setup steps 3 to 6 · L
The account, salary, cash and phone steps after the recovery key, currency asked once. Done when: the tests walk an empty profile through every step and every Skip.

## 11N3 Home's first day and the guideline · M
Bills and first payment on Home's first day after setup; the meadow wash and the password wording in the guideline, in both repos. Done when: the first-day tests pass and the guideline copies match.
