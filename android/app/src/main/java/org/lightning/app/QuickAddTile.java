package org.lightning.app;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.TileService;

/** A Quick Settings tile (phone roadmap M8): one tap from the notification shade opens Add, amount first, through
 *  the same safe in-app link path as a reminder (reminder_href, checked by ReminderNotifications.safeHrefForActivity). */
public class QuickAddTile extends TileService {
    @Override
    public void onClick() {
        Intent open = new Intent(this, MainActivity.class).setAction("org.lightning.app.OPEN_REMINDER")
                .putExtra("reminder_href", "/accounts/add-transaction")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 7, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        } else {
            startActivityAndCollapse(open);
        }
    }
}
