"""Minimal, fail-closed Windows WebView2 window adapter."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import threading
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from lightning import DISPLAY_VERSION

_PYWEBVIEW_VERSION = "6.2.1"
_SMOKE_TIMEOUT = 20.0
_STARTUP_TIMEOUT = 30.0
_REMINDER_SCRIPT = (
    "window.__lightningReminderResult=null;"
    "fetch('/reminders/due.json',{credentials:'same-origin',cache:'no-store'})"
    ".then(r=>{if(!r.ok)throw Error();return r.json()})"
    ".then(v=>window.__lightningReminderResult=JSON.stringify(v))"
    ".catch(()=>window.__lightningReminderResult='')"
)


def _safe_reminder_href(value: object, origin: str, allowed_origin: tuple[str, str, int]) -> str | None:
    href = str(value or "")
    if not href.startswith("/") or href.startswith("//") or "\\" in href:
        return None
    target = urljoin(origin.rstrip("/") + "/", href)
    return target if _allowed_navigation(target, allowed_origin) else None


def _reminder_prefs_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return root / "Lightning" / "native-reminders.json"


def _read_reminder_prefs(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        seen = data.get("seen", {}) if isinstance(data, dict) else {}
        return {str(key): str(value) for key, value in seen.items()
                if isinstance(key, str) and isinstance(value, str)} if isinstance(seen, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_reminder_prefs(path: Path, seen: dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"seen": seen}, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def _native_reminder_loop(window, origin: str, allowed_origin: tuple[str, str, int], ready,
                          closed: threading.Event, native_state: dict) -> None:
    """Poll through the active WebView session and send in-process Windows notification balloons."""
    try:
        path = _reminder_prefs_path()
        seen = _read_reminder_prefs(path)
        while not closed.is_set():
            if ready.wait(1):
                try:
                    window.run_js(_REMINDER_SCRIPT)
                    deadline = __import__("time").monotonic() + 5
                    payload = ""
                    while __import__("time").monotonic() < deadline and not closed.is_set():
                        value = window.evaluate_js("window.__lightningReminderResult||''")
                        if value:
                            payload = str(value)
                            break
                        closed.wait(0.15)
                    data = json.loads(payload) if payload else {}
                    if data.get("enabled") is True and isinstance(data.get("items"), list):
                        today = date.today().isoformat()
                        seen = {key: value for key, value in seen.items() if value == today}
                        for item in data["items"]:
                            if not isinstance(item, dict):
                                continue
                            item_id = str(item.get("id", ""))
                            href = _safe_reminder_href(item.get("href"), origin, allowed_origin)
                            label = " ".join(str(item.get("label", "")).split())[:63]
                            detail = " ".join(str(item.get("detail", "")).split())[:63]
                            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", item_id) or not label or not href or seen.get(item_id) == today:
                                continue
                            icon, native = native_state.get("icon"), window.native
                            if icon is None or native is None:
                                break
                            from System import Action

                            native_state["href"] = href
                            text = (label if not detail else f"{label} · {detail}")[:63]
                            native.BeginInvoke(Action(lambda icon=icon, text=text: _show_balloon(icon, text, closed)))
                            seen[item_id] = today
                            _write_reminder_prefs(path, seen)
                            break  # keep one balloon active so its click target cannot be confused with another
                except Exception:
                    # Native reminders are optional. Session or notification failures never affect the financial UI.
                    pass
            closed.wait(60)
    except Exception:
        # pywebview's in-process Windows Forms API can be unavailable on a host; in-app reminders remain available.
        pass


def _show_balloon(icon, text: str, closed: threading.Event) -> None:
    if closed.is_set():
        return
    try:
        from System.Windows.Forms import ToolTipIcon

        icon.Visible = True
        icon.BalloonTipTitle = "Lightning"
        icon.BalloonTipText = text
        icon.BalloonTipIcon = ToolTipIcon.Info
        icon.ShowBalloonTip(5000)
    except Exception:
        pass


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("origin must be an HTTP(S) origin")
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("origin must not contain credentials, path, query, or fragment")
    host = parsed.hostname.lower()
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("desktop origin must use loopback")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid origin port") from exc
    scheme = parsed.scheme.lower()
    return scheme, host, port if port is not None else (443 if scheme == "https" else 80)


def _store_link(uri: str) -> bool:
    """The one outside page the app may open, in the system browser: the website's marketplace (any query or fragment)."""
    try:
        parsed = urlsplit(str(uri))
        return (
            parsed.scheme == "https"
            and parsed.hostname == "lightningeg.com"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and parsed.path in ("/marketplace.html", "/ar/marketplace.html")
            and "\\" not in str(uri)
        )
    except ValueError:
        return False


