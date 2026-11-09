"""The Android shell (BT-2F): outside links and Back are wired, without a device.

The Java cannot run here, so these tests read it: each handler the WebView needs is present and keeps the locks
of task 04c (only this phone's server is loaded, no file or content access).
"""
from pathlib import Path

JAVA = Path(__file__).resolve().parents[1] / 'android/app/src/main/java/org/lightning/app'
MAIN = (JAVA / 'MainActivity.java').read_text()


def test_outside_links_open_in_the_browser_over_https_only():
    assert 'Intent.ACTION_VIEW' in MAIN and '"https".equals(uri.getScheme())' in MAIN
    assert 'getUserInfo() == null' in MAIN


def test_back_goes_to_overview_before_leaving():
    back = MAIN[MAIN.index('private void goBack'):]
    assert back.index('canGoBack') < back.index('"/".equals') < back.index('moveTaskToBack')


def test_back_uses_the_predictive_back_callback_from_api_33():
    """NF-11B1: target 36 means onBackPressed is never called on API 33+; the callback carries the same steps."""
    manifest = (JAVA.parents[3] / 'AndroidManifest.xml').read_text()
    assert 'android:enableOnBackInvokedCallback="true"' in manifest
    assert 'registerOnBackInvokedCallback' in MAIN and 'this::goBack' in MAIN
    pressed = MAIN[MAIN.index('public void onBackPressed'):]
    assert pressed.index('goBack();') < pressed.index('}')


def test_probe_screen_is_debug_only():
    main = JAVA.parents[3]
    assert 'ProbeActivity' not in (main / 'AndroidManifest.xml').read_text().split('-->')[-1]
    assert not (JAVA / 'ProbeActivity.java').exists()
    assert (main.parent / 'debug/java/org/lightning/app/ProbeActivity.java').exists()
    assert '.ProbeActivity' in (main.parent / 'debug/AndroidManifest.xml').read_text()
