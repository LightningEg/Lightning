package org.lightning.app;

import android.app.Activity;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.os.Build;
import android.view.View;
import android.view.WindowInsets;
import android.widget.FrameLayout;
import android.webkit.CookieManager;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.List;

/** Dummy data only. 04a/04b checks run at launch; the button runs 04c: Lightning's own pages in a locked-down WebView. */
public final class ProbeActivity extends Activity {
    private TextView result;
    private Button open;
    private LinearLayout main;
    private WebView web;
    private Uri origin;
    private String checks = "";
    private boolean isolationTested;
    private String fetchResult = "not run";
    private final List<String> visited = new ArrayList<>();
    private final List<String> blocked = new ArrayList<>();
    private final List<String> intercepted = new ArrayList<>();
    private final List<String> left = new ArrayList<>();

    private static PyObject probe() {
        return Python.getInstance().getModule("probe");
    }

    /** Android 15 draws apps edge to edge: keep content clear of the status bar, navigation bar and keyboard. */
    private static void fitSystemBars(View view) {
        if (Build.VERSION.SDK_INT >= 30) {
            view.setOnApplyWindowInsetsListener((v, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime()
                        | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return WindowInsets.CONSUMED;
            });
        } else {
            view.setFitsSystemWindows(true);
        }
    }

