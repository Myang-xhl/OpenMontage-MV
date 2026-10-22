"""Background task manager — slow operations run in daemon threads.

Ported from learn-claude-code s13. When the agent calls a slow tool (ffmpeg
render, yinghe video generation, pip install), the call is dispatched to a
background thread. The main loop gets an immediate placeholder tool_result;
when the background task finishes, a ``<task_notification>`` is injected into
the next turn's messages.

Thread model: each session owns one ``BackgroundTaskManager``. Tasks run in
daemon threads (killed when the process exits). State is in-memory only —
a server restart drops in-flight background tasks, which is acceptable for
a video-production workbench where assets are regenerable.
"""

from __future__ import annotations

import threading
from typing import Callable

# Keywords that indicate a slow operation. Used as a fallback when the model
# doesn't set run_in_background explicitly. These cover the OpenMontage
# toolchain: yinghe video API (async polling up to 600s), ffmpeg compose
# (minutes), and package installs.
_SLOW_KEYWORDS = [
    # Package management
    "install", "pip install", "npm install",
    # Build / compile
    "build", "compile", "make",
    # Testing / deployment
    "test", "pytest", "deploy",
    # OpenMontage-specific slow operations
    "yinghe", "ffmpeg", "render", "seedance",
    # Video generation via registry
    "video/generation", "python -c",
]


def is_slow_operation(tool_name: str, tool_input: dict) -> bool:
    """Fallback heuristic: commands likely to take > 30s."""
    if tool_name != "bash":
        return False
    cmd = tool_input.get("command", "").lower()
    return any(kw in cmd for kw in _SLOW_KEYWORDS)


def should_run_background(tool_name: str, tool_input: dict) -> bool:
    """Decide whether a tool call should run in the background.

    Model explicit request (run_in_background=true) takes priority;
    otherwise fall back to the slow-operation heuristic.
    """
    if tool_input.get("run_in_background"):
        return True
    return is_slow_operation(tool_name, tool_input)


class BackgroundTaskManager:
    """Thread-safe registry of background tasks for one session."""

    def __init__(self):
        self._counter = 0
        self._tasks: dict[str, dict] = {}    # bg_id -> {tool_use_id, command, status}
        self._results: dict[str, str] = {}  # bg_id -> output
        self._lock = threading.Lock()

    def start(
        self,
        tool_use_id: str,
        tool_name: str,
        tool_input: dict,
        execute_fn: Callable[[str, dict], str],
        emit: Callable[..., None] | None = None,
    ) -> str:
        """Dispatch a tool call to a daemon thread. Returns bg_id.

        ``execute_fn(tool_name, tool_input)`` is called in the background
        thread. ``run_in_background`` is stripped from ``tool_input``
        before calling — it is a dispatch hint, not a tool parameter.
        """
        with self._lock:
            self._counter += 1
            bg_id = f"bg_{self._counter:04d}"
            command = tool_input.get("command", tool_name)
            self._tasks[bg_id] = {
                "tool_use_id": tool_use_id,
                "command": command,
                "status": "running",
            }

        def worker():
            try:
                ti = {k: v for k, v in tool_input.items()
                      if k != "run_in_background"}
                result = execute_fn(tool_name, ti)
            except Exception as e:  # noqa: BLE001 — background errors must not crash
                result = f"Error: {type(e).__name__}: {e}"
            with self._lock:
                if bg_id in self._tasks:
                    self._tasks[bg_id]["status"] = "completed"
                    self._results[bg_id] = result
            if emit:
                emit("background_done", {"bg_id": bg_id, "command": command})

        thread = threading.Thread(target=worker, daemon=True,
                                  name=f"bg-{bg_id}")
        thread.start()
        return bg_id

    def collect_notifications(self) -> list[dict]:
        """Collect completed results. Returns list of notification dicts.

        Each dict: {bg_id, command, summary, full_output}.
        Completed tasks are removed from the registry.
        """
        with self._lock:
            ready_ids = [bid for bid, task in self._tasks.items()
                         if task["status"] == "completed"]
            collected = []
            for bg_id in ready_ids:
                task = self._tasks.pop(bg_id)
                output = self._results.pop(bg_id, "")
                collected.append({
                    "bg_id": bg_id,
                    "command": task["command"],
                    "summary": output[:500] if len(output) > 500 else output,
                    "full_output": output,
                })
            return collected

    def pending_count(self) -> int:
        """Number of background tasks still running."""
        with self._lock:
            return sum(1 for t in self._tasks.values()
                       if t["status"] == "running")

    def format_notification(self, notif: dict) -> str:
        """Format a notification dict as an XML task_notification string."""
        return (
            "<task_notification>\n"
            f"  <task_id>{notif['bg_id']}</task_id>\n"
            "  <status>completed</status>\n"
            f"  <command>{notif['command']}</command>\n"
            f"  <summary>{notif['summary']}</summary>\n"
            "</task_notification>"
        )
