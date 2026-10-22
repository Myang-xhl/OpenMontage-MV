"""Studio agent loop — ported from learn-claude-code s20 (practical core set).

One blocking loop per turn: prepare context -> call model -> execute tool_use
blocks -> append tool_results -> repeat until the model stops. Includes the
s20 error-recovery ladder (429/529 backoff, fallback model, max_tokens
escalation + continuation, reactive compact) and a two-layer context budget
(old tool_result trimming, then model-summarized compaction).

The loop never touches the web layer directly: it talks to a ``session``
object (see sessions.py) for messages, events, todos, approval gates, and
interrupts. ``MODEL_ID=mock`` swaps in a scripted client so the whole
web -> loop -> tools -> SSE path can be verified without an API key.
"""

from __future__ import annotations

import json
import os
import random
import time
from types import SimpleNamespace

from backlot.agent import background, tools as T
from backlot.agent.prompts import assemble_system_prompt
from lib.env_loader import load_env

DEFAULT_MAX_TOKENS = 8000
ESCALATED_MAX_TOKENS = 16000
MAX_RETRIES = 3
MAX_CONSECUTIVE_529 = 2
MAX_RECOVERY_RETRIES = 2
BASE_DELAY_MS = 500
# Character budget (~4 chars/token). Tool outputs in this repo are large
# (registry dumps, render logs), so the ceiling is generous.
CONTEXT_LIMIT_CHARS = 360_000
KEEP_RECENT_TOOL_RESULTS = 3
COMPACTED_RESULT_NOTE = "[Earlier tool result compacted. Re-run the tool if needed.]"
CONTINUATION_PROMPT = "Continue from the previous response. Do not repeat completed work."