def _open_in_browser(uri: str) -> None:
    """Hand a store link to the person's default browser on a thread; the app window never navigates."""
    def run() -> None:
        try:
            if os.name == "nt":
                os.startfile(uri)  # the shell's default browser
            else:
                import webbrowser
                webbrowser.open(uri)
        except Exception:  # no browser to open: the page simply stays as it is
            pass
    threading.Thread(target=run, daemon=True).start()


def _allowed_navigation(uri: str, allowed_origin: tuple[str, str, int]) -> bool:
    if uri == "about:blank":
        return True
    try:
        parsed = urlsplit(uri)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        scheme = parsed.scheme.lower()
        port = parsed.port
        candidate = (scheme, parsed.hostname.lower(), port if port is not None else (443 if scheme == "https" else 80))
        return candidate == allowed_origin
    except ValueError:
        return False


# Windows 11 paints the title bar black when the system is dark; these let the window take the page's own colours.
_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_CAPTION_COLOR, _DWMWA_TEXT_COLOR = 20, 35, 36
_TITLE_BAR_SCRIPT = (
    "(()=>{const s=getComputedStyle(document.documentElement);"
    "return [s.getPropertyValue('--canvas-start').trim()||getComputedStyle(document.body).backgroundColor,"
    "s.getPropertyValue('--ink').trim()].join('|')})()"
)


def _colorref(css: str) -> int | None:
    """``#RRGGBB`` or ``rgb(r, g, b)`` as a Windows COLORREF (0x00BBGGRR); None for anything else."""
    css = (css or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", css):
        r, g, b = (int(css[i:i + 2], 16) for i in (1, 3, 5))
    elif found := re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,[^)]*)?\)", css):
        r, g, b = (min(int(v), 255) for v in found.groups())
    else:
        return None
    return r | g << 8 | b << 16


def _is_dark(colorref: int) -> bool:
    r, g, b = colorref & 255, colorref >> 8 & 255, colorref >> 16 & 255
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128


def _paint_title_bar(window) -> None:
    """The title bar in the page's canvas and Ink (any theme, its night version too), not the system's black.
    Windows 11 only; elsewhere, or on any failure, the system's own bar stays."""
    import ctypes

    caption, _, text = str(window.evaluate_js(_TITLE_BAR_SCRIPT) or "").partition("|")
    caption_ref, text_ref = _colorref(caption), _colorref(text)
    if caption_ref is None:
        return
    hwnd = ctypes.c_void_p(int(window.native.Handle.ToInt64()))
    dwm = ctypes.windll.dwmapi

    def put(attribute: int, value: int) -> None:
        data = ctypes.c_int(value)
        dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))

    put(_DWMWA_USE_IMMERSIVE_DARK_MODE, int(_is_dark(caption_ref)))  # caption buttons readable on the bar
    put(_DWMWA_CAPTION_COLOR, caption_ref)
    if text_ref is not None:
        put(_DWMWA_TEXT_COLOR, text_ref)


