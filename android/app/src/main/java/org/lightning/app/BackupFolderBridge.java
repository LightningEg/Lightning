package org.lightning.app;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.UriPermission;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * A copy outside the app (BT-2AI3), for the Python side (lightning.runtime.outside_copy, adapted in
 * lightning_android.py). The person picks a folder once with the system's folder picker; Lightning keeps the
 * permission to that one folder (takePersistableUriPermission: no storage permission) and writes profile files
 * into it through DocumentsContract. An uninstall leaves the folder. This class only moves bytes and lists
 * names: what to write, when, and what to prune is decided in Python.
 */
public final class BackupFolderBridge {
    static final int REQUEST_FOLDER = 4;
    private static final String PREFS = "lightning-outside-copy";
    private static final String KEY = "tree";
    private static final int FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    static volatile Activity activity;

    private BackupFolderBridge() {}

    /** Show the system's folder picker; the answer comes to MainActivity.onActivityResult, then chosen(). */
    public static void choose() {
        Activity current = activity;
        if (current == null) return;
        current.runOnUiThread(() -> {
            Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
                    .addFlags(FLAGS | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            try {
                current.startActivityForResult(pick, REQUEST_FOLDER);
            } catch (android.content.ActivityNotFoundException none) {
                // No folder picker on this phone: nothing is chosen, and Settings keeps saying so.
            }
        });
    }

    /** The picker's answer: keep the permission to the new folder and give back the old one's. */
    static void chosen(Activity current, Uri tree) {
        if (tree == null) return;
        ContentResolver resolver = current.getContentResolver();
        try {
            resolver.takePersistableUriPermission(tree, FLAGS);
        } catch (SecurityException refused) {
            return;
        }
        Uri old = saved(current);
        if (old != null && !old.equals(tree)) release(resolver, old);
        current.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, tree.toString()).apply();
    }

    /** Stop: give the permission back and forget the folder. The files in it stay. */
    public static void forget() {
        Activity current = activity;
        if (current == null) return;
        Uri old = saved(current);
        if (old != null) release(current.getContentResolver(), old);
        current.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY).apply();
    }

    /** {"state": "none" | "ok" | "lost", "name": the folder's name}. Lost: deleted, or its permission was revoked. */
    public static String state() {
        JSONObject answer = new JSONObject();
        try {
            Activity current = activity;
            Uri tree = current == null ? null : saved(current);
            if (tree == null) return answer.put("state", "none").put("name", "").toString();
            String name = held(current.getContentResolver(), tree) ? folderName(current.getContentResolver(), tree) : null;
            return answer.put("state", name == null ? "lost" : "ok").put("name", name == null ? "" : name).toString();
        } catch (org.json.JSONException e) {
            return "{\"state\":\"none\",\"name\":\"\"}";
        }
    }

    /** Copy a file from the app's own `outside-copy/` folder into the chosen folder; the name it got there, or "". */
    public static String write(String path, String name) {
        Activity current = activity;
        if (current == null) return "";
        Uri tree = saved(current);
        File file = new File(path);
        File folder = new File(current.getFilesDir(), "outside-copy");
        try {
            if (tree == null || !folder.getCanonicalPath().equals(file.getCanonicalFile().getParent()) || !file.isFile()) return "";
        } catch (IOException e) {
            return "";
        }
        ContentResolver resolver = current.getContentResolver();
        Uri created = null;
        try {
            created = DocumentsContract.createDocument(resolver, root(tree), "application/octet-stream", name);
            if (created == null) return "";
            try (InputStream in = new FileInputStream(file); OutputStream out = resolver.openOutputStream(created, "w")) {
                if (out == null) throw new IOException("no stream");
                byte[] buffer = new byte[64 * 1024];
                for (int read; (read = in.read(buffer)) > 0; ) out.write(buffer, 0, read);
            }
            String given = text(resolver, created, DocumentsContract.Document.COLUMN_DISPLAY_NAME);
            return given == null ? name : given;
        } catch (IOException | RuntimeException failed) {
            if (created != null) {
                try {
                    DocumentsContract.deleteDocument(resolver, created);  // never leave half a copy behind
                } catch (IOException | RuntimeException ignored) {
                    // the folder is gone: nothing to tidy
                }
            }
            return "";
        }
    }

    /** The names of the files in the chosen folder, as a JSON array. */
    public static String names() {
        JSONArray names = new JSONArray();
        Activity current = activity;
        Uri tree = current == null ? null : saved(current);
        if (tree == null) return names.toString();
        try (Cursor rows = children(current.getContentResolver(), tree)) {
            while (rows != null && rows.moveToNext()) names.put(rows.getString(1));
        } catch (RuntimeException gone) {
            // an unreadable folder lists nothing
        }
        return names.toString();
    }

    /** Delete one file in the chosen folder by its name. */
    public static boolean delete(String name) {
        Activity current = activity;
        Uri tree = current == null ? null : saved(current);
        if (tree == null || name == null) return false;
        ContentResolver resolver = current.getContentResolver();
        try (Cursor rows = children(resolver, tree)) {
            while (rows != null && rows.moveToNext()) {
                if (name.equals(rows.getString(1))) {
                    return DocumentsContract.deleteDocument(resolver,
                            DocumentsContract.buildDocumentUriUsingTree(tree, rows.getString(0)));
                }
            }
        } catch (IOException | RuntimeException failed) {
            return false;
        }
        return false;
    }

    private static Uri saved(Context context) {
        String value = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null);
        return value == null ? null : Uri.parse(value);
    }

    private static void release(ContentResolver resolver, Uri tree) {
        try {
            resolver.releasePersistableUriPermission(tree, FLAGS);
        } catch (SecurityException notHeld) {
            // already gone
        }
    }

    private static boolean held(ContentResolver resolver, Uri tree) {
        for (UriPermission permission : resolver.getPersistedUriPermissions()) {
            if (permission.getUri().equals(tree) && permission.isWritePermission()) return true;
        }
        return false;
    }

    private static Uri root(Uri tree) {
        return DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
    }

    private static String folderName(ContentResolver resolver, Uri tree) {
        try {
            return text(resolver, root(tree), DocumentsContract.Document.COLUMN_DISPLAY_NAME);
        } catch (RuntimeException gone) {
            return null;
        }
    }

    private static String text(ContentResolver resolver, Uri document, String column) {
        try (Cursor row = resolver.query(document, new String[] {column}, null, null, null)) {
            return row != null && row.moveToFirst() ? row.getString(0) : null;
        }
    }

    private static Cursor children(ContentResolver resolver, Uri tree) {
        Uri list = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
        return resolver.query(list, new String[] {DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null);
    }
}
