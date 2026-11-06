package org.lightning.app;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * A copy of the profile outside the app (BT-2AI3; lightning.runtime.outside_copy, adapted in lightning_android.py).
 * The person chooses a folder once with the system's own folder screen (no storage permission); the app keeps the
 * right to use it, so an uninstall leaves the copies behind and "Open a profile file" turns one back into the book.
 * Only strings cross to Python: a file path, a name and a prefix.
 */
public final class OutsideCopyBridge {
    static final int REQUEST_TREE = 5;
    static final int KEEP = 3;
    private static final String PREFS = "outside_copy";
    private static final String TREE = "tree";
    static volatile Activity activity;

    private OutsideCopyBridge() {}

    private static Context context() {
        Activity current = activity;
        return current == null ? null : current.getApplicationContext();
    }

    private static Uri tree(Context context) {
        String saved = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(TREE, null);
        return saved == null ? null : Uri.parse(saved);
    }

    /** A folder is chosen and the app may still use it (the person can withdraw it in system settings). */
    public static boolean chosen() {
        Context context = context();
        if (context == null) return false;
        Uri tree = tree(context);
        if (tree == null) return false;
        for (android.content.UriPermission grant : context.getContentResolver().getPersistedUriPermissions()) {
            if (grant.getUri().equals(tree) && grant.isWritePermission()) return true;
        }
        return false;
    }

    /** Show the folder screen; false when there is no screen to show it on. */
    public static boolean choose() {
        Activity current = activity;
        if (current == null) return false;
        current.runOnUiThread(() -> {
            Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                    | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
            try {
                current.startActivityForResult(pick, REQUEST_TREE);
            } catch (android.content.ActivityNotFoundException none) {
                // no folder screen on this phone: the page keeps saying there is no copy
            }
        });
        return true;
    }

    /** The folder answer: keep the right to it, and remember it. */
    static void finish(Activity current, Uri chosen) {
        if (chosen == null) return;
        try {
            current.getContentResolver().takePersistableUriPermission(chosen,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        } catch (SecurityException e) {
            return;
        }
        SharedPreferences.Editor edit = current.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit();
        edit.putString(TREE, chosen.toString()).apply();
    }

    /** Copy the file at `path` into the folder as `name` (replacing one of the same name), then keep only the
     *  newest KEEP files that start with `prefix`. False when anything fails: the caller tries again later. */
    public static boolean write(String prefix, String name, String path) {
        Context context = context();
        if (context == null || !chosen()) return false;
        Uri tree = tree(context);
        ContentResolver resolver = context.getContentResolver();
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree));
        try (InputStream in = new FileInputStream(new File(path))) {
            for (String[] child : children(resolver, tree, parent)) {
                if (child[1].equals(name)) DocumentsContract.deleteDocument(resolver, uri(tree, child[0]));
            }
            Uri target = DocumentsContract.createDocument(resolver, parent, "application/octet-stream", name);
            if (target == null) return false;
            try (OutputStream out = resolver.openOutputStream(target, "w")) {
                if (out == null) return false;
                byte[] buffer = new byte[64 * 1024];
                for (int read; (read = in.read(buffer)) > 0; ) out.write(buffer, 0, read);
            }
            List<String[]> mine = new ArrayList<>();
            for (String[] child : children(resolver, tree, parent)) {
                if (child[1].startsWith(prefix) && child[1].endsWith(".lightning")) mine.add(child);
            }
            Collections.sort(mine, (a, b) -> b[1].compareTo(a[1]));  // names carry the date: newest first
            for (int i = KEEP; i < mine.size(); i++) DocumentsContract.deleteDocument(resolver, uri(tree, mine.get(i)[0]));
            return true;
        } catch (IOException | SecurityException | IllegalArgumentException e) {
            return false;
        }
    }

    private static Uri uri(Uri tree, String documentId) {
        return DocumentsContract.buildDocumentUriUsingTree(tree, documentId);
    }

    private static List<String[]> children(ContentResolver resolver, Uri tree, Uri parent) {
        List<String[]> found = new ArrayList<>();
        Uri list = DocumentsContract.buildChildDocumentsUriUsingTree(tree, DocumentsContract.getDocumentId(parent));
        try (Cursor cursor = resolver.query(list, new String[] {DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null)) {
            while (cursor != null && cursor.moveToNext()) found.add(new String[] {cursor.getString(0), cursor.getString(1)});
        }
        return found;
    }
}
