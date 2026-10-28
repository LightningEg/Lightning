package org.lightning.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.content.res.ColorStateList;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import com.chaquo.python.Python;
import java.io.ByteArrayInputStream;
import java.util.concurrent.atomic.AtomicBoolean;

/** Lightning on the phone: the shared pages in a WebView locked to this phone's own server (task 04c rules). */
public final class MainActivity extends Activity {
    static volatile Uri reminderOrigin;
    static volatile String reminderCookie;
    static volatile boolean reminderEnabled;
    private static final AtomicBoolean journalSyncRunning = new AtomicBoolean();
    private WebView web;
    private Uri origin;
    private volatile boolean serverReady;
    private boolean openSms;  // a message was shared in before the pages were ready
    private String pendingReminderHref;
    private final Handler reminderHandler = new Handler(Looper.getMainLooper());
    private final Handler journalSyncHandler = new Handler(Looper.getMainLooper());
    private final Runnable foregroundJournalSync = new Runnable() {
        @Override public void run() {
            if (serverReady) requestJournalSync();
            journalSyncHandler.postDelayed(this, 15 * 60 * 1000L);
        }
    };
    private final Runnable reminderPoll = new Runnable() {
        @Override public void run() {
            checkReminders();
            reminderHandler.postDelayed(this, 60_000);
        }
    };

    static void fitSystemBars(View view) {
        if (Build.VERSION.SDK_INT >= 30) {
            view.setOnApplyWindowInsetsListener((v, insets) -> {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime()
                        | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return WindowInsets.CONSUMED;
            });
        } else {
            view.setFitsSystemWindows(true);
        }
    }

    private boolean ours(Uri uri) {
        return origin != null && "http".equals(uri.getScheme()) && origin.getHost().equals(uri.getHost())
                && origin.getPort() == uri.getPort();
    }

