"""ASS subtitle (lyrics) parser for the music-video pipeline.

Deterministic implementation of mv-storyboard SKILL.md Step 1
(.agents/skills/mv-storyboard/SKILL.md — 读取与解析ASS文件):
encoding detection (UTF-8 → GBK fallback), [Events] Dialogue extraction,
karaoke/override tag stripping, singer-role mapping from Style, and
H:MM:SS.cs → seconds conversion (centisecond precision preserved).

Step 2 onwards (section detection, style/emotion analysis) stays with the
Agent — this tool only supplies the parsed lyric lines plus the timing
gaps the Agent needs for the three-signal section analysis.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

# SKILL.md 1.2 — Dialogue line field extraction (10 groups).
DIALOGUE_RE = re.compile(
    r"^Dialogue:\s*(\d+),([^,]+),([^,]+),([^,]+),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),(.*)$"
)
# SKILL.md 1.3 — karaoke tags {\K28}/{\k28}, then any other override tags.
KARAOKE_TAG_RE = re.compile(r"\{\\[Kk]\d+\}")
OVERRIDE_TAG_RE = re.compile(r"\{[^}]*\}")
# CJK presence check used by the encoding-garble heuristic (SKILL.md 1.1).
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CONTROL_CHAR_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]")


def _read_ass_text(path: Path) -> tuple[str, str]:
    """Read ASS content with UTF-8 first, falling back to GBK on garble.

    Returns (text, encoding_used). Garble signals per SKILL.md 1.1:
    replacement chars (\ufffd), unexpected control chars, or a file that
    contains no CJK at all (Chinese Style names garbled away).
    """
    raw = path.read_bytes()
    # Strip UTF-8 BOM if present — common in ASS exports.
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"

    text = raw.decode("utf-8", errors="replace")
    garbled = (
        "\ufffd" in text
        or CONTROL_CHAR_RE.search(text) is not None
        or CJK_RE.search(text) is None
    )
    if garbled:
        try:
            return raw.decode("gbk"), "gbk"
        except (UnicodeDecodeError, LookupError):
            pass  # keep the UTF-8 (replaced) text rather than fail hard
    return text, "utf-8"


def parse_ass_time(time_str: str) -> float:
    """Convert H:MM:SS.cs to seconds, preserving centisecond precision."""
    parts = time_str.strip().split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return round(hours * 3600 + minutes * 60 + seconds, 2)


def map_singer(style: str) -> str:
    """Map ASS Style name to singer role (SKILL.md 1.4)."""
    if "男" in style:
        return "男"
    if "女" in style:
        return "女"
    if "合" in style:
        return "合"
    if "配唱" in style or "一词" in style:
        return "配唱"
    return "Default"


def strip_tags(text: str) -> str:
    """Strip karaoke tags then remaining override tags; keep lyric text intact."""
    text = KARAOKE_TAG_RE.sub("", text)
    text = OVERRIDE_TAG_RE.sub("", text)
    # ASS hard line breaks / hard spaces inside lyric text.
    return text.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ").strip()


class AssParser(BaseTool):
    name = "ass_parser"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies: list[str] = []
    install_instructions = ""

    capabilities = ["parse_ass_lyrics", "karaoke_tag_strip", "singer_role_mapping"]
    best_for = [
        "parsing ASS karaoke lyric files for the music-video pipeline",
        "extracting timed lyric lines with singer roles for storyboard planning",
        "computing lyric timing gaps for song-section analysis",
    ]
    not_good_for = [
        "general subtitle format conversion (use subtitle tools)",
        "semantic song-section / emotion analysis (Agent cognitive task)",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the .ass lyric file",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=64, vram_mb=0, disk_mb=0, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=0, retryable_errors=[])
    idempotency_key_fields = ["input_path"]
    side_effects: list[str] = []

    agent_skills = ["mv-storyboard"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"File not found: {input_path}")

        start = time.time()

        try:
            text, encoding_used = _read_ass_text(input_path)
        except OSError as exc:
            return ToolResult(success=False, error=f"Failed to read file: {exc}")

        # SKILL.md 1.2 — only the [Events] section matters.
        in_events = False
        lines: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("["):
                in_events = stripped.lower() == "[events]"
                continue
            if not in_events:
                continue
            match = DIALOGUE_RE.match(stripped)
            if not match:
                continue
            raw_text = match.group(10)
            lyric = strip_tags(raw_text)
            if not lyric:
                continue
            try:
                start_s = parse_ass_time(match.group(2))
                end_s = parse_ass_time(match.group(3))
            except (ValueError, IndexError):
                continue  # malformed timestamp — skip the line, don't fail the file
            lines.append({
                "start": start_s,
                "end": end_s,
                "singer": map_singer(match.group(4)),
                "style": match.group(4),
                "text": lyric,
                "raw": raw_text,
            })

        if not lines:
            return ToolResult(
                success=False,
                error=(
                    f"No Dialogue lyric lines found in [Events] of {input_path} "
                    f"(decoded as {encoding_used})"
                ),
            )

        lines.sort(key=lambda l: (l["start"], l["end"]))
        total_duration = lines[-1]["end"]

        # Timing gaps feed the Agent's three-signal section analysis
        # (SKILL.md Step 2.1): intro before first line, >3s interludes,
        # outro after the last line (unknowable from lyrics alone → intro only).
        gaps: list[dict[str, Any]] = []
        if lines[0]["start"] > 0:
            gaps.append({
                "after_line": None,
                "start": 0.0,
                "end": lines[0]["start"],
                "duration": round(lines[0]["start"], 2),
                "kind": "intro",
            })
        for i in range(len(lines) - 1):
            gap = round(lines[i + 1]["start"] - lines[i]["end"], 2)
            if gap > 3:
                gaps.append({
                    "after_line": i,
                    "start": lines[i]["end"],
                    "end": lines[i + 1]["start"],
                    "duration": gap,
                    "kind": "interlude",
                })

        return ToolResult(
            success=True,
            data={
                "file": str(input_path),
                "encoding": encoding_used,
                "line_count": len(lines),
                "lines": lines,
                "total_duration": total_duration,
                "singers": sorted({l["singer"] for l in lines}),
                "gaps": gaps,
            },
            duration_seconds=round(time.time() - start, 2),
        )
