package org.lightning.app;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.Telephony;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;

/**
 * Bank SMS for the Python side (lightning.sms_imports.SmsSource, adapted in lightning_android.py): whether
 * Lightning may read SMS, the system's permission question, the inbox since a time, and texts shared into the
 * app. Nothing here keeps a message: Python reads them into the locked profile's review and forgets them.
 */
public final class SmsBridge {
    static final int REQUEST_SMS = 2;
    private static final int MAX_MESSAGES = 500;
    static volatile Activity activity;
    /** The sender with spaces and one leading + taken off (SQLite, run by the SMS provider). */
    private static final String BARE = "(CASE WHEN substr(replace(coalesce(address, ''), ' ', ''), 1, 1) = '+' "
            + "THEN substr(replace(coalesce(address, ''), ' ', ''), 2) ELSE replace(coalesce(address, ''), ' ', '') END)";
    /** Never a person (NF-11B2, Play's SMS policy): the provider leaves out every sender that is a phone number, the
     *  PERSON rule of lightning/sms_imports.py (^\+?\d{7,}$), so a person's message never reaches the app. Banks
     *  send from a name (CIB, NBE) or a short code, which pass. */
    static final String NOT_A_PERSON = "NOT (length(" + BARE + ") >= 7 AND " + BARE + " NOT GLOB '*[^0-9]*')";
    private static final List<String> shared = new ArrayList<>();

    private SmsBridge() {}

    public static String permission() {
        Activity current = activity;
        if (current == null) return "unavailable";
        return current.checkSelfPermission(Manifest.permission.READ_SMS) == PackageManager.PERMISSION_GRANTED
                ? "granted" : "not_granted";
    }

    public static void request() {
        Activity current = activity;
        if (current == null) return;
        current.runOnUiThread(() -> current.requestPermissions(new String[]{Manifest.permission.READ_SMS}, REQUEST_SMS));
    }

    /** The inbox after `afterMs` from senders that are not people, oldest first, as JSON [[sender, body, receivedMs], …]. */
    public static String since(long afterMs) {
        JSONArray out = new JSONArray();
        Activity current = activity;
        if (current == null || !"granted".equals(permission())) return out.toString();
        String[] columns = {Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE};
        try (Cursor cursor = current.getContentResolver().query(Telephony.Sms.Inbox.CONTENT_URI, columns,
                Telephony.Sms.DATE + " > ? AND " + NOT_A_PERSON, new String[]{Long.toString(afterMs)}, Telephony.Sms.DATE + " ASC")) {
            if (cursor == null) return out.toString();
            while (cursor.moveToNext() && out.length() < MAX_MESSAGES) {
                JSONArray row = new JSONArray();
                row.put(cursor.isNull(0) ? "" : cursor.getString(0));
                row.put(cursor.isNull(1) ? "" : cursor.getString(1));
                row.put(cursor.getLong(2));
                out.put(row);
            }
        } catch (SecurityException refused) {
            // The permission was taken away meanwhile: nothing to read.
        }
        return out.toString();
    }

    static void share(String text) {
        if (text == null || text.trim().isEmpty()) return;
        synchronized (shared) {
            if (shared.size() < 50) shared.add(text.length() > 4000 ? text.substring(0, 4000) : text);
        }
    }

    /** Texts shared into Lightning since the last call, as a JSON array; the list is emptied. */
    public static String takeShared() {
        synchronized (shared) {
            JSONArray out = new JSONArray(shared);
            shared.clear();
            return out.toString();
        }
    }
}
