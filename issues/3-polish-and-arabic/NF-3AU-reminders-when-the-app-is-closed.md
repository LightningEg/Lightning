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

## 3AU3 Windows: a daily task shows the schedule with the app closed · M · opus
3AU2 is built: `lightning/workflows/reminder_schedule.py` (`read`, `KIND_TEXT`, `default_path()`), written by `ReminderService.upcoming()` on turning reminders on, on the daily `/reminders/due.json` poll and on lock.
Files: `lightning/desktop/app.py` (argument parser ~line 17), `lightning/desktop/window.py` (`_show_balloon`, the reminder tray icon ~line 301), new `lightning/desktop/reminder_task.py`, new `tests/test_reminder_task.py`.
Do: a hidden `--remind` argument that reads the schedule, shows one Windows notification for today's items (a single "Lightning: 2 things are due tomorrow" when there are several), records shown ids in `native-reminders.json` as the open app does, and exits without opening a window or a profile. `reminder_task.register(exe)` / `unregister()` create and delete a per-user task with `schtasks /Create /SC DAILY /ST 09:00 /TN "Lightning reminders" /TR "\"<exe>\" --remind" /F` (no admin rights; `/Delete /TN ... /F` to remove), called when reminders are turned on or off in the Windows app. A missing or stale (`written` older than 14 days) file shows nothing.
Done when: `tests/test_reminder_task.py` checks the `schtasks` command lines (subprocess mocked) and that `--remind` with a fixture schedule calls the notifier once with no figure, and with no file calls it never: `python -m pytest tests/test_reminder_task.py -q`; then one Windows workflow run by hand shows the task created and removed.

## 3AU4 Android: a daily job shows the schedule with the app closed · M · opus
3AU2 is built: `lightning/workflows/reminder_schedule.py` (`read`, `KIND_TEXT`, `default_path()`), written by `ReminderService.upcoming()` on turning reminders on, on the daily `/reminders/due.json` poll and on lock.
Files: `android/app/src/main/java/org/lightning/app/ReminderNotifications.java` (`deliver`, `safeHrefForActivity`), `JournalSyncScheduler.java` and `JournalSyncJobService.java` (copy their JobScheduler pattern), new `ReminderJobService.java`, `android/app/src/main/AndroidManifest.xml` (a `<service ... android:permission="android.permission.BIND_JOB_SERVICE">` like `.JournalSyncJobService`), `android/app/src/main/python/lightning_android.py` (set `LIGHTNING_REMINDER_SCHEDULE` to a file under the app's files dir; without it nothing is written on Android), `tests/test_android_shell.py`.
Do: a periodic job (once a day, `setPersisted(true)`, no network needed) that reads the schedule file, posts today's items on the existing `native-reminders` channel through `deliver`'s notification code (generic text from the kind; tap opens `MainActivity`, which shows the lock screen), and does nothing when the file is missing, stale or `POST_NOTIFICATIONS` is not granted. Schedule it when reminders are turned on, cancel it when off. No new library (no WorkManager; see skill dependency-change if one seems needed).
Done when: `tests/test_android_shell.py` gains a static test that the manifest declares `.ReminderJobService` with `BIND_JOB_SERVICE`, that `ReminderJobService.java` reads only the schedule file (no `/reminders/due.json`, no cookie) and that its notification text comes from the kind; `python -m pytest tests/test_android_shell.py tests/test_journal_android.py -q`; then one Android workflow run by hand builds the APK, and a device check (app swiped away, a fixture schedule for today) shows one notification with no figure.
