---
title: Reminder checks start the dataSync foreground service when the app leaves the screen; Play may reject that as not data sync
type: tech
pillar: everywhere
size: M
model: opus
status: ready
created: 2026-11-09
by: Claude
post: no
---

## Report

`MainActivity.onStop` starts `SyncService` (foreground type `dataSync`) whenever reminders are on, with the note
"Checking enabled reminders", even when no pairing or hand-back is open; `SyncService` then polls
`ReminderNotifications.check` with the in-memory `MainActivity.reminderCookie`. Play's foreground-service policy
allows `dataSync` only for transferring data, so the declaration in `docs/google-play.md` › Foreground service
(and its video) covers the pairing/hand-back use but not this one. Owner, 2026-11-09: fix it before the first Play
submission (NF-11B), not after a rejection.

## Fix

`onStop` starts `SyncService` only when `background_note` is not empty (a pairing or lent ledger). Reminder checks move
to a scheduled job (the `JournalSyncJobService` / `JournalSyncScheduler` pattern, or WorkManager-free `JobScheduler`),
which cannot use the WebView session cookie after the app is gone: the job needs its own way to read due reminders
(for example a reminder summary the app writes on stop, or a short-lived token the loopback server accepts for the
reminders endpoint only). Remove the "Checking enabled reminders" risk row from `docs/google-play.md`. Tests: the
manifest/Java checks in `tests/` that cover `SyncService` and reminders; on the phone, reminders still notify with the
app closed and no foreground notification appears unless pairing or hand-back is open.

Not posted: it touches the background service and the loopback server's authentication.
