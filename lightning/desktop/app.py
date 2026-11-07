"""Windows finance window using the shared password/profile runtime."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import tempfile
import traceback
from contextlib import ExitStack
from pathlib import Path


def run(argv=None) -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Lightning encrypted profiles")
    parser.add_argument("--profile-root", type=Path, help="alternate profile folder")
    parser.add_argument("--self-check", action="store_true", help="synthetic encryption/resource tests only")
    parser.add_argument("--smoke", action="store_true", help="open/check/close isolated profile chooser")
    parser.add_argument("--report", type=Path, help="non-secret diagnostic JSON")
    # The update helper's own launches (NF-9B3): the staged copy swaps folders and exits; the others only note why.
    parser.add_argument("--finish-update", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--install", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--old-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--from", dest="from_version", help=argparse.SUPPRESS)
    parser.add_argument("--after-update", metavar="OLD_VERSION", help=argparse.SUPPRESS)
    parser.add_argument("--update-failed", metavar="NEW_VERSION", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.finish_update:
        if not (args.install and args.old_pid and args.from_version):
            parser.error("--finish-update needs --install, --old-pid and --from")
        from lightning.desktop.update_helper import main as finish_update
        return finish_update(args.install, args.old_pid, args.from_version)
    report = {"ok": False, "mode": "self-check" if args.self_check else ("smoke" if args.smoke else "profiles")}
    stage = "start"
    try:
        if args.self_check:
            stage = "security-checks"
            from lightning.security.selfcheck import run_checks
            checks = run_checks()
            stage = "profile-checks"
            from lightning.runtime.selfcheck import run_profile_checks
            checks.update(run_profile_checks())
            report["checks"] = checks
            if not checks or not all(value is True for value in checks.values()):
                raise RuntimeError("A self-check failed")
        else:
            from lightning.runtime.app import profile_app
            from lightning.runtime.http import Host
            from lightning.desktop.window import run_window
            stage = "local-server"
            with ExitStack() as stack:
                root = args.profile_root
                if args.smoke:
                    root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="lightning-profile-smoke-"))) / "Profiles"
                from lightning.desktop.update_controller import for_this_app
                updates = for_this_app(args.after_update or "", args.update_failed or "")
                if updates is not None:
                    updates.startup()
                host = Host(lambda credentials: profile_app(credentials, root, updates=updates)).start()
                stage = "window"
                try:
                    result = run_window(host.launch_url, host.origin, smoke=args.smoke,
                                        diagnostics=report.setdefault("window", {}), profile_mode=True)
                    if result != 0:
                        raise RuntimeError("The profile window could not start")
                finally:
                    host.stop()
        report["ok"] = True
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error_stage"] = stage
        # Where it failed, never what it said: file, function and line only, so the report holds no
        # paths, profile names or values from the message.
        report["error_frames"] = [f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                                  for frame in traceback.extract_tb(exc.__traceback__)][-12:]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(report))
    if not report["ok"] and sys.platform == "win32" and not (args.self_check or args.smoke):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "Lightning could not start. Check the selected folder and Microsoft Edge WebView2 Runtime. Python is bundled; you do not need to install it. Run with --self-check --report result.json for a diagnostic check.", "Lightning", 0x10)
    return 0 if report["ok"] else 1
