---
title: Profiles are public and on the leaderboard by default; no age requirement
type: feature
area: website
status: ready
created: 2026-10-27
by: Claude
repo: website
---

## Report

Owner, 2026-10-27: "privacy settings should be public by default, people should opt out of being shown on leaderboard
not the other way around, i dont need them to be 18 to participate". [Audit](../../reports/2026-10-27-store-and-community/report.md) P1.

## Fix

- Migration: `member_profiles` defaults `visibility='public'`, `show_on_leaderboard=true`; drop the minors trigger and the two `*_needs_adult` constraints; `adult_confirmed` defaults true and stops gating (leaderboard, stories, directory, profile); existing members keep what they chose.
- Account page: remove "I am 18 or older"; the two switches read *Show my profile* and *Show me on the leaderboard*, on, with one line on what is shown. Sign-up states it once. Privacy page updated, English and Arabic.
- Owner risk to note in the PR: members under 18 can now be public and pay by InstaPay; the terms should say a parent pays for a minor.
