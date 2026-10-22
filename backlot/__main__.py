"""Backlot CLI.

    python -m backlot open [project-id]   # start server if needed, open browser
    python -m backlot serve [--port N]    # run the server in the foreground
    python -m backlot studio              # start server if needed, open /studio

``open`` is idempotent and non-fatal by design: agents call it at pipeline
initialization and must continue the production even if it fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from backlot import DEFAULT_PORT

LOG_PATH = Path(__file__).resolve().parent.parent / ".studio" / "server.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # keep the log from growing unbounded


def _port() -> int:
    try:
        return int(os.environ.get("BACKLOT_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _open_log_file():
    """Append handle to .studio/server.log, rotating once when it gets big."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        if LOG_PATH.is_file() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
    except OSError:
        pass
    return LOG_PATH.open("a", encoding="utf-8", errors="replace")


def _spawn_server(port: int) -> None:
    """Start the server as a detached background process, logging to file."""
    cmd = [sys.executable, "-u", "-m", "backlot", "serve", "--port", str(port)]
    try:
        log = _open_log_file()
        log.write(f"--- backlot server spawn (port {port}) {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log.flush()
    except OSError:
        log = subprocess.DEVNULL
    kwargs: dict = {
        "stdout": log,
        "stderr": subprocess.STDOUT if log is not subprocess.DEVNULL else subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kwargs)
    finally:
        if log is not subprocess.DEVNULL:
            log.close()  # child holds its own handle


def cmd_open(project_id: str | None, path: str | None = None) -> int:
    port = _port()
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"backlot: could not start server ({exc}) — continuing without the board")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print("backlot: server did not come up in time — continuing without the board")
            return 1
    url = f"http://127.0.0.1:{port}/"
    if path:
        url = f"http://127.0.0.1:{port}{path}"
    elif project_id:
        url = f"http://127.0.0.1:{port}/p/{project_id}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"backlot: {url}")
    return 0


def cmd_serve(port: int) -> int:
    import uvicorn

    # Bind loopback by default so a laptop dev server isn't silently exposed.
    # Set BACKLOT_HOST=0.0.0.0 to publish on the LAN (e.g. for intranet peers).
    host = os.environ.get("BACKLOT_HOST", "127.0.0.1")
    uvicorn.run("backlot.server:app", host=host, port=port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backlot", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_open = sub.add_parser("open", help="open the board in the browser (starts server if needed)")
    p_open.add_argument("project_id", nargs="?", default=None)

    p_serve = sub.add_parser("serve", help="run the Backlot server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())

    sub.add_parser("studio", help="open the Studio chat workbench (starts server if needed)")

    args = parser.parse_args(argv)
    if args.command == "open":
        return cmd_open(args.project_id)
    if args.command == "serve":
        return cmd_serve(args.port)
    if args.command == "studio":
        return cmd_open(None, path="/studio")
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
