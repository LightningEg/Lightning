package org.lightning.app;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.util.Log;
import com.chaquo.python.Python;

/** Runs one bounded journal catch-up when Android has network and CPU time available. */
public final class JournalSyncJobService extends JobService {
    private static final String TAG = "LightningJournalSync";
    private volatile boolean stopped;

    @Override
    public boolean onStartJob(JobParameters params) {
        stopped = false;
        String files = getFilesDir().getAbsolutePath();
        new Thread(() -> {
            boolean retry = false;
            try {
                String result = Python.getInstance().getModule("lightning_android")
                        .callAttr("sync_journal", files).toString();
                if ("synced".equals(result)) {
                    Log.i(TAG, "Journal catch-up completed");
                } else if ("offline".equals(result)) {
                    Log.i(TAG, "Journal catch-up deferred: cloud is offline or not configured");
                    retry = true;
                } else if ("error".equals(result)) {
                    Log.w(TAG, "Journal catch-up failed; Android will retry");
                    retry = true;
                } else {
                    Log.i(TAG, "Journal catch-up: " + result);
                }
            } catch (Throwable error) {
                Log.w(TAG, "Journal catch-up could not start; Android will retry", error);
                retry = true;
            }
            if (!stopped) jobFinished(params, retry);
        }, "lightning-journal-job").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        stopped = true;
        return true; // constraints changed or Android reclaimed time; retry when it can run again
    }
}
