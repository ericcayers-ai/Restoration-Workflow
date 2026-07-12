"""Double-click launcher for the packaged desktop build (PyInstaller).

`restore serve` (cli.py) is the real entry point, and is what you want in any
terminal-driven or scripted context. This wraps it for the one case a
terminal isn't there to read a URL from: a user double-clicking
RestorationWorkflow.exe. It starts the same server `restore serve` does,
against the same `AppServices`, and opens the default browser at the root URL
once the server actually starts listening — not before, and not by guessing.
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

# Absolute (not relative) imports on purpose: this module is both a package
# member (the `restoration-workflow` console script, imported as
# `restoration.launcher`) and PyInstaller's top-level entry script, where it
# runs as `__main__` with no parent package — relative imports raise there.
# Absolute imports work in both cases because `restoration` is importable.
from restoration import __version__
from restoration.api import create_app
from restoration.service import AppServices


def _open_browser_once_listening(url: str, server: uvicorn.Server) -> None:
    while not server.started:
        time.sleep(0.05)
    webbrowser.open(url)


def main() -> int:
    parser = argparse.ArgumentParser(prog="RestorationWorkflow")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cpu", action="store_true", help="force CPU even if a GPU is present")
    parser.add_argument(
        "--no-browser", action="store_true", help="don't open a browser tab automatically"
    )
    args = parser.parse_args()

    services = AppServices(force_cpu=args.cpu or None)
    app = create_app(services)

    # Windows consoles still default to a legacy code page that mangles an
    # em-dash (cli.py's _force_utf8_output note applies here too) — a plain
    # hyphen sidesteps the whole class of problem instead of reconfiguring
    # stdout for a one-line startup banner.
    print(f"Restoration Workflow {__version__} - starting at http://{args.host}:{args.port}")
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)

    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        threading.Thread(
            target=_open_browser_once_listening, args=(url, server), daemon=True
        ).start()

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
