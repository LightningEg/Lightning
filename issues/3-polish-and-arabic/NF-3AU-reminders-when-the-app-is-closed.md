---
title: Reminders only reach Windows and Android while the app (or its sync service) is running
type: feature
pillar: everywhere
size: M
model: opus
status: new
created: 2026-11-05
by: Claude
---

## Report

Reminders are native (Windows balloon in `lightning/desktop/window.py`, Android notification in `ReminderNotifications.java`), but both poll `/reminders/due.json` from a running process. With the app closed, a bill due tomorrow is not announced on Windows, and on Android only while `SyncService` is alive. See X-11 in 3H.

## Fix

Decide with the owner how far to go: a Windows scheduled task or login helper that checks due reminders against the encrypted profile without opening the window, and an Android periodic job (WorkManager) that does the same. Reminders must stay opt-in and never expose figures on a locked profile. Test: a due-tomorrow bill produces one notification with the app closed.
