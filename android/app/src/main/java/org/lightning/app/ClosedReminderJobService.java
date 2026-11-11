package org.lightning.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * NF-3AU4: reminders with Lightning closed. Once a day this job reads the reminder schedule the open app wrote
 * (files/reminder-schedule.json, workflows/reminder_schedule.py: days, kinds and opaque ids, never a figure or a name)
 * and posts today's items on the native-reminders channel with a fixed sentence for their kind. It reads only that
 * file: no server, no session, no cookie. A missing or stale schedule, or no notification permission, shows nothing.
 * Scheduled while reminders are on (MainActivity.checkReminders), cancelled when they are off. Not persisted across a
 * reboot (that needs RECEIVE_BOOT_COMPLETED, outside the permission allowlist): opening Lightning schedules it again.
 */
public final class ClosedReminderJobService extends JobService {
    private static final int JOB_ID = 47516;
    private static final long DAY = TimeUnit.DAYS.toMillis(1);
    private static final long FLEX = TimeUnit.HOURS.toMillis(2);
    private static final int STALE_DAYS = 14;
    static final String FILE = "reminder-schedule.json";

    static void schedule(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler == null || scheduler.getPendingJob(JOB_ID) != null) return;
        scheduler.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(context, ClosedReminderJobService.class))
                .setPeriodic(DAY, FLEX)  // a file on this phone: no network needed
                .build());
    }

    static void cancel(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler != null) scheduler.cancel(JOB_ID);
    }

    /** The fixed sentence for a kind (reminder_schedule.KIND_TEXT); null for a kind this build does not know. */
    static String textFor(String kind, boolean arabic) {
        switch (kind) {
            case "payment": return arabic ? "فيه دفعة مستحقة بكرة." : "A payment is due tomorrow.";
            case "gameya": return arabic ? "فيه قسط جمعية مستحق بكرة." : "A gam'eya instalment is due tomorrow.";
            case "zakat": return arabic ? "يوم الزكاة بكرة." : "Zakat day is tomorrow.";
            default: return null;
        }
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                announceToday(this);
            } catch (Exception ignored) {
                // A closed-app notice is a convenience: the open app still shows every reminder.
            }
            jobFinished(params, false);
        }, "lightning-closed-reminders").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return false;  // tomorrow's run tries again
    }

    static void announceToday(Context context) throws Exception {
        File file = new File(context.getFilesDir(), FILE);
        if (!file.isFile() || file.length() > 64 * 1024) return;
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        try (FileInputStream in = new FileInputStream(file)) {   // API 24: read with a plain stream
            byte[] buffer = new byte[4096];
            for (int n; (n = in.read(buffer)) != -1; ) body.write(buffer, 0, n);
        }
        JSONObject schedule = new JSONObject(new String(body.toByteArray(), StandardCharsets.UTF_8));
        if (schedule.optInt("version", 0) != 1) return;
        SimpleDateFormat iso = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        String today = iso.format(new Date());
        Date written = iso.parse(schedule.optString("written", "1970-01-01"));
        if (written == null || new Date().getTime() - written.getTime() > TimeUnit.DAYS.toMillis(STALE_DAYS)) return;
        boolean arabic = "ar".equals(Locale.getDefault().getLanguage());
        JSONArray items = schedule.optJSONArray("items");
        List<String> ids = new ArrayList<>();
        String single = null;
        for (int i = 0; items != null && i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null || !today.equals(item.optString("day", ""))) continue;
            String text = textFor(item.optString("kind", ""), arabic);
            String id = item.optString("id", "");
            if (text == null || !id.matches("[A-Za-z0-9._:-]{1,128}")) continue;
            ids.add(id);
            single = text;
        }
        if (ids.isEmpty()) return;
        String text = ids.size() == 1 ? single
                : (arabic ? ids.size() + " حاجات مستحقة بكرة." : ids.size() + " things are due tomorrow.");
        ReminderNotifications.announce(context, ids, text);
    }
}
