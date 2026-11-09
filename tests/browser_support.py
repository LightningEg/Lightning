"""One place that finds Chromium for the browser tests and decides what a missing browser means.

On a developer machine without Playwright or Chromium the browser tests skip. In CI the job sets
LIGHTNING_REQUIRE_BROWSER=1, and then a missing browser fails the test instead, so the browser tests can
never be skipped silently again (they were, on every pull request, until IT-9Q). tests/conftest.py also
turns any skip that names Playwright or Chromium into a failure under that variable, for a test that
finds the browser some other way.
"""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

import pytest

REQUIRE_BROWSER = os.environ.get("LIGHTNING_REQUIRE_BROWSER") == "1"


def _runnable(path: str | None) -> str | None:
    if path and Path(path).is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


@lru_cache(maxsize=1)
def _playwright_bundled() -> str | None:
    """The Chromium that `python -m playwright install chromium` put in Playwright's own folder."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            return _runnable(p.chromium.executable_path)
    except Exception:
        return None


def chromium_executable() -> str | None:
    """The first runnable Chromium: LIGHTNING_CHROMIUM, then the PATH, then the usual folders, then Playwright's."""
    for candidate in (
        os.environ.get("LIGHTNING_CHROMIUM"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/usr/bin/chromium",
        "/opt/pw-browsers/chromium",
    ):
        found = _runnable(candidate)
        if found:
            return found
    return _playwright_bundled()


def browser_missing(reason: str):
    """Skip on a machine without a browser; fail where the browser is required."""
    if REQUIRE_BROWSER:
        pytest.fail(f"{reason}, and LIGHTNING_REQUIRE_BROWSER=1 requires it", pytrace=False)
    pytest.skip(reason)


def require_chromium() -> str:
    """Playwright importable and a Chromium to launch, or skip (fail in CI). Returns the executable path."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        browser_missing("Playwright is not installed")
    executable = chromium_executable()
    if not executable:
        browser_missing("Chromium is not installed")
    return executable
