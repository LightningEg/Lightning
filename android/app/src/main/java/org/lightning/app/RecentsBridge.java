package org.lightning.app;

import android.app.Activity;
import android.content.Context;
import android.os.Build;
import android.view.WindowManager;

/**
 * Settings › This phone › Hide in recent apps (NF-11B6), for the Python side (lightning_android.AndroidRecents): a
 * phone setting, on by default, kept in the app's own preferences so it holds before any profile is open. When on,
 * the Recents card is blank: setRecentsScreenshotEnabled(false) from API 33, FLAG_SECURE before it.
 */
public final class RecentsBridge {
    private static final String PREFS = "lightning-privacy";
    private static final String KEY = "hide_recents";
    static volatile Activity activity;

    private RecentsBridge() {}

    static boolean hidden(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY, true);
    }

    public static boolean hidden() {
        Activity current = activity;
        return current == null || hidden(current);
    }

    public static void setHidden(boolean hide) {
        Activity current = activity;
        if (current == null) return;
        current.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY, hide).apply();
        current.runOnUiThread(() -> apply(current));
    }

    /** Called at start and after each change. */
    static void apply(Activity current) {
        boolean hide = hidden(current);
        if (Build.VERSION.SDK_INT >= 33) {
            current.setRecentsScreenshotEnabled(!hide);
        } else if (hide) {
            current.getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        } else {
            current.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
        }
    }
}
