---
title: Reminders only reach Windows and Android while the app (or its sync service) is running
type: feature
pillar: everywhere
size: M
model: opus
status: ready
created: 2026-11-05
by: Claude
---

## Report

Reminders are native (Windows balloon in `lightning/desktop/window.py`, Android notification in `ReminderNotifications.java`), but both poll `/reminders/due.json` from a running process. With the app closed, a bill due tomorrow is not announced on Windows, and on Android only while `SyncService` is alive. See X-11 in 3H.

2026-11-08, checked against main: still true. Windows: `_native_reminder_loop` (`lightning/desktop/window.py` ~line 62) polls `/reminders/due.json` every 60 s through the open WebView; seen ids go to `%LOCALAPPDATA%/Lightning/native-reminders.json` (`_reminder_prefs_path`). Android: `ReminderNotifications.check` is called from `MainActivity` (~line 461) and from `SyncService.check` every 60 s while that foreground service lives; there is already a `JobScheduler` job (`JournalSyncJobService`, `JournalSyncScheduler`) and no WorkManager dependency. The list comes from `ReminderService.due()` (`lightning/workflows/reminders.py`), opt-in by the `reminders_enabled` setting, and needs an open, unlocked profile: with the app closed the encrypted profile cannot be read, so whatever fires later must be prepared while it is open.

## Decided

- 2026-11-08, owner (3AU1): option 1: a dated schedule with days and kinds only, no figures or names; Windows Task Scheduler and an Android daily job post it. 3AU2-3AU4 as written.

## Fix

The owner picks the approach (3AU1). Then: a small reminder schedule written while the profile is open (3AU2), a Windows scheduled task that shows it with the app closed (3AU3), and an Android job that does the same (3AU4). Reminders stay opt-in; nothing written outside the profile carries a figure, and a locked profile shows none.

## How to work on this item

Each step is one pull request. Read only the files a step names. Run the step's test command, then `python -m pytest tests/test_workflow_views_review.py tests/test_review_decisions.py -q`; delete the step's heading in the same commit. 3AU3 and 3AU4 need a real Windows / Android run as evidence: run the Windows or Android workflow by hand only for those steps (AGENTS.md §2).

## 3AU4 Android: the evidence run · S · opus
Built (2026-11-11): `ClosedReminderJobService.java` (a daily job; reads only `files/reminder-schedule.json`; today's
items as one notice with the kind's fixed sentence, English or Arabic by the phone's language; ids shared with the open
app through `ReminderNotifications.announce`), declared with `BIND_JOB_SERVICE`; `MainActivity.checkReminders` schedules
it while reminders are on and cancels it when off; `lightning_android.start` sets `LIGHTNING_REMINDER_SCHEDULE`
(`tests/test_android_shell.py`). The name `ReminderJobService` was taken by IT-11J's session job. Not persisted across a
reboot: that needs `RECEIVE_BOOT_COMPLETED`, outside `android/permissions` (an owner choice); opening Lightning
schedules it again. The APK builds and passes its permission check (Phone app run 43062171133, PR #533). 3AU3's Windows
run passed the same day (run 43062231933: task created, `--remind` exits 0, task removed). Left: the device check, done
with the owner's phone check (3AY13): app swiped away, a fixture schedule for today, one notification with no figure.
