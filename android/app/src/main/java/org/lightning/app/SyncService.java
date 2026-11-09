package org.lightning.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import com.chaquo.python.Python;

/** Keeps Lightning listening for the PC while the app is in the background and the ledger is away or a pairing is
 *  open. Shows that it does; stops itself once nothing needs it, or when Android's time limit ends it. */
public final class SyncService extends Service {
    private static final String CHANNEL = "sync";
    private final Handler handler = new Handler(Looper.getMainLooper());

    private Notification notification(String text) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE);
        return builder.setSmallIcon(R.drawable.ic_lightning).setContentTitle("Lightning").setContentText(text)
                .setContentIntent(open).setOngoing(true).build();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager.class).createNotificationChannel(
                    new NotificationChannel(CHANNEL, "Your ledger and your PC", NotificationManager.IMPORTANCE_LOW));
        }
        String note = intent != null && intent.getStringExtra("note") != null ? intent.getStringExtra("note") : "";
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, notification(note), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(1, notification(note));
        }
        handler.removeCallbacksAndMessages(null);
        handler.post(this::check);
        return START_NOT_STICKY;
    }

    /** Every minute: still needed? Update the text, or stop. */
    private void check() {
        new Thread(() -> {
            String note;
            try {
                note = Python.getInstance().getModule("lightning_android").callAttr("background_note").toString();
            } catch (Throwable error) {
                note = "";
            }
            String text = note;  // reminders are ReminderJobService's (IT-11J): this service only moves data
            handler.post(() -> {
                if (text.isEmpty()) {
                    stopSelf();
                } else {
                    getSystemService(NotificationManager.class).notify(1, notification(text));
                    handler.postDelayed(this::check, 60_000);
                }
            });
        }, "lightning-sync-check").start();
    }

    @Override
    public void onTimeout(int startId, int fgsType) {
        stopSelf();  // Android 15's daily limit for data sync: the PC hands back when Lightning is open again
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
