package org.lightning.app;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.view.WindowManager;

/**
 * "Hide in recent apps" (NF-11B6, r29 S6): balances must not show in the Recents card. On by default; the switch
 * sits in Settings › This phone (Python's AndroidScreen in lightning_android.py calls hidden() and setHidden()).
 * The choice belongs to this phone, not a profile, so it lives in the app's own preferences.
 *
 * API 33 and up: Recents gets a blank card (setRecentsScreenshotEnabled), and screenshots still work. Below 33
 * Android has no such switch, so FLAG_SECURE blanks the card and also blocks screenshots while it is on.
 */
public final class ScreenBridge {
    private static final String PREFS = "lightning-screen";
    private static final String KEY = "hide_in_recents";
    static volatile Activity activity;

    private ScreenBridge() {}

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
        SharedPreferences prefs = current.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        prefs.edit().putBoolean(KEY, hide).apply();
        current.runOnUiThread(() -> apply(current));
    }

    /** Called from onCreate before the first frame, and again whenever the switch changes. */
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
