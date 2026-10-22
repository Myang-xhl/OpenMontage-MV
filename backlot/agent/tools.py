"""Studio agent tools — definitions + handlers (ported from learn-claude-code s20).

Every handler is a plain function returning a string. File tools are confined
to the repository root (``safe_path``); ``bash`` stays powerful on purpose and
is governed by the session permission mode instead.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

from lib.paths import REPO_ROOT

DEFAULT_BASH_TIMEOUT = 300
MAX_BASH_TIMEOUT = 1800
MAX_TOOL_OUTPUT = 50_000

# Directories that are pure noise for glob/grep scans.
_SCAN_EXCLUDE = {"node_modules", ".git", "__pycache__", ".cache", ".venv",
                 "venv", ".studio", ".backlot"}


def safe_path(p: str) -> Path:
    """Resolve a path and refuse anything that escapes the repository."""
    path = Path(p)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


# ---------------------------------------------------------------------------
# File / shell tools
# ---------------------------------------------------------------------------

def run_bash(command: str, timeout: int | None = None, cancel_check=None) -> str:
    timeout = min(int(timeout or DEFAULT_BASH_TIMEOUT), MAX_BASH_TIMEOUT)
    if os.name == "nt":
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", command]
        shell = False
    else:
        argv = command
        shell = True
    try:
        # Popen + poll (instead of subprocess.run) so a user interrupt can
        # kill a long render mid-flight — Stop must not wait out the timeout.
        proc = subprocess.Popen(argv, shell=shell, cwd=REPO_ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, text=True,
                                encoding="utf-8", errors="replace",
                                **({} if os.name == "nt" else {"start_new_session": True}))
        chunks: dict = {}
        reader = threading.Thread(
            target=lambda: chunks.update(zip(("out", "err"), proc.communicate())),
            daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        while reader.is_alive():
            if cancel_check and cancel_check():
                _kill_tree(proc)
                reader.join(5)
                return "Error: Command killed — interrupted by user."
            if time.monotonic() > deadline:
                _kill_tree(proc)
                reader.join(5)
                return f"Error: Timeout ({timeout}s)"
            reader.join(0.5)
        out = ((chunks.get("out") or "") + (chunks.get("err") or "")).strip()
        if proc.returncode != 0:
            out = f"[exit code {proc.returncode}]\n{out}"
        return out[:MAX_TOOL_OUTPUT] if out else "(no output)"
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model
        return f"Error: {e}"


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a command and its children (renders spawn node/ffmpeg trees)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001 — best effort; orphans are survivable
        pass


def run_read(path: str, limit: int | None = None, offset: int = 0) -> str:
    try:
        text = safe_path(path).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        offset = max(int(offset or 0), 0)
        lines = lines[offset:]
        if limit is not None and int(limit) < len(lines):
            limit = int(limit)
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:MAX_TOOL_OUTPUT] or "(empty file)"
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        text = fp.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        fp.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def _iter_repo_files(subdir: str | None = None):
    base = safe_path(subdir) if subdir else REPO_ROOT
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SCAN_EXCLUDE]
        for name in files:
            yield Path(root) / name


def run_glob(pattern: str, path: str | None = None) -> str:
    try:
        pat = pattern if pattern.startswith("**/") or "/" in pattern else f"**/{pattern}"
        base = safe_path(path) if path else REPO_ROOT
        results = []
        for fp in _iter_repo_files(path):
            rel = fp.relative_to(base).as_posix()
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fp.name, pattern):
                results.append(fp.relative_to(REPO_ROOT).as_posix())
                if len(results) >= 500:
                    results.append("... (truncated at 500 matches)")
                    break
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


def run_grep(pattern: str, path: str | None = None, glob: str | None = None,
             max_matches: int = 100) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex — {e}"
    try:
        results: list[str] = []
        for fp in _iter_repo_files(path):
            if glob and not fnmatch.fnmatch(fp.name, glob):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in text[:1024]:
                continue  # binary
            rel = fp.relative_to(REPO_ROOT).as_posix()
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    results.append(f"{rel}:{i}: {line.strip()[:300]}")
                    if len(results) >= max_matches:
                        results.append(f"... (truncated at {max_matches} matches)")
                        return "\n".join(results)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Checkpoint protocol — native tools (infrastructure as enforcement)
# ---------------------------------------------------------------------------
# External coding agents write checkpoints via inline Python in a terminal.
# Inline Python inside PowerShell quoting is fragile enough that models skip
# the protocol entirely, so the studio harness exposes the two infrastructure
# calls as first-class tools instead.

def run_init_project(project_id: str, title: str, pipeline_type: str,
                     style_playbook: str | None = None) -> str:
    try:
        from lib.checkpoint import init_project
        kwargs = {"style_playbook": style_playbook} if style_playbook else {}
        project_dir = init_project(project_id, title=title,
                                   pipeline_type=pipeline_type, **kwargs)
        try:
            rel = project_dir.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(project_dir)
        return (f"Initialized {rel}/ (canonical layout + project.json marker). "
                f"The Backlot board for this project is /p/{project_id}.")
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model
        return f"Error: {type(e).__name__}: {e}"


def run_write_checkpoint(project_id: str, stage: str, status: str,
                         artifacts=None, pipeline_type: str | None = None,
                         human_approval_required: bool = False,
                         human_approved: bool = False,
                         error: str | None = None,
                         metadata=None) -> str:
    try:
        from lib.checkpoint import write_checkpoint
        from lib.paths import PROJECTS_DIR
        if isinstance(artifacts, str):
            try:
                artifacts = json.loads(artifacts)
            except json.JSONDecodeError:
                return "Error: artifacts must be a JSON object, got an unparseable string"
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {"note": metadata}
        path = write_checkpoint(
            PROJECTS_DIR, project_id, stage, status, artifacts or {},
            pipeline_type=pipeline_type,
            human_approval_required=bool(human_approval_required),
            human_approved=bool(human_approved),
            error=error, metadata=metadata)
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(path)
        return f"Checkpoint written: {rel} (stage={stage}, status={status})"
    except Exception as e:  # noqa: BLE001 — validation errors guide the model
        return f"Error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Todos (validation logic from s20)
# ---------------------------------------------------------------------------

def normalize_todos(todos):
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"
    if not isinstance(todos, list):
        return None, "Error: todos must be a list"
    for i, todo in enumerate(todos):
        if not isinstance(todo, dict):
            return None, f"Error: todos[{i}] must be an object"
        if "content" not in todo or "status" not in todo:
            return None, f"Error: todos[{i}] missing 'content' or 'status'"
        if todo["status"] not in ("pending", "in_progress", "completed"):
            return None, f"Error: todos[{i}] has invalid status '{todo['status']}'"
    return todos, None


# ---------------------------------------------------------------------------
# Skill catalog — OpenMontage Layer 2 (skills/) + Layer 3 (.agents/skills/)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].strip()


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line:
            return line[:120]
    return ""


def scan_skills() -> dict[str, dict]:
    """Skill id -> {description, path}. Ids mirror repo-relative paths."""
    catalog: dict[str, dict] = {}
    layer3 = REPO_ROOT / ".agents" / "skills"
    if layer3.is_dir():
        for directory in sorted(layer3.iterdir()):
            manifest = directory / "SKILL.md"
            if not directory.is_dir() or not manifest.is_file():
                continue
            try:
                raw = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, _body = _parse_frontmatter(raw)
            desc = str(meta.get("description") or _first_heading(raw))[:200]
            catalog[directory.name] = {
                "description": desc,
                "path": manifest.relative_to(REPO_ROOT).as_posix(),
            }
    layer2 = REPO_ROOT / "skills"
    if layer2.is_dir():
        for fp in sorted(layer2.rglob("*.md")):
            rel = fp.relative_to(layer2).as_posix()
            skill_id = f"skills/{rel[:-3]}"
            try:
                raw = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            catalog[skill_id] = {
                "description": _first_heading(raw)[:200],
                "path": fp.relative_to(REPO_ROOT).as_posix(),
            }
    return catalog


def list_skills(catalog: dict[str, dict] | None = None) -> str:
    catalog = catalog if catalog is not None else scan_skills()
    if not catalog:
        return "(no skills found)"
    return "\n".join(f"- {name}: {info['description']}"
                     for name, info in catalog.items())


def load_skill(name: str, catalog: dict[str, dict] | None = None) -> str:
    catalog = catalog if catalog is not None else scan_skills()
    info = catalog.get(name)
    if not info:
        # Tolerate close variants: paths, trailing .md, SKILL.md refs.
        stripped = name.strip().removeprefix("./").removesuffix("/SKILL.md").removesuffix(".md")
        info = catalog.get(stripped) or catalog.get(Path(stripped).name)
    if not info:
        return (f"Skill not found: {name}. Use list_skills or read the file "
                f"directly with read_file.")
    try:
        return safe_path(info["path"]).read_text(encoding="utf-8", errors="replace")[:MAX_TOOL_OUTPUT]
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool-use format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {"name": "bash",
     "description": (
         "Run a shell command from the repository root "
         f"({'PowerShell' if os.name == 'nt' else 'sh'} on this machine, "
         f"Python: {Path(sys.executable).name}). Use for the OpenMontage "
         "registry, checkpoints, renders, and any CLI work. Long renders may "
         "need a higher timeout."),
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "string"},
         "timeout": {"type": "integer",
                     "description": f"Seconds, default {DEFAULT_BASH_TIMEOUT}, max {MAX_BASH_TIMEOUT}."},
         "run_in_background": {"type": "boolean",
                     "description": "If true, run this command in a background thread. "
                                    "Use for slow operations (ffmpeg renders, pip install, "
                                    "video generation via the registry). You get a task id "
                                    "immediately; the real output arrives as a "
                                    "<task_notification> in the next turn. Don't block "
                                    "the conversation waiting for slow commands."}},
         "required": ["command"]}},
    {"name": "read_file",
     "description": "Read a file (repo-relative or absolute path inside the repo).",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "limit": {"type": "integer"},
         "offset": {"type": "integer"}},
         "required": ["path"]}},
    {"name": "write_file",
     "description": "Create or overwrite a file inside the repo.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "content": {"type": "string"}},
         "required": ["path", "content"]}},
    {"name": "edit_file",
     "description": "Replace the first occurrence of old_text with new_text in a file.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "old_text": {"type": "string"},
         "new_text": {"type": "string"}},
         "required": ["path", "old_text", "new_text"]}},
    {"name": "glob",
     "description": "Find files by glob pattern (e.g. *.yaml, pipeline_defs/*.yaml).",
     "input_schema": {"type": "object", "properties": {
         "pattern": {"type": "string"},
         "path": {"type": "string", "description": "Subdirectory to search in."}},
         "required": ["pattern"]}},
    {"name": "grep",
     "description": "Search file contents by regex. Optional filename glob filter.",
     "input_schema": {"type": "object", "properties": {
         "pattern": {"type": "string"},
         "path": {"type": "string"},
         "glob": {"type": "string"}},
         "required": ["pattern"]}},
    {"name": "init_project",
     "description": (
         "Initialize a production project workspace: creates projects/<id>/ "
         "with the canonical layout and the project.json marker the Backlot "
         "board renders. Call this at pipeline init, BEFORE producing any "
         "artifact. Idempotent."),
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string", "description": "kebab-case, e.g. blackhole-explainer-01"},
         "title": {"type": "string"},
         "pipeline_type": {"type": "string", "description": "A pipeline id from pipeline_defs/, e.g. animated-explainer"},
         "style_playbook": {"type": "string"}},
         "required": ["project_id", "title", "pipeline_type"]}},
    {"name": "write_checkpoint",
     "description": (
         "Record a pipeline stage checkpoint (the ONLY sanctioned way — do "
         "not write checkpoint JSON by hand). Call after every stage: "
         "status='completed' when done, 'awaiting_human' at a human gate "
         "(then end your turn), 'failed' with error on failure. Validation "
         "and gate-enforcement errors come back as text — fix and retry."),
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"},
         "stage": {"type": "string", "description": "Stage name from the pipeline manifest"},
         "status": {"type": "string", "enum": ["completed", "awaiting_human", "failed", "in_progress"]},
         "artifacts": {"type": "object", "description": "Stage outputs — file paths under projects/<id>/ plus key fields"},
         "pipeline_type": {"type": "string"},
         "human_approval_required": {"type": "boolean"},
         "human_approved": {"type": "boolean", "description": "Set true only after the user explicitly approved in chat"},
         "error": {"type": "string"},
         "metadata": {"type": "object"}},
         "required": ["project_id", "stage", "status", "artifacts"]}},
    {"name": "todo_write",
     "description": ("Replace your plan with a list of "
                     "{content, status: pending|in_progress|completed} items. "
                     "Keep it current — the user sees it live."),
     "input_schema": {"type": "object", "properties": {
         "todos": {"type": "array", "items": {"type": "object", "properties": {
             "content": {"type": "string"},
             "status": {"type": "string",
                        "enum": ["pending", "in_progress", "completed"]}},
             "required": ["content", "status"]}}},
         "required": ["todos"]}},
    {"name": "list_skills",
     "description": "List the OpenMontage skill catalog (Layer 2 + Layer 3) with descriptions.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "load_skill",
     "description": ("Load a skill's full content by id from list_skills "
                     "(e.g. 'ai-video-gen' or 'skills/meta/onboarding')."),
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}},
         "required": ["name"]}},
    {"name": "task",
     "description": (
         "Launch a subagent with a fresh context to handle a complex subtask. "
         "The subagent has bash/read/write/edit/glob/grep/load_skill but "
         "CANNOT spawn further subagents. Only the final summary is returned — "
         "intermediate tool results are discarded, keeping this conversation "
         "clean. Use for isolated multi-step work like generating and verifying "
         "a single video clip, or exploring a complex file structure."),
     "input_schema": {"type": "object", "properties": {
         "description": {"type": "string",
             "description": "A complete, self-contained task description for the subagent."}},
         "required": ["description"]}},
    {"name": "compact",
     "description": "Summarize and compress the conversation history when context grows too large.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
]

# Tools that a 'confirm' permission session must hold for web approval.
CONFIRM_TOOLS = {"bash", "write_file", "edit_file"}


def build_handlers(session) -> dict:
    """Dispatch map. ``session`` supplies todo state and the skill catalog."""

    def _todo_write(todos):
        todos, error = normalize_todos(todos)
        if error:
            return error
        session.set_todos(todos)
        return f"Updated {len(todos)} todos"

    def _task(description):
        from backlot.agent.subagent import spawn_subagent
        return spawn_subagent(session, description)

    return {
        "bash": lambda command, timeout=None: run_bash(
            command, timeout, cancel_check=session.interrupted),
        "read_file": run_read,
        "write_file": run_write,
        "edit_file": run_edit,
        "glob": run_glob,
        "grep": run_grep,
        "init_project": run_init_project,
        "write_checkpoint": run_write_checkpoint,
        "todo_write": _todo_write,
        "task": _task,
        "list_skills": lambda: list_skills(session.skill_catalog),
        "load_skill": lambda name: load_skill(name, session.skill_catalog),
        # "compact" is intercepted inside the loop, never dispatched here.
    }


def call_tool_handler(handler, args: dict, name: str) -> str:
    if not handler:
        return f"Unknown tool: {name}"
    try:
        return str(handler(**(args or {})))
    except TypeError as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"
