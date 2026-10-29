package org.lightning.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.widget.Toast;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Downloads for the Python side (lightning.runtime.phone_files, adapted in lightning_android.py, 2F). The WebView
 * saves nothing a page sends as an attachment, so the server writes the file into the app's own `outgoing/`
 * folder and offers it here; the system's "Save to" screen (works on every Android version, no storage
 * permission) lets the person choose Downloads, Drive or anywhere else. The file is deleted either way.
 */
public final class FileBridge {
    static final int REQUEST_SAVE = 3;
    static volatile Activity activity;
    private static File waiting;

    private FileBridge() {}

    /** Show "Save to" for a file in `outgoing/`; false when there is no screen to show it on. */
    public static boolean offer(String path, String name, String mimeType) {
        Activity current = activity;
        if (current == null) return false;
        File file = new File(path);
        File folder = new File(current.getFilesDir(), "outgoing");
        try {
            if (!folder.getCanonicalPath().equals(file.getCanonicalFile().getParent()) || !file.isFile()) return false;
        } catch (IOException e) {
            return false;
        }
        current.runOnUiThread(() -> {
            synchronized (FileBridge.class) {
                if (waiting != null) waiting.delete();  // a newer download replaces one still waiting
                waiting = file;
            }
            Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(mimeType == null || mimeType.isEmpty() ? "application/octet-stream" : mimeType)
                    .putExtra(Intent.EXTRA_TITLE, name);
            try {
                current.startActivityForResult(save, REQUEST_SAVE);
            } catch (android.content.ActivityNotFoundException none) {
                finish(current, null, false);
            }
        });
        return true;
    }

    /** The "Save to" answer: copy the waiting file there, or just forget it; say which in the app's language. */
    static void finish(Activity current, Uri target, boolean arabic) {
        File file;
        synchronized (FileBridge.class) {
            file = waiting;
            waiting = null;
        }
        if (file == null) return;
        boolean saved = false;
        if (target != null) {
            try (InputStream in = new FileInputStream(file);
                 OutputStream out = current.getContentResolver().openOutputStream(target, "w")) {
                if (out != null) {
                    byte[] buffer = new byte[64 * 1024];
                    for (int read; (read = in.read(buffer)) > 0; ) out.write(buffer, 0, read);
                    saved = true;
                }
            } catch (IOException | SecurityException e) {
                saved = false;
            }
        }
        file.delete();
        String said = saved ? (arabic ? "اتحفظ." : "Saved.")
                : target == null ? (arabic ? "متحفظش." : "Not saved.")
                : (arabic ? "الملف متحفظش. جرّب مكان تاني." : "Could not save the file. Try another place.");
        Toast.makeText(current, said, Toast.LENGTH_SHORT).show();
    }
}
