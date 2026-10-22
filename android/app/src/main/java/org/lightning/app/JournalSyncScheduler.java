package org.lightning.app;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;

/** Android's network-aware, Doze-aware opportunity to catch up journal replicas in the background. */
final class JournalSyncScheduler {
    private static final int JOB_ID = 47514;
    private static final long PERIOD_MILLIS = 15 * 60 * 1000L; // Android's minimum periodic interval
    private static final long FLEX_MILLIS = 5 * 60 * 1000L;

    private JournalSyncScheduler() { }

    static void schedule(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler == null || scheduler.getPendingJob(JOB_ID) != null) return;
        JobInfo job = new JobInfo.Builder(JOB_ID,
                new ComponentName(context, JournalSyncJobService.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(PERIOD_MILLIS, FLEX_MILLIS)
                .build();
        scheduler.schedule(job);
    }
}
