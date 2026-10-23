"""Start Lightning: back up, migrate, then serve the app on this computer only.

    python -m lightning                 # opens http://127.0.0.1:8765 in your browser
    python -m lightning --db my.db --port 9000 --no-browser
    python -m lightning --demo          # a sample household in its own database, on port 8766
    python -m lightning --sample        # Mohab's 2026 from the sample CSVs, in its own database, on port 8767
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

if sys.version_info < (3, 11):
    sys.exit("Lightning needs Python 3.11 or newer.")


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    from lightning.bootstrap import DEFAULT_DATA_DIR, build
    from lightning.ui.web import create_app

    parser = argparse.ArgumentParser(prog="lightning", description="Personal finance, in one place.")
    parser.add_argument("--db", default=str(DEFAULT_DATA_DIR / "lightning.db"), help="database file")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--profiles", action="store_true", help="password-protected profiles in Documents/Lightning")
    parser.add_argument("--profile-root", help="explicit alternate profile folder (with --profiles)")
    parser.add_argument("--demo", action="store_true",
                        help="open a sample household in a separate demo database (rebuilt on every start)")
    parser.add_argument("--sample", action="store_true",
                        help="open Mohab's 2026 (loaded from the sample CSVs) in a separate database (rebuilt on every start)")
    args = parser.parse_args(argv)
    if args.demo and args.sample:
        parser.error("choose --demo or --sample, not both")
    sample = "sample" if args.sample else "demo" if args.demo else None
    args.demo = bool(sample)
    if args.profiles:
        if args.demo or args.db != str(DEFAULT_DATA_DIR / "lightning.db") or args.port != 8765:
            parser.error("--profiles uses its own chooser and a random local port; omit --demo, --db and --port")
        from lightning.runtime.launcher import run_browser
        run_browser(args.profile_root, open_browser=not args.no_browser)
        return
    if args.profile_root:
        parser.error("--profile-root requires --profiles")
    if args.demo:
        # The demo file is deleted and rebuilt on every start, so it can never be pointed at real data.
        if args.db != str(DEFAULT_DATA_DIR / "lightning.db"):
            parser.error(f"--{sample} always uses its own database (data/{sample}.db); leave out --db")
        args.db = str(DEFAULT_DATA_DIR / f"{sample}.db")
        if args.port == 8765:
            args.port = 8766 if sample == "demo" else 8767  # never collide with (or reuse) your real Lightning

    url = f"http://127.0.0.1:{args.port}"
    # Reuse the server on repeated desktop launches before backing up or refreshing prices.
    try:
        with urlopen(f"{url}/__health", timeout=1) as response:
            if response.read(32) == b"lightning-ok":
                print(f"Lightning is already running at {url}.")
                return
    except (OSError, URLError):
        pass
    try:
        with socket.create_connection(("127.0.0.1", args.port), timeout=1):
            parser.error(f"port {args.port} is already used by another application")
    except OSError:
        pass

    if args.demo:  # only once no demo server is using the file
        from pathlib import Path
        for suffix in ("", "-wal", "-shm"):
            Path(args.db + suffix).unlink(missing_ok=True)
    if sample == "sample":
        from lightning.samples import pin_sample_today
        pin_sample_today()  # inside the sample's data, unless LIGHTNING_TODAY says otherwise
    container = build(args.db, backup_on_start=not args.demo)
    if sample == "demo":
        from lightning.demo import build_demo
        summary = build_demo(container)
        print(f"Demo household ready: {summary['accounts']} accounts, {summary['from']} to {summary['to']}.")
    elif sample == "sample":
        from lightning.samples import load_mohab_2026
        summary = load_mohab_2026(container)
        print(f"Mohab's 2026 ready: {summary['rows']} imported rows, {summary['from']} to {summary['to']}.")
    from lightning.workflows.profile_open import open_profile_tasks
    for report in open_profile_tasks(container, wait=True):  # prices, missing closes, month-end checkpoints
        print(report if isinstance(report, str) else report.summary())
    app = create_app(container)
    print(f"Lightning is running at {url}  (data: {container.db.path})  — press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