def _show_error(message: str) -> None:
    """Show a native Windows error without importing GUI bindings on other platforms."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, message, "Lightning", 0x10)


def run_window(url: str, origin: str, *, smoke: bool = False, diagnostics: dict | None = None,
               profile_mode: bool = False) -> int:
    """Run one guarded WebView2 window; return nonzero for startup or smoke failures."""
    if __import__("sys").platform != "win32":
        raise RuntimeError("The Lightning desktop window is available only on Windows")

    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics["stage"] = "initializing"
    try:
        allowed_origin = _origin(origin)
        target = urlsplit(url)
        if not _allowed_navigation(url, allowed_origin) or target.scheme not in ("http", "https"):
            raise ValueError("URL must belong to the configured loopback origin")
        if importlib.metadata.version("pywebview") != _PYWEBVIEW_VERSION:
            raise RuntimeError("Lightning requires pywebview 6.2.1")

        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
        webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
        webview.settings["IGNORE_SSL_ERRORS"] = False
        webview.settings["REMOTE_DEBUGGING_PORT"] = None

        state: dict[str, object] = {"guard": False, "failure": None, "rejected": threading.Event()}
        reminder_native: dict[str, object] = {"icon": None, "href": None}
        app_ready = threading.Event()
        smoke_done = threading.Event()
        window_closed = threading.Event()
        result = {"code": 1 if smoke else 0}

        def fail(reason: str) -> None:
            diagnostics["failure"] = reason
            state["failure"] = reason
            result["code"] = 1
            smoke_done.set()
            native = window.native
            if native is not None:
                try:
                    from System import Action

                    native.BeginInvoke(Action(lambda: native.Close()))
                except Exception:
                    try:
                        if not native.InvokeRequired:
                            native.Close()
                    except Exception:
                        pass

        def install_reminder_icon() -> None:
            try:
                from System.Drawing import SystemIcons
                from System.Windows.Forms import NotifyIcon

                icon = NotifyIcon()
                icon.Icon = SystemIcons.Information
                icon.Text = "Lightning reminders"
                reminder_native["icon"] = icon

                def open_link(*_args) -> None:
                    href = reminder_native.get("href")
                    if isinstance(href, str) and _allowed_navigation(href, allowed_origin) and not window_closed.is_set():
                        try:
                            window.load_url(href)
                        except Exception:
                            pass

                icon.BalloonTipClicked += open_link
            except Exception:
                # Windows notifications can be unavailable while the in-app reminder list still works.
                reminder_native["icon"] = None

        def close_window(*_args) -> None:
            window_closed.set()
            smoke_done.set()
            icon = reminder_native.get("icon")
            if icon is not None:
                try:
                    icon.Visible = False
                    icon.Dispose()
                except Exception:
                    pass

        def before_show(*_args) -> None:
            diagnostics["stage"] = "native-window"
            if profile_mode and not smoke:
                install_reminder_icon()
            try:
                if webview.renderer != "edgechromium":
                    raise RuntimeError("WebView2 renderer was not selected")
                native = window.native
                browser = getattr(native, "browser", None)
                control = getattr(browser, "webview", None)
                init_event = getattr(control, "CoreWebView2InitializationCompleted", None)
                if control is None or init_event is None:
                    raise RuntimeError("WebView2 initialization hook unavailable")

                def initialized(sender, args) -> None:
                    try:
                        if not args.IsSuccess:
                            raise RuntimeError("WebView2 initialization failed")
                        core = sender.CoreWebView2
                        if core is None:
                            raise RuntimeError("WebView2 core is unavailable")

                        def navigation_starting(_sender, event) -> None:
                            uri = str(event.Uri)
                            if _store_link(uri):
                                event.Cancel = True
                                _open_in_browser(uri)
                            elif not _allowed_navigation(uri, allowed_origin):
                                event.Cancel = True
                                state["rejected"].set()

                        def new_window(_sender, event) -> None:
                            event.set_Handled(True)
                            uri = str(getattr(event, "Uri", ""))
                            if _store_link(uri):
                                _open_in_browser(uri)
                            else:
                                state["rejected"].set()

                        core.NavigationStarting += navigation_starting
                        core.NewWindowRequested += new_window
                        state["guard"] = True
                        diagnostics["stage"] = "navigation-guard-installed"

                        def navigate() -> None:
                            if not window.events.shown.wait(10):
                                fail("WebView2 window did not become visible")
                                return
                            try:
                                window.load_url(url)
                            except Exception:
                                fail("Could not open the local application")

                        threading.Thread(target=navigate, daemon=True).start()
                    except Exception:
                        fail("Could not install the WebView2 navigation guard")

                init_event += initialized
            except Exception:
                fail("Could not attach the WebView2 initialization guard")

        window = webview.create_window(
            f"Lightning v{DISPLAY_VERSION}", "about:blank", width=1200, height=800, js_api=None
        )

        def require_edgechromium(renderer: str) -> bool | None:
            if renderer != "edgechromium":
                state["failure"] = "WebView2 renderer was not selected"
                result["code"] = 1
                return False
            return None

        window.events.initialized += require_edgechromium
        window.events.before_show += before_show
        window.events.closed += close_window

        if profile_mode and not smoke:
            threading.Thread(target=_native_reminder_loop,
                             args=(window, origin, allowed_origin, app_ready, window_closed, reminder_native),
                             name="lightning-native-reminders", daemon=True).start()

        if smoke:
            def monitor_smoke() -> None:
                import time

                end = time.monotonic() + _SMOKE_TIMEOUT
                while time.monotonic() < end and not smoke_done.is_set():
                    if app_ready.is_set() and state["guard"]:
                        try:
                            selector = "#profile-ready" if profile_mode else "#probe-ready"
                            check_path = "/profiles/health" if profile_mode else "/api/check"
                            if window.evaluate_js(f"Boolean(document.querySelector('{selector}'))"):
                                window.run_js(
                                    "(async()=>{try{const r=await fetch('" + check_path + "');"
                                    "const j=await r.json();document.documentElement.dataset.lightningSmoke="
                                    "(r.ok&&new URL(r.url).origin===location.origin&&j.ok===true?"
                                    "'ok':'fail')}catch(e){"
                                    "document.documentElement.dataset.lightningSmoke='fail'}})()"
                                )
                                check_end = time.monotonic() + 5
                                while time.monotonic() < check_end:
                                    if window.evaluate_js(
                                        "document.documentElement.dataset.lightningSmoke||''"
                                    ) == "ok":
                                        window.run_js("location.href='https://example.com/'")
                                        if state["rejected"].wait(2):
                                            if not window_closed.is_set():
                                                result["code"] = 0
                                                diagnostics["stage"] = "smoke-passed"
                                        else:
                                            result["code"] = 1
                                        smoke_done.set()
                                        break
                                    if window.evaluate_js(
                                        "document.documentElement.dataset.lightningSmoke||''"
                                    ) == "fail":
                                        result["code"] = 1
                                        smoke_done.set()
                                        break
                                    threading.Event().wait(0.1)
                                break
                        except Exception:
                            result["code"] = 1
                            smoke_done.set()
                            break
                    threading.Event().wait(0.1)
                if not smoke_done.is_set():
                    result["code"] = 1
                    smoke_done.set()
                if result["code"]:
                    fail("WebView2 smoke check failed")
                else:
                    try:
                        window.destroy()
                    except Exception:
                        result["code"] = 1

            def on_loaded(*_args) -> None:
                try:
                    current_url = str(window.get_current_url() or "")
                    if current_url != "about:blank" and state["guard"] and _allowed_navigation(
                        current_url, allowed_origin
                    ):
                        app_ready.set()
                except Exception:
                    pass

            window.events.loaded += on_loaded
            threading.Thread(target=monitor_smoke, daemon=True).start()
        else:
            def on_loaded(*_args) -> None:
                try:
                    current_url = str(window.get_current_url() or "")
                    if current_url != "about:blank" and state["guard"] and _allowed_navigation(
                        current_url, allowed_origin
                    ):
                        app_ready.set()
                        _paint_title_bar(window)  # each page: a theme change shows on the next one
                except Exception:
                    pass

            window.events.loaded += on_loaded

            def startup_watchdog() -> None:
                if not app_ready.wait(_STARTUP_TIMEOUT) and not window.events.closed.wait(0):
                    fail("The local application did not finish loading")

            threading.Thread(target=startup_watchdog, daemon=True).start()

        webview.start(gui="edgechromium", debug=False, private_mode=True)
        if state["failure"] and not smoke:
            _show_error(str(state["failure"]))
            return 1
        return int(result["code"])
    except Exception as exc:
        diagnostics["error_type"] = type(exc).__name__
        # Where it failed (file, function, line), never the text: framework errors can contain the launch URL.
        diagnostics["error_frames"] = [f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.name}:{frame.lineno}"
                                       for frame in __import__("traceback").extract_tb(exc.__traceback__)][-12:]
        if not smoke:
            try:
                _show_error("Lightning window failed to start. Check the local URL and WebView2 runtime.")
            except Exception:
                pass
        return 1
