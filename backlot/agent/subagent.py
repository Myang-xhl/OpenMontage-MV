"""Subagent — context-isolated sub-task execution.

Ported from learn-claude-code s06. The ``task`` tool spawns a subagent with a
fresh ``messages[]`` list, its own tool loop (bash/read/write/edit/glob/grep/
load_skill — but NO ``task``, preventing recursion), and a 30-turn safety
limit. Only the final text summary is returned to the parent agent; all
intermediate tool results are discarded, keeping the parent's context clean.

Typical use: delegate "generate shot_05 video clip and verify it matches
the storyboard" — the subagent calls yinghe_video (via bash + registry),
checks the output, and returns a one-line summary, without polluting the
parent's context with hundreds of lines of API polling output.

Design decisions (from s06):
- Fresh messages[]: intermediate tool results stay in the subagent's scope.
- No ``task`` tool: prevents recursive subagent spawning.
- Safety limit: 30 turns per subagent.
- File system side-effects (generated videos, written files) persist —
  only the conversation history is discarded.
- Subagent tool calls are emitted to the session for UI visibility.
"""

from __future__ import annotations

SUB_MAX_TURNS = 30

# Subagent tools: file/shell + skill loading, but NO pipeline-control tools
# (init_project, write_checkpoint, todo_write stay with the parent), NO
# compact (the subagent's context is bounded by 30 turns), and NO task
# (prevents recursion).
_SUB_TOOL_NAMES = [
    "bash", "read_file", "write_file", "edit_file",
    "glob", "grep", "load_skill", "list_skills",
]

_SUB_SYSTEM_PROMPT = """You are an OpenMontage subagent — a focused worker spawned for a single \
sub-task. You have the same file and shell tools as the main agent, plus skill loading, but you CANNOT spawn further subagents (no `task` tool).

Rules:
- Complete the specific task you were given, then return a concise summary.
- Do not delegate further.
- All file outputs go under projects/<project-id>/ as usual.
- Communicate in the user's language."""


def spawn_subagent(session, description: str) -> str:
    """Spawn a subagent with fresh messages[], return summary only.

    The subagent reuses the parent session's model client and tool handlers
    (so it respects the same safe_path sandbox and interrupt signals), but
    gets its own isolated message list and a restricted tool set.
    """
    # Lazy imports to avoid circular dependency (harness <-> subagent).
    from backlot.agent import tools as T
    from backlot.agent.harness import (
        make_client, normalize_content, has_tool_use, extract_text,
    )

    client, model, _fallback = make_client()

    # Build a restricted tool pool from the parent's definitions.
    sub_tools = [t for t in T.TOOL_DEFINITIONS if t["name"] in _SUB_TOOL_NAMES]
    base_handlers = T.build_handlers(session)
    sub_handlers = {name: base_handlers[name]
                    for name in _SUB_TOOL_NAMES if name in base_handlers}

    session.emit("subagent_start", {"description": description[:300]})

    messages: list[dict] = [{"role": "user", "content": description}]

    for _ in range(SUB_MAX_TURNS):
        if session.interrupted():
            break

        try:
            response = client.messages.create(
                model=model,
                system=_SUB_SYSTEM_PROMPT,
                messages=messages,
                tools=sub_tools,
                max_tokens=8000,
            )
        except Exception as e:  # noqa: BLE001 — subagent errors are recoverable
            summary = f"Subagent error: {type(e).__name__}: {e}"
            session.emit("subagent_done", {"summary": summary[:500]})
            return summary

        content = normalize_content(response.content)
        messages.append({"role": "assistant", "content": content})

        # Emit subagent tool calls to the session for UI visibility.
        for block in content:
            if block.get("type") == "tool_use":
                session.emit("subagent_tool_call", {
                    "name": block["name"],
                    "input_summary": str(block.get("input") or "")[:200],
                })

        if not has_tool_use(content):
            break

        results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if session.interrupted():
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "[Interrupted by user before execution]",
                })
                continue
            try:
                name = block["name"]
                tool_input = block.get("input") or {}
                handler = sub_handlers.get(name)
                output = T.call_tool_handler(handler, tool_input, name)
                session.emit("subagent_tool_result", {
                    "name": name,
                    "output_summary": output[:200],
                })
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": output,
                })
            except Exception as e:  # noqa: BLE001 — must not break tool_use/result pairing
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": f"[Tool execution error] {type(e).__name__}: {e}",
                })
        messages.append({"role": "user", "content": results})
    # else: safety limit hit — fall through to extract whatever text we can.

    # Extract the final text answer (subagent's last message may be a
    # tool_result if the safety limit was hit mid-tool).
    result = extract_text(messages[-1].get("content", [])) if messages else ""
    if not result:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                result = extract_text(msg.get("content", []))
                if result:
                    break
        if not result:
            result = ("Subagent reached its 30-turn limit without a final "
                      "answer. Check the generated files directly.")

    session.emit("subagent_done", {"summary": result[:500]})
    return result