class ModelError(RuntimeError):
    """Raised when the model cannot be reached after all recovery attempts."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def make_client():
    """Return (client, model_id, fallback_model_id). Honors MODEL_ID=mock."""
    load_env()
    model = os.environ.get("MODEL_ID", "").strip()
    if not model:
        raise ModelError(
            "MODEL_ID is not set. Add MODEL_ID (and ANTHROPIC_API_KEY / "
            "ANTHROPIC_BASE_URL for compatible providers) to your .env.")
    if model.lower() == "mock":
        return MockClient(), "mock", None
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise ModelError("The 'anthropic' package is not installed — "
                         "run: pip install anthropic") from e
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise ModelError("ANTHROPIC_API_KEY is not set in .env.")
    client = Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL") or None)
    return client, model, os.environ.get("FALLBACK_MODEL_ID") or None


class MockClient:
    """Scripted stand-in: one bash echo tool_use, then a closing text reply."""

    class _Messages:
        def __init__(self):
            self._turn_calls = 0

        def create(self, **kwargs):
            messages = kwargs.get("messages", [])
            last = messages[-1] if messages else {}
            content = last.get("content") if isinstance(last, dict) else None
            is_tool_reply = (isinstance(content, list) and content
                             and isinstance(content[0], dict)
                             and content[0].get("type") == "tool_result")
            if not is_tool_reply:
                blocks = [
                    SimpleNamespace(type="text",
                                    text="[mock] Running a probe command."),
                    SimpleNamespace(type="tool_use", id=f"mock_{int(time.time()*1000)}",
                                    name="bash",
                                    input={"command": "echo mock-harness-ok"}),
                ]
                return SimpleNamespace(content=blocks, stop_reason="tool_use")
            blocks = [SimpleNamespace(
                type="text",
                text="[mock] Turn complete — harness, tools, SSE and "
                     "persistence are wired correctly.")]
            return SimpleNamespace(content=blocks, stop_reason="end_turn")

    def __init__(self):
        self.messages = MockClient._Messages()


# ---------------------------------------------------------------------------
# Message helpers (plain-dict messages; model output normalized immediately)
# ---------------------------------------------------------------------------

def normalize_content(content) -> list[dict]:
    """SDK content blocks -> JSON-serializable dicts (for history on disk)."""
    out = []
    for block in content:
        btype = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None)
        if btype == "text":
            text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
            out.append({"type": "text", "text": text or ""})
        elif btype == "tool_use":
            if isinstance(block, dict):
                out.append({"type": "tool_use", "id": block.get("id"),
                            "name": block.get("name"), "input": block.get("input") or {}})
            else:
                out.append({"type": "tool_use", "id": block.id,
                            "name": block.name, "input": dict(block.input or {})})
        # thinking/other block types are dropped from durable history
    return out


def has_tool_use(content: list[dict]) -> bool:
    return any(b.get("type") == "tool_use" for b in content)


def extract_text(content: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in content
                     if b.get("type") == "text").strip()


def estimate_size(messages: list) -> int:
    return len(json.dumps(messages, default=str, ensure_ascii=False))


def _collect_tool_results(messages: list) -> list[dict]:
    blocks = []
    for msg in messages:
        content = msg.get("content")
        if msg.get("role") != "user" or not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                blocks.append(block)
    return blocks


def micro_compact(messages: list) -> None:
    """Blank out old tool_result payloads, keeping the most recent few."""
    results = _collect_tool_results(messages)
    if len(results) <= KEEP_RECENT_TOOL_RESULTS:
        return
    for block in results[:-KEEP_RECENT_TOOL_RESULTS]:
        if len(str(block.get("content", ""))) > 200:
            block["content"] = COMPACTED_RESULT_NOTE


def is_prompt_too_long_error(e: Exception) -> bool:
    msg = str(e).lower()
    return (("prompt" in msg and "long" in msg)
            or "context_length_exceeded" in msg
            or "max_context_window" in msg)


# ---------------------------------------------------------------------------
# Error recovery (s20)
# ---------------------------------------------------------------------------

class RecoveryState:
    def __init__(self, model: str):
        self.has_escalated = False
        self.recovery_count = 0
        self.consecutive_529 = 0
        self.has_attempted_reactive_compact = False
        self.current_model = model


def _retry_delay(attempt: int) -> float:
    base = min(BASE_DELAY_MS * (2 ** attempt), 32_000) / 1000
    return base + random.uniform(0, base * 0.25)


def with_retry(fn, state: RecoveryState, fallback_model: str | None, emit):
    for attempt in range(MAX_RETRIES):
        try:
            result = fn()
            state.consecutive_529 = 0
            return result
        except Exception as e:  # noqa: BLE001 — classified below
            name = type(e).__name__.lower()
            msg = str(e).lower()
            if "ratelimit" in name or "429" in msg:
                delay = _retry_delay(attempt)
                emit("status", {"text": f"Rate limited — retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s"})
                time.sleep(delay)
                continue
            if "overloaded" in name or "overloaded" in msg or "529" in msg:
                state.consecutive_529 += 1
                if state.consecutive_529 >= MAX_CONSECUTIVE_529 and fallback_model:
                    state.current_model = fallback_model
                    state.consecutive_529 = 0
                    emit("status", {"text": f"Provider overloaded — switching to {fallback_model}"})
                delay = _retry_delay(attempt)
                emit("status", {"text": f"Overloaded — retry {attempt + 1}/{MAX_RETRIES} in {delay:.1f}s"})
                time.sleep(delay)
                continue
            raise
    raise ModelError(f"Model unavailable after {MAX_RETRIES} retries")


# ---------------------------------------------------------------------------
# Compaction (summary layer)
# ---------------------------------------------------------------------------

def summarize_history(client, model: str, messages: list) -> str:
    conversation = json.dumps(messages, default=str, ensure_ascii=False)[:80_000]
    prompt = ("Summarize this video-production agent conversation so work can "
              "continue seamlessly. Preserve: current goal, chosen pipeline and "
              "project id, provider/model decisions, completed stages and "
              "checkpoints, generated asset paths, pending approvals, and user "
              "constraints.\n\n" + conversation)
    response = client.messages.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000)
    return extract_text(normalize_content(response.content)) or "(empty summary)"


def compact_history(client, model: str, messages: list, emit) -> list:
    emit("status", {"text": "Compacting conversation history…"})
    try:
        summary = summarize_history(client, model, messages)
    except Exception:  # noqa: BLE001 — degraded but functional
        summary = "Earlier conversation was trimmed (summary unavailable)."
    return [{"role": "user", "content": f"[Compacted conversation summary]\n\n{summary}"}]


def reactive_compact(client, model: str, messages: list, emit) -> list:
    """Prompt-too-long recovery: summarize everything but the recent tail."""
    tail_start = max(0, len(messages) - 5)
    # Never split a tool_use/tool_result pair across the cut.
    while tail_start > 0:
        msg = messages[tail_start]
        content = msg.get("content")
        if (msg.get("role") == "user" and isinstance(content, list)
                and any(isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content)):
            tail_start -= 1
        else:
            break
    try:
        summary = summarize_history(client, model, messages[:tail_start])
    except Exception:  # noqa: BLE001
        summary = "Earlier conversation was trimmed after a prompt-too-long error."
    emit("status", {"text": "Context overflow — compacted older history."})
    return ([{"role": "user", "content": f"[Compacted conversation summary]\n\n{summary}"}]
            + messages[tail_start:])


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def run_turn(session) -> None:
    """Run one agent turn on ``session`` until the model stops (or error).

    Session protocol used here:
      messages: list[dict]            emit(type, payload)
      skill_catalog: dict             interrupted() -> bool
      permission_mode: 'auto'|'confirm'
      request_approval(tool, input) -> bool   (blocks; False = denied)
    """
    client, model, fallback = make_client()
    handlers = T.build_handlers(session)
    state = RecoveryState(model)
    max_tokens = DEFAULT_MAX_TOKENS
    system = assemble_system_prompt(session.skill_catalog)
    messages = session.messages

    while True:
        if session.interrupted():
            session.emit("status", {"text": "Interrupted by user."})
            return

        micro_compact(messages)
        if estimate_size(messages) > CONTEXT_LIMIT_CHARS:
            messages[:] = compact_history(client, state.current_model, messages, session.emit)

        try:
            response = with_retry(
                lambda: client.messages.create(
                    model=state.current_model,
                    system=system,
                    messages=messages,
                    tools=T.TOOL_DEFINITIONS,
                    max_tokens=max_tokens),
                state, fallback, session.emit)
        except ModelError:
            raise
        except Exception as e:  # noqa: BLE001
            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:
                messages[:] = reactive_compact(client, state.current_model,
                                               messages, session.emit)
                state.has_attempted_reactive_compact = True
                continue
            raise ModelError(f"{type(e).__name__}: {e}") from e

        content = normalize_content(response.content)

        if response.stop_reason == "max_tokens":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                session.emit("status", {"text": "Response truncated — retrying with a larger budget."})
                continue
            messages.append({"role": "assistant", "content": content})
            _emit_assistant(session, content)
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            return

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False
        messages.append({"role": "assistant", "content": content})
        _emit_assistant(session, content)

        if not has_tool_use(content):
            return

        results = []
        compacted_now = False
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if session.interrupted():
                results.append(_tool_result(block, "[Interrupted by user before execution]"))
                continue

            name, tool_input = block["name"], block.get("input") or {}

            if name == "compact":
                messages[:] = compact_history(client, state.current_model,
                                              messages, session.emit)
                messages.append({"role": "user",
                                 "content": "[Compacted. Continue with summarized context.]"})
                compacted_now = True
                break

            # Wrap the entire per-block execution in try-except so that
            # ANY exception (emit failure, approval timeout, background
            # dispatch error) still produces a tool_result. Without this,
            # an orphaned tool_use block causes a 400 on the next API call.
            try:
                session.emit("tool_call", {"id": block["id"], "name": name,
                                           "input": tool_input})

                if session.permission_mode == "confirm" and name in T.CONFIRM_TOOLS:
                    approved = session.request_approval(block["id"], name, tool_input)
                    if not approved:
                        output = "[Denied by user. Ask how to proceed instead of retrying.]"
                        session.emit("tool_result", {"id": block["id"], "name": name,
                                                     "output": output, "denied": True})
                        results.append(_tool_result(block, output))
                        continue

                # s13: Background task dispatch — slow operations go to a
                # daemon thread; the main loop gets a placeholder result and
                # the real output arrives as <task_notification> next turn.
                if background.should_run_background(name, tool_input):
                    bg_id = session.background.start(
                        tool_use_id=block["id"], tool_name=name,
                        tool_input=tool_input,
                        execute_fn=lambda tn, ti: T.call_tool_handler(
                            handlers.get(tn), ti, tn),
                        emit=session.emit)
                    cmd_desc = tool_input.get("command", name)
                    output = (f"[Background task {bg_id} started] Command: {cmd_desc}. "
                              "The result will arrive as a <task_notification> when "
                              "complete. Continue with other work meanwhile.")
                    session.emit("tool_result", {"id": block["id"], "name": name,
                                                 "output": output})
                    results.append(_tool_result(block, output))
                    continue

                output = T.call_tool_handler(handlers.get(name), tool_input, name)
                session.emit("tool_result", {
                    "id": block["id"], "name": name,
                    "output": output[:2000] + ("…" if len(output) > 2000 else ""),
                })
                results.append(_tool_result(block, output))

            except Exception as e:  # noqa: BLE001 — tool errors must not break tool_use/result pairing
                output = f"[Tool execution error] {type(e).__name__}: {e}"
                try:
                    session.emit("tool_result", {"id": block["id"], "name": name,
                                                 "output": output, "error": True})
                except Exception:
                    pass
                results.append(_tool_result(block, output))

        # Safety net: ensure every tool_use block has a matching result.
        # Catches edge cases where a block was skipped (e.g. compact break
        # left results behind but compact_history replaced messages — in
        # that case results are stale and harmless to append).
        if not compacted_now:
            seen_ids = {r.get("tool_use_id") for r in results}
            for block in content:
                if (block.get("type") == "tool_use"
                        and block.get("id") not in seen_ids):
                    results.append(_tool_result(
                        block, "[Skipped — no tool_result was produced]"))

        if compacted_now:
            continue

        # s13: Inject completed background task notifications alongside
        # tool results in one user message.
        user_content: list = []
        bg_notifications = session.background.collect_notifications()
        if bg_notifications:
            for notif in bg_notifications:
                user_content.append({"type": "text",
                                     "text": session.background.format_notification(notif)})
                session.emit("background_done", {
                    "bg_id": notif["bg_id"],
                    "command": notif["command"],
                    "summary": notif["summary"][:200],
                })
            session.emit("status", {
                "text": f"{len(bg_notifications)} background task(s) completed."})

        if results or user_content:
            user_content.extend(results)
            messages.append({"role": "user", "content": user_content})
        elif session.interrupted():
            return


def _tool_result(block: dict, output: str) -> dict:
    return {"type": "tool_result", "tool_use_id": block["id"], "content": output}


def _emit_assistant(session, content: list[dict]) -> None:
    text = extract_text(content)
    if text:
        session.emit("assistant", {"text": text})