    /** The one outside page the app opens, in the phone's browser: the website's marketplace, any query or fragment. */
    private boolean storeLink(Uri uri) {
        String path = uri.getPath();
        return "https".equals(uri.getScheme()) && "lightningeg.com".equals(uri.getHost())
                && uri.getUserInfo() == null && uri.getPort() == -1
                && ("/marketplace.html".equals(path) || "/ar/marketplace.html".equals(path));
    }

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
                && getIntent().getBooleanExtra("pairing_probe", false)) {
            startActivity(new Intent(this, ProbeActivity.class).putExtra("pairing_probe", true));
            finish();
            return;
        }
        JournalSyncScheduler.schedule(this);
        SmsBridge.activity = this;
        BiometricBridge.activity = this;
        takeShare(getIntent());
        queueReminder(getIntent());
        addShortcuts();
        WebView.setWebContentsDebuggingEnabled(false);
        FrameLayout frame = new FrameLayout(this);
        fitSystemBars(frame);
        frame.setBackgroundColor(0xFFF5F8F7);  // the app's own background, so the start looks like the app
        // The start screen: the lockup (guideline A02, one drawing) over a slim bar that moves while Python starts.
        float dp = getResources().getDisplayMetrics().density;
        LinearLayout splash = new LinearLayout(this);
        splash.setOrientation(LinearLayout.VERTICAL);
        splash.setGravity(android.view.Gravity.CENTER);
        ImageView lockup = new ImageView(this);
        lockup.setImageResource(R.drawable.lightning_lockup);
        lockup.setContentDescription("Lightning");
        splash.addView(lockup, new LinearLayout.LayoutParams((int) (226 * dp), (int) (56 * dp)));
        ProgressBar loading = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        loading.setIndeterminate(true);
        loading.setIndeterminateTintList(ColorStateList.valueOf(0xFF0A2442));  // Nile
        loading.setProgressBackgroundTintList(ColorStateList.valueOf(0xFFE6EFEC));  // Track
        LinearLayout.LayoutParams bar = new LinearLayout.LayoutParams((int) (120 * dp), (int) (4 * dp));
        bar.topMargin = (int) (28 * dp);
        splash.addView(loading, bar);
        frame.addView(splash, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        TextView starting = new TextView(this);  // only if Python cannot start: what went wrong, selectable
        starting.setPadding(48, 48, 48, 48);
        starting.setTextColor(0xFF0D2233);
        starting.setVisibility(View.GONE);
        frame.addView(starting, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(frame);
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        String files = getFilesDir().getAbsolutePath();
        new Thread(() -> {
            try {
                String url = Python.getInstance().getModule("lightning_android").callAttr("start", files).toString();
                runOnUiThread(() -> show(frame, url));
            } catch (Throwable error) {
                String text = "Lightning could not start. Close it and open it again.\n\n" + Log.getStackTraceString(error);
                runOnUiThread(() -> {
                    splash.setVisibility(View.GONE);
                    starting.setVisibility(View.VISIBLE);
                    starting.setTextSize(13);
                    starting.setGravity(android.view.Gravity.START);
                    starting.setText(text);
                    starting.setTextIsSelectable(true);
                });
            }
        }, "lightning-start").start();
    }

    private void show(FrameLayout frame, String url) {
        serverReady = true;
        Uri launch = Uri.parse(url);
        origin = launch.buildUpon().encodedPath("/").clearQuery().fragment(null).build();
        reminderOrigin = origin;
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setGeolocationEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                if (storeLink(target)) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, target));
                    } catch (android.content.ActivityNotFoundException ignored) {
                        // no browser installed: the app stays where it is
                    }
                    return true;
                }
                return !ours(target);  // another site, a file or an app link: never opened
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (ours(request.getUrl())) return null;
                return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", null,
                        new ByteArrayInputStream(new byte[0]));
            }

            @Override
            public void onPageFinished(WebView view, String finishedUrl) {
                if (ours(Uri.parse(finishedUrl))) checkReminders();
            }
        });
        frame.removeAllViews();
        frame.addView(web);
        web.loadUrl(url);
        requestJournalSync();
        if (pendingReminderHref != null) {
            String href = pendingReminderHref;
            pendingReminderHref = null;
            web.postDelayed(() -> openReminder(href), 1000);
        }
        if (openSms) {
            openSms = false;
            web.postDelayed(() -> web.loadUrl(origin.buildUpon().path("/sms").build().toString()), 1500);
        }
    }

    /** "Share" from the SMS app: the text waits for the Python side, and From SMS opens to read it. */
    private void takeShare(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return;
        CharSequence text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
        if (text == null) return;
        SmsBridge.share(text.toString());
        if (web != null && origin != null) web.loadUrl(origin.buildUpon().path("/sms").build().toString());
        else openSms = true;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        takeShare(intent);
        String href = intent.getStringExtra("reminder_href");
        if (href != null) openReminder(href);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == SmsBridge.REQUEST_SMS && web != null && origin != null) {
            web.loadUrl(origin.buildUpon().path("/sms").build().toString());  // read right away, or say why not
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else moveTaskToBack(true);  // keep the server and an open lend reachable
    }

    @Override
    protected void onStart() {
        super.onStart();
        stopService(new Intent(this, SyncService.class));
        if (serverReady) requestJournalSync();
        journalSyncHandler.removeCallbacks(foregroundJournalSync);
        journalSyncHandler.postDelayed(foregroundJournalSync, 15 * 60 * 1000L);
        reminderHandler.removeCallbacks(reminderPoll);
        reminderHandler.postDelayed(reminderPoll, 5_000);
    }

    /** Let an already-unlocked phone catch up when it returns to the foreground. */
    private void requestJournalSync() {
        if (!journalSyncRunning.compareAndSet(false, true)) return;
        String files = getFilesDir().getAbsolutePath();
        new Thread(() -> {
            try {
                String result = Python.getInstance().getModule("lightning_android")
                        .callAttr("sync_journal", files).toString();
                Log.i("LightningJournalSync", "Foreground catch-up: " + result);
            } catch (Throwable error) {
                Log.w("LightningJournalSync", "Foreground catch-up deferred", error);
            } finally {
                journalSyncRunning.set(false);
            }
        }, "lightning-journal-foreground").start();
    }

    @Override
    protected void onStop() {
        reminderHandler.removeCallbacks(reminderPoll);
        journalSyncHandler.removeCallbacks(foregroundJournalSync);
        super.onStop();
        new Thread(() -> {
            try {
                String note = Python.getInstance().getModule("lightning_android").callAttr("background_note").toString();
                String cookie = reminderCookie;
                if (!note.isEmpty() || (reminderEnabled && cookie != null && !cookie.isEmpty())) {
                    Intent intent = new Intent(this, SyncService.class)
                            .putExtra("note", note.isEmpty() ? "Checking enabled reminders" : note);
                    if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent);
                    else startService(intent);
                }
            } catch (Throwable ignored) {
                // Without the service the PC hands back the next time Lightning is open here.
            }
        }, "lightning-background").start();
    }

    private void checkReminders() {
        if (web == null || origin == null || !ours(Uri.parse(web.getUrl() == null ? "" : web.getUrl()))) return;
        String cookie = CookieManager.getInstance().getCookie(origin.toString());
        reminderCookie = cookie;
        if (cookie == null || cookie.isEmpty()) return;
        Uri currentOrigin = origin;
        new Thread(() -> {
            ReminderNotifications.PollResult result = ReminderNotifications.check(this, currentOrigin, cookie);
            reminderEnabled = result.enabled;
        }, "lightning-reminders").start();
    }

    /** Long-press the app icon (phone roadmap M8): Add expense and Bank SMS open straight away, through the same
     *  safe in-app link path as a reminder (reminder_href, checked by safeHrefForActivity). */
    private void addShortcuts() {
        if (Build.VERSION.SDK_INT < 25) return;
        try {
            android.content.pm.ShortcutManager manager = getSystemService(android.content.pm.ShortcutManager.class);
            if (manager == null) return;
            java.util.List<android.content.pm.ShortcutInfo> list = new java.util.ArrayList<>();
            String[][] items = {{"add", "Add expense", "/accounts/add-transaction"}, {"sms", "Bank SMS", "/sms"}};
            for (String[] item : items) {
                Intent open = new Intent(this, MainActivity.class).setAction("org.lightning.app.OPEN_REMINDER")
                        .putExtra("reminder_href", item[2]).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
                list.add(new android.content.pm.ShortcutInfo.Builder(this, item[0]).setShortLabel(item[1])
                        .setIcon(android.graphics.drawable.Icon.createWithResource(this, R.drawable.ic_lightning))
                        .setIntent(open).build());
            }
            manager.setDynamicShortcuts(list);
        } catch (RuntimeException ignored) {
            // a launcher without shortcuts: nothing to add
        }
    }

    private void queueReminder(Intent intent) {
        if (intent == null) return;
        String href = intent.getStringExtra("reminder_href");
        if (href != null) pendingReminderHref = href;
    }

    private void openReminder(String href) {
        Uri target = ReminderNotifications.safeHrefForActivity(href);
        if (target == null) return;
        if (web == null || origin == null) {
            pendingReminderHref = href;
            return;
        }
        Uri full = origin.buildUpon().encodedPath(target.getEncodedPath())
                .encodedQuery(target.getEncodedQuery()).fragment(null).build();
        if (ours(full)) web.loadUrl(full.toString());
    }
}
