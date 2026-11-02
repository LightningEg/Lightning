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
    back = MAIN[MAIN.index('public void onBackPressed'):]
    assert back.index('canGoBack') < back.index('"/".equals') < back.index('moveTaskToBack')
