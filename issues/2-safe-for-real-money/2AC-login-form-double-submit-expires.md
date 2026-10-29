---
title: Submitting the unlock form twice (Enter and the button) shows "This form expired" on the desktop app
type: bug
look: technical
severity: medium
area: desktop
status: ready
created: 2026-10-29
by: Claude
skills: bug-hunt
app_version: 1.5.0
repo: app
github: 193
---

## Report

[#193](https://github.com/LightningEg/Lightning/issues/193): on the desktop app's login page, pressing Enter and then clicking Login (or the reverse) shows "This form expired. Reload the page and try again." The first submission consumes the one-time form token; the second reuses it.

## Fix

Disable the submit control after the first submission, so a double submit sends one request. Make a repeated token on the login page show the form again with the password field kept empty, not an error page. Test both through the profile-session routes.
