package org.lightning.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;

/**
 * Reminders while Lightning is in the background (IT-11J). A periodic job, not the dataSync foreground service: Play
 * allows `dataSync` only for moving data, and a reminder check moves none. The job asks the app's own server for the
 * due list with the session the open window left in memory (MainActivity.reminderCookie), exactly as the window does;
 * nothing about a reminder is written to disk. When that session is gone (the profile locked, or Android ended the
 * process) there is nothing to ask, so the job cancels itself until Lightning is opened again.
 */
public final class ReminderJobService extends JobService {
    private static final int JOB_ID = 47515;
    private static final long PERIOD_MILLIS = 15 * 60 * 1000L;  // Android's minimum periodic interval
    private static final long FLEX_MILLIS = 5 * 60 * 1000L;

    /** From MainActivity.onStop when reminders are on: check every 15 minutes while the app is away. */
    static void schedule(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler == null || scheduler.getPendingJob(JOB_ID) != null) return;
        scheduler.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(context, ReminderJobService.class))
                .setPeriodic(PERIOD_MILLIS, FLEX_MILLIS)  // the server is on this phone: no network needed
                .build());
    }

    /** From MainActivity.onStart: the open window polls by itself. */
    static void cancel(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler != null) scheduler.cancel(JOB_ID);
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            ReminderNotifications.PollResult result = ReminderNotifications.check(
                    this, MainActivity.reminderOrigin, MainActivity.reminderCookie);
            if (!result.sessionAvailable || !result.enabled) cancel(this);  // nothing to ask until the app opens
            jobFinished(params, false);
        }, "lightning-reminder-job").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return false;  // the next period tries again
    }
}
