package org.lightning.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Fetches only the session-guarded same-origin due list. No bridge is exposed to page JavaScript. */
final class ReminderNotifications {
    private static final String CHANNEL = "native-reminders";
    private static final String PREFS = "native_reminder_preferences";

    static final class PollResult {
        final boolean sessionAvailable;
        final boolean enabled;
        PollResult(boolean sessionAvailable, boolean enabled) {
            this.sessionAvailable = sessionAvailable;
            this.enabled = enabled;
        }
    }

    private ReminderNotifications() {}

    static synchronized PollResult check(Context context, Uri origin, String cookie) {
        if (origin == null || cookie == null || cookie.isEmpty()) return new PollResult(false, false);
        HttpURLConnection connection = null;
        try {
            URL url = new URL(origin.toString().replaceAll("/$", "") + "/reminders/due.json");
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(2500);
            connection.setReadTimeout(3500);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Cookie", cookie);
            connection.setRequestProperty("Accept", "application/json");
            int status = connection.getResponseCode();
            if (status == 401 || status == 403) return new PollResult(false, false);
            if (status != 200) return new PollResult(true, false);
            String body = read(connection.getInputStream());
            JSONObject document = new JSONObject(body);
            boolean enabled = document.optBoolean("enabled", false);
            if (enabled && permitted(context)) deliver(context, document.optJSONArray("items"));
            return new PollResult(true, enabled && permitted(context));
        } catch (Exception ignored) {
            return new PollResult(false, false);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static boolean permitted(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null || !manager.areNotificationsEnabled()) return false;
        return Build.VERSION.SDK_INT < 33
                || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }

    private static void deliver(Context context, JSONArray items) {
        if (items == null || items.length() == 0) return;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Lightning reminders",
                    NotificationManager.IMPORTANCE_DEFAULT));
        }
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        android.content.SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        android.content.SharedPreferences.Editor editor = prefs.edit();
        for (String key : prefs.getAll().keySet()) {
            if (key.startsWith("seen:") && !today.equals(prefs.getString(key, ""))) editor.remove(key);
        }
        editor.commit();
        editor = prefs.edit();
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null) continue;
            String id = item.optString("id", "");
            String label = clean(item.optString("label", ""), 120);
            String detail = clean(item.optString("detail", ""), 160);
            Uri href = safeHrefForActivity(item.optString("href", ""));
            if (!id.matches("[A-Za-z0-9._:-]{1,128}") || label.isEmpty() || href == null) continue;
            String key = "seen:" + id;
            if (today.equals(prefs.getString(key, ""))) continue;
            Intent open = new Intent(context, MainActivity.class).setAction("org.lightning.app.OPEN_REMINDER")
                    .putExtra("reminder_href", href.toString());
            int request = id.hashCode() & 0x7fffffff;
            PendingIntent pending = PendingIntent.getActivity(context, request, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            String text = detail.isEmpty() ? label : label + " · " + detail;
            Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(context, CHANNEL) : new Notification.Builder(context);
            builder.setSmallIcon(R.drawable.ic_lightning).setContentTitle("Lightning")
                    .setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
                    .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).setContentIntent(pending);
            manager.notify(request, builder.build());
            editor.putString(key, today);
            editor.commit();
        }
    }

    /** NF-3AU4: one closed-app notice for today's scheduled items (ClosedReminderJobService). The text is the kind's
     *  fixed sentence; a tap opens Lightning, which shows its lock. Ids already shown today (here or by the open app)
     *  are skipped, and these are noted so the open app does not repeat them. */
    static synchronized void announce(Context context, java.util.List<String> ids, String text) {
        if (!permitted(context) || ids.isEmpty()) return;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Lightning reminders",
                    NotificationManager.IMPORTANCE_DEFAULT));
        }
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        android.content.SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        java.util.List<String> fresh = new java.util.ArrayList<>();
        for (String id : ids) if (!today.equals(prefs.getString("seen:" + id, ""))) fresh.add(id);
        if (fresh.isEmpty()) return;
        Intent open = new Intent(context, MainActivity.class).setAction(Intent.ACTION_MAIN);
        PendingIntent pending = PendingIntent.getActivity(context, 47516, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(context, CHANNEL) : new Notification.Builder(context);
        builder.setSmallIcon(R.drawable.ic_lightning).setContentTitle("Lightning").setContentText(text)
                .setVisibility(Notification.VISIBILITY_PRIVATE).setAutoCancel(true).setContentIntent(pending);
        manager.notify(47516, builder.build());
        android.content.SharedPreferences.Editor editor = prefs.edit();
        for (String id : fresh) editor.putString("seen:" + id, today);
        editor.commit();
    }

    static Uri safeHrefForActivity(String value) {
        if (value == null || !value.startsWith("/") || value.startsWith("//") || value.contains("\\")) return null;
        Uri relative = Uri.parse(value);
        if (relative.isHierarchical() && (relative.getScheme() != null || relative.getAuthority() != null
                || relative.getFragment() != null || relative.getPath() == null)) return null;
        return relative;
    }

    private static String clean(String value, int limit) {
        String text = value == null ? "" : value.replaceAll("[\\p{Cntrl}\\s]+", " ").trim();
        return text.length() > limit ? text.substring(0, limit) : text;
    }

    private static String read(InputStream input) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[2048];
        int size;
        while ((size = input.read(buffer)) != -1) {
            if (out.size() + size > 1024 * 1024) throw new IllegalStateException("Reminder response too large");
            out.write(buffer, 0, size);
        }
        return out.toString("UTF-8");
    }
}
