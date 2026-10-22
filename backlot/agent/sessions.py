"""Studio chat sessions — threads, event feed, approvals, persistence.

Each session owns: the model-facing message history, a monotonically numbered
event feed for the web UI, the current todo list, and (at most) one agent
turn running on a dedicated thread. Everything is append-only JSONL on disk
(``.studio/sessions/<id>.jsonl``) so a server restart resumes conversations.

The FastAPI layer only ever calls thread-safe methods here; the agent loop
(harness.run_turn) runs blocking in the session thread and talks back through
``emit`` / ``request_approval`` / ``interrupted``.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from pathlib import Path

from backlot.agent import harness, tools
from backlot.agent.background import BackgroundTaskManager
from lib.paths import PROJECTS_DIR, REPO_ROOT

SESSIONS_DIR = REPO_ROOT / ".studio" / "sessions"
APPROVAL_TIMEOUT_SECONDS = 24 * 3600  # a human gate can legitimately wait long
MAX_EVENT_REPLAY = 2000

_PROJECT_ID_RE = re.compile(r"projects[/\\]([A-Za-z0-9._-]+)")


class SessionBusyError(RuntimeError):
    pass


class Session:
    def __init__(self, session_id: str, permission_mode: str = "auto"):
        self.id = session_id
        self.permission_mode = permission_mode if permission_mode in ("auto", "confirm") else "auto"
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.todos: list[dict] = []
        self.title = ""
        self.project_id: str | None = None
        self.status = "idle"  # idle | running | awaiting_approval
        self.created_at = time.time()

        self.skill_catalog = tools.scan_skills()
        self.background = BackgroundTaskManager()

        self._lock = threading.Lock()
        self._new_event = threading.Condition(self._lock)
        self._interrupt = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_approval: dict | None = None
        self._approval_decision: bool | None = None
        self._path = SESSIONS_DIR / f"{session_id}.jsonl"

    # -- persistence -------------------------------------------------------

    def _append_record(self, record: dict) -> None:
        try:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # persistence is best-effort; the live session keeps working

    @classmethod
    def load(cls, path: Path) -> "Session | None":
        try:
            session = cls(path.stem)
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = record.get("t")
                if kind == "meta":
                    session.permission_mode = record.get("permission_mode", session.permission_mode)
                    session.title = record.get("title", session.title)
                    session.created_at = record.get("created_at", session.created_at)
                elif kind == "msg":
                    session.messages.append(record["m"])
                elif kind == "ev":
                    event = record["e"]
                    session.events.append(event)
                    if event.get("type") == "todos":
                        session.todos = event.get("data", {}).get("todos", [])
                    if event.get("type") == "project":
                        session.project_id = event.get("data", {}).get("project_id")
            # A restart kills any in-flight thread; surface that honestly.
            # A cleanly finished turn ends with turn_done + state{idle}.
            last = session.events[-1] if session.events else None
            clean = last is None or last.get("type") in ("turn_done", "error") or (
                last.get("type") == "state"
                and last.get("data", {}).get("status") == "idle")
            if not clean:
                with session._lock:
                    session._emit_unlocked("error", {"text": "Server restarted mid-turn. Send a message to continue."})
            return session
        except OSError:
            return None

    # -- events ------------------------------------------------------------

    def _emit_unlocked(self, event_type: str, data: dict) -> dict:
        event = {"seq": len(self.events) + 1, "ts": time.time(),
                 "type": event_type, "data": data}
        self.events.append(event)
        self._append_record({"t": "ev", "e": event})
        self._new_event.notify_all()
        return event

    def emit(self, event_type: str, data: dict) -> None:
        with self._lock:
            self._emit_unlocked(event_type, data)
        # Project detection rides on the event stream: the first time a
        # projects/<id> path shows up in a tool call/result, pin the board.
        if self.project_id is None and event_type in ("tool_call", "tool_result"):
            self._detect_project(json.dumps(data, default=str, ensure_ascii=False))

    def _detect_project(self, text: str) -> None:
        for match in _PROJECT_ID_RE.finditer(text):
            candidate = match.group(1)
            if candidate.startswith((".", "_")):
                continue
            if (PROJECTS_DIR / candidate).is_dir():
                self.project_id = candidate
                with self._lock:
                    self._emit_unlocked("project", {"project_id": candidate})
                return

    def wait_events(self, after_seq: int, timeout: float = 25.0) -> list[dict]:
        """Events with seq > after_seq; blocks up to timeout if none yet."""
        deadline = time.time() + timeout
        with self._lock:
            while True:
                fresh = [e for e in self.events[-MAX_EVENT_REPLAY:]
                         if e["seq"] > after_seq]
                if fresh:
                    return fresh
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._new_event.wait(remaining)

    # -- session protocol used by the harness -------------------------------

    def interrupted(self) -> bool:
        return self._interrupt.is_set()

    def set_todos(self, todos: list[dict]) -> None:
        self.todos = todos
        self.emit("todos", {"todos": todos})

    def request_approval(self, tool_use_id: str, name: str, tool_input: dict) -> bool:
        with self._lock:
            self._pending_approval = {"tool_use_id": tool_use_id, "name": name,
                                      "input": tool_input}
            self._approval_decision = None
            self.status = "awaiting_approval"
            self._emit_unlocked("approval_request", dict(self._pending_approval))
            deadline = time.time() + APPROVAL_TIMEOUT_SECONDS
            while self._approval_decision is None:
                if self._interrupt.is_set():
                    break
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._new_event.wait(min(remaining, 1.0))
            decision = bool(self._approval_decision)
            self._pending_approval = None
            self._approval_decision = None
            self.status = "running"
            return decision

    # -- web-facing operations ----------------------------------------------

    def post_message(self, text: str) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise SessionBusyError("Agent is still working — interrupt it or wait.")
            if not self.title:
                self.title = text.strip().splitlines()[0][:80]
                self._append_record({"t": "meta", "title": self.title,
                                     "permission_mode": self.permission_mode,
                                     "created_at": self.created_at})
            self._interrupt.clear()
            message = {"role": "user", "content": text}
            self.messages.append(message)
            self._append_record({"t": "msg", "m": message})
            self._emit_unlocked("user", {"text": text})
            self.status = "running"
            self._emit_unlocked("state", {"status": "running"})
            self._thread = threading.Thread(target=self._run_turn, daemon=True,
                                            name=f"studio-{self.id}")
            self._thread.start()

    def _run_turn(self) -> None:
        persisted = len(self.messages)
        try:
            harness.run_turn(self)
        except harness.ModelError as e:
            self.emit("error", {"text": str(e)})
        except Exception as e:  # noqa: BLE001 — turn must never kill the server
            self.emit("error", {"text": f"{type(e).__name__}: {e}"})
        finally:
            # Persist everything the turn appended (assistant + tool_results).
            # Compaction may have REPLACED history — detect and rewrite whole file.
            with self._lock:
                if len(self.messages) < persisted or any(
                        isinstance(m.get("content"), str)
                        and m["content"].startswith("[Compacted conversation summary]")
                        for m in self.messages[:1]):
                    self._rewrite_file()
                else:
                    for message in self.messages[persisted:]:
                        self._append_record({"t": "msg", "m": message})
                self.status = "idle"
                self._emit_unlocked("turn_done", {})
                self._emit_unlocked("state", {"status": "idle"})

    def _rewrite_file(self) -> None:
        try:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"t": "meta", "title": self.title,
                                    "permission_mode": self.permission_mode,
                                    "created_at": self.created_at},
                                   ensure_ascii=False) + "\n")
                for message in self.messages:
                    f.write(json.dumps({"t": "msg", "m": message},
                                       ensure_ascii=False, default=str) + "\n")
                for event in self.events:
                    f.write(json.dumps({"t": "ev", "e": event},
                                       ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def resolve_approval(self, approve: bool) -> bool:
        with self._lock:
            if self._pending_approval is None:
                return False
            self._approval_decision = bool(approve)
            self._new_event.notify_all()
            return True

    def interrupt(self) -> None:
        self._interrupt.set()
        with self._lock:
            self._new_event.notify_all()

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title or "(new session)",
            "status": self.status if (self._thread and self._thread.is_alive()) else "idle",
            "permission_mode": self.permission_mode,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "last_seq": self.events[-1]["seq"] if self.events else 0,
            "todos": self.todos,
        }


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if SESSIONS_DIR.is_dir():
                for path in sorted(SESSIONS_DIR.glob("*.jsonl")):
                    if path.stem not in self._sessions:
                        session = Session.load(path)
                        if session:
                            self._sessions[session.id] = session
            self._loaded = True

    def create(self, permission_mode: str = "auto") -> Session:
        self._ensure_loaded()
        session_id = (f"s-{time.strftime('%Y%m%d-%H%M%S')}"
                      f"-{random.randint(0, 9999):04d}")
        session = Session(session_id, permission_mode)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        self._ensure_loaded()
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        """Drop a session and its transcript file. Busy sessions refuse."""
        self._ensure_loaded()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            if session._thread and session._thread.is_alive():
                raise SessionBusyError("Agent is still working — interrupt it before deleting.")
            self._sessions.pop(session_id, None)
        try:
            session._path.unlink(missing_ok=True)
        except OSError:
            pass  # in-memory removal already happened; stale file is harmless
        return True

    def list(self) -> list[dict]:
        self._ensure_loaded()
        summaries = [s.summary() for s in self._sessions.values()]
        summaries.sort(key=lambda s: -s["created_at"])
        return summaries


manager = SessionManager()