    private static String failure(String what, Throwable error) {
        return what + " failed:\n" + Log.getStackTraceString(error);  // the Python traceback or the Java causes
    }

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
                && getIntent().getBooleanExtra("pairing_probe", false)) {
            result = new TextView(this);
            result.setTextIsSelectable(true);
            result.setText("Checking dummy device credential protection…");
            setContentView(result);
            new Thread(() -> {
                String text;
                try {
                    text = probe().callAttr("pairing_credentials").toString();
                } catch (Throwable failed) {
                    text = "{\"passed\":false,\"error\":\"credential_probe_failed\"}";
                }
                final String shown = text;
                Log.i("LightningPairingProbe", shown);
                runOnUiThread(() -> result.setText(shown));
            }, "pairing-credential-probe").start();
            return;
        }
        WebView.setWebContentsDebuggingEnabled(false);  // no remote inspection of finance pages, even in this debug build
        result = new TextView(this);
        result.setPadding(32, 32, 32, 32);
        result.setTextIsSelectable(true);
        result.setText("Checking… the encrypted round-trip and pages take a few seconds.");
        open = new Button(this);
        open.setText("Open Lightning (04c)");
        open.setEnabled(false);
        open.setOnClickListener(view -> startServer());
        ScrollView scroll = new ScrollView(this);
        scroll.addView(result);
        main = new LinearLayout(this);
        main.setOrientation(LinearLayout.VERTICAL);
        fitSystemBars(main);
        main.addView(open);
        main.addView(scroll);
        setContentView(main);
        // Off the UI thread: key derivation takes seconds. Each check opens and closes its database on this one thread.
        new Thread(() -> {
            String text;
            try {
                text = probe().callAttr("run").toString();
            } catch (Throwable error) {
                text = failure("Dependency probe", error);
            }
            String shown = text + "\n\n04c: tap Open Lightning, choose the Dummy profile, type the password\n"
                    + "dummy round-trip password\nopen a few pages, then press Back.";
            runOnUiThread(() -> {
                checks = shown;
                result.setText(shown);
                open.setEnabled(true);
            });
        }, "probe").start();
    }

    private void startServer() {
        open.setEnabled(false);
        result.setText(checks + "\n\nStarting Lightning…");
        String files = getFilesDir().getAbsolutePath();  // app-private storage
        new Thread(() -> {
            try {
                String launch = probe().callAttr("serve", files).toString();
                runOnUiThread(() -> showWeb(launch));
            } catch (Throwable error) {
                String text = failure("04c server", error);
                runOnUiThread(() -> {
                    result.setText(checks + "\n\n" + text);
                    open.setEnabled(true);
                });
            }
        }, "probe-serve").start();
    }

    private boolean ours(Uri uri) {
        return "http".equals(uri.getScheme()) && origin.getHost().equals(uri.getHost()) && origin.getPort() == uri.getPort();
    }

    private void showWeb(String launch) {
        origin = Uri.parse(launch);
        visited.clear(); blocked.clear(); intercepted.clear(); left.clear();
        isolationTested = false;
        fetchResult = "not run";
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);  // app.js keeps small view choices, as in the Windows window
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setGeolocationEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (ours(request.getUrl())) return false;
                blocked.add(request.getUrl().toString());  // another site, a file, an app intent: never opened
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (ours(request.getUrl())) return null;
                intercepted.add(request.getUrl().toString());
                return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", null,
                        new ByteArrayInputStream(new byte[0]));
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Uri page = Uri.parse(url);
                if (!ours(page)) {
                    left.add(url);
                    return;
                }
                visited.add(page.getPath());
                if ("/".equals(page.getPath()) && !isolationTested) {
                    isolationTested = true;
                    testIsolation(view);
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                left.add("the page renderer stopped (crash: " + detail.didCrash() + ")");
                finishWeb();
                return true;
            }
        });
        FrameLayout frame = new FrameLayout(this);  // padded, so the page sits between the status and navigation bars
        frame.addView(web);
        fitSystemBars(frame);
        setContentView(frame);
        web.loadUrl(launch);
    }

    /** From the Overview, try to leave the app's origin three ways and to reach the internet; each must be refused. */
    private void testIsolation(WebView view) {
        view.evaluateJavascript("(function(){window.__probe='pending';"
                + "fetch('https://example.com/').then(function(){window.__probe='fetch reached example.com'})"
                + ".catch(function(){window.__probe='fetch refused'});"
                + "setTimeout(function(){location.href='https://example.com/'},300);"
                + "setTimeout(function(){location.href='file:///proc/version'},600);"
                + "setTimeout(function(){location.href='intent://scan/#Intent;scheme=zxing;end'},900);})()", null);
        view.postDelayed(() -> {
            if (web == view) view.evaluateJavascript("String(window.__probe)", value -> fetchResult = value);
        }, 2000);
    }

    private String webReport() {
        StringBuilder text = new StringBuilder();
        boolean overview = visited.contains("/");
        text.append(overview ? "OK  " : "FAIL ").append("04c WebView pages: ").append(visited.size())
                .append(" loaded, Overview ").append(overview ? "shown" : "never shown").append(": ").append(visited).append('\n');
        boolean https = false;
        for (String url : blocked) https |= url.startsWith("https:");
        // WebView itself may refuse the file and intent links before asking us; either way no page may leave the app.
        boolean refused = fetchResult.contains("fetch refused");
        boolean isolated = overview && https && refused && left.isEmpty();
        text.append(isolated ? "OK  " : "FAIL ").append("04c WebView isolation: navigations blocked ").append(blocked)
                .append("; requests stopped ").append(intercepted.size()).append("; fetch: ").append(fetchResult);
        if (!left.isEmpty()) text.append("; left the app: ").append(left);
        return text.toString();
    }

    private void finishWeb() {
        if (web == null) return;
        String report = webReport();
        web.stopLoading();
        web.destroy();
        web = null;
        setContentView(main);
        result.setText(checks + "\n\nStopping Lightning…");
        new Thread(() -> {
            String served;
            try {
                served = probe().callAttr("stop").toString();
            } catch (Throwable error) {
                served = failure("04c shutdown", error);
            }
            String shown = checks + "\n\n" + report + "\n" + served;
            runOnUiThread(() -> {
                result.setText(shown);
                open.setEnabled(true);
            });
        }, "probe-stop").start();
    }

    @Override
    public void onBackPressed() {
        if (web != null) finishWeb();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
            new Thread(() -> probe().callAttr("stop_quietly"), "probe-stop").start();
        }
        super.onDestroy();
    }
}
