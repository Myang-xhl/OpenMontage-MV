"""MV Frontend Bridge — REST endpoints for the MVAgent-Frontend Vue app.

Adapts the frontend's expected API shape to the agent session mechanism:
upload an ASS file → create project + agent session → poll for storyboard,
shots, and final video. The agent runs the full music-video pipeline
autonomously; these endpoints are read-only queries on the project state.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backlot.agent.sessions import SessionBusyError, manager as session_manager
from lib.checkpoint import init_project
from lib.paths import PROJECTS_DIR

router = APIRouter(prefix="/api/mv", tags=["mv-bridge"])

_PIPELINE_STAGES = ["idea", "proposal", "storyboard", "assets", "edit", "compose", "publish"]
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_project_dir(project_id: str) -> Path:
    """Validate project id and return its directory, or raise 404."""
    if any(c in project_id for c in "/\\:") or project_id in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid project id")
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    return project_dir


def _kebab_case(text: str) -> str:
    """Sanitize text to a kebab-case project id."""
    text = text.strip()
    # Replace runs of non-word chars (keep CJK) with hyphens
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text, flags=re.UNICODE)
    text = text.strip("-").lower()
    text = re.sub(r"-+", "-", text)
    return text or "mv-project"


def _get_video_duration(path: Path) -> float:
    """Get video duration in seconds via ffprobe (0.0 on failure)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def _parse_character_ids(character_field: str) -> list[str]:
    """Parse the storyboard shot 'character' field into a list of IDs.

    Empty shots ("无") → []; single character → [id]; double → [id1, id2].
    """
    if not character_field or character_field.strip() == "无":
        return []
    parts = re.split(r"[,，+和]|&", character_field.strip())
    return [p.strip() for p in parts if p.strip() and p.strip() != "无"]


def _read_checkpoint_status(project_dir: Path, stage: str) -> str:
    """Read a checkpoint's status field (pending if missing)."""
    cp_path = project_dir / f"checkpoint_{stage}.json"
    if not cp_path.is_file():
        return "pending"
    try:
        with open(cp_path, encoding="utf-8") as f:
            cp = json.load(f)
        return cp.get("status", "pending")
    except (json.JSONDecodeError, OSError):
        return "pending"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload(
    assFile: UploadFile = File(...),
    songId: str = Form(""),
    extraRequirement: str = Form(""),
    characterImages: list[UploadFile] = File(default=[]),
) -> dict:
    """Upload an ASS file and start the MV production pipeline.

    Creates a project directory, saves the ASS file and optional character
    reference images, then creates an agent session and posts a message
    instructing the agent to run the music-video pipeline.
    """
    # 1. Generate unique project ID from songId or ASS filename
    ass_name = assFile.filename or "song.ass"
    ass_stem = Path(ass_name).stem
    raw_id = songId.strip() if songId.strip() else ass_stem
    project_id = _kebab_case(raw_id)
    base_id = project_id
    counter = 1
    while (PROJECTS_DIR / project_id).is_dir():
        project_id = f"{base_id}-{counter}"
        counter += 1

    # 2. Initialize project directory (creates artifacts/ assets/ renders/ etc.)
    project_dir = init_project(
        project_id, title=songId.strip() or ass_stem,
        pipeline_type="music-video",
    )

    # 3. Save ASS file
    ass_path = project_dir / "song.ass"
    content = await assFile.read()
    ass_path.write_bytes(content)

    # 4. Save character reference images
    char_ref_dir = project_dir / "assets" / "character_refs"
    char_ref_dir.mkdir(parents=True, exist_ok=True)
    for img in characterImages:
        if img.filename:
            safe_name = re.sub(r"[^\w.\-]", "_", img.filename)
            img_content = await img.read()
            (char_ref_dir / safe_name).write_bytes(img_content)

    # 5. Create agent session
    session = session_manager.create("auto")

    # 6. Construct agent message
    rel_ass = f"projects/{project_id}/song.ass"
    message_parts = [
        "用户通过 MV 前端上传了 ASS 歌词文件，请按照 AGENT_GUIDE.md 运行 music-video 流水线。",
        f"项目 ID: {project_id}",
        f"ASS 文件: {rel_ass}",
    ]
    if songId.strip():
        message_parts.append(f"歌曲编号: {songId.strip()}")
    if extraRequirement.strip():
        message_parts.append(f"额外要求: {extraRequirement.strip()}")
    if characterImages:
        message_parts.append(
            f"角色参考图目录: projects/{project_id}/assets/character_refs/ "
            f"请在 proposal 阶段的角色匹配中使用这些参考图。"
        )
    message_parts.append(
        "请先执行预检（确认 yinghe_video 可用、ffmpeg 可用），然后逐阶段执行流水线。"
    )
    message_text = "\n".join(message_parts)

    # 7. Post message to agent (starts the agent thread in background)
    try:
        await asyncio.to_thread(session.post_message, message_text)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "sessionId": session.id,
        "projectId": project_id,
        "status": "running",
    }


@router.get("/project/{project_id}/storyboard")
async def get_storyboard(project_id: str) -> dict:
    """Get the storyboard in frontend MagicScript format.

    Returns 404 with {"status": "not_ready"} if the storyboard hasn't
    been generated yet.
    """
    project_dir = _safe_project_dir(project_id)
    storyboard_path = project_dir / "artifacts" / "storyboard.json"
    if not storyboard_path.is_file():
        raise HTTPException(status_code=404, detail={"status": "not_ready"})

    try:
        with open(storyboard_path, encoding="utf-8") as f:
            storyboard = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"storyboard parse error: {exc}")

    # Convert to frontend MagicScript format
    characters = storyboard.get("characters", [])
    cast = [c.get("id", "") for c in characters if c.get("id")]

    # Build character info for frontend DigitalHuman creation
    char_ref_dir = project_dir / "assets" / "character_refs"
    char_ref_images: list[str] = []
    if char_ref_dir.is_dir():
        for f in sorted(char_ref_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS:
                char_ref_images.append(
                    f"/media/{project_id}/assets/character_refs/{f.name}"
                )

    char_infos = []
    for c in characters:
        cid = c.get("id", "")
        # Try to match a reference image by checking if the character id
        # appears in any image filename
        avatar = ""
        for img_url in char_ref_images:
            img_name = img_url.rsplit("/", 1)[-1]
            if cid and cid.lower() in img_name.lower():
                avatar = img_url
                break
        char_infos.append({
            "id": cid,
            "name": c.get("role", cid),
            "description": c.get("description", ""),
            "style": c.get("style", ""),
            "avatar": avatar,
        })

    # Convert shots to frontend lines
    lines = []
    for shot in storyboard.get("shots", []):
        char_field = shot.get("character", "")
        lines.append({
            "lyrics": shot.get("lyrics", ""),
            "lyricsZh": None,
            "scenePrompt": shot.get("sceneDescription", ""),
            "shotPrompt": shot.get("seedancePrompt", ""),
            "digitalHumanIds": _parse_character_ids(char_field),
            "duration": shot.get("duration", 5),
            "shotNumber": shot.get("shotNumber", 0),
        })

    return {
        "cast": cast,
        "characters": char_infos,
        "lines": lines,
        "characterRefs": char_ref_images,
    }


@router.get("/project/{project_id}/shots")
async def get_shots(project_id: str) -> list:
    """Get generated shot video clips."""
    project_dir = _safe_project_dir(project_id)
    video_dir = project_dir / "assets" / "video"
    if not video_dir.is_dir():
        return []

    shots = []
    for f in sorted(video_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _VIDEO_EXTS:
            continue
        match = re.match(r"shot_(\d+)", f.stem)
        shot_number = int(match.group(1)) if match else 0
        duration = _get_video_duration(f)
        shots.append({
            "shotNumber": shot_number,
            "videoUrl": f"/media/{project_id}/assets/video/{f.name}",
            "coverUrl": f"/thumb/{project_id}/assets/video/{f.name}",
            "duration": duration,
        })

    return shots


@router.get("/project/{project_id}/progress")
async def get_progress(project_id: str) -> dict:
    """Get pipeline stage progress."""
    project_dir = _safe_project_dir(project_id)

    stages = []
    current_stage = None
    for stage in _PIPELINE_STAGES:
        status = _read_checkpoint_status(project_dir, stage)
        stages.append({"name": stage, "status": status})
        if status in ("in_progress", "awaiting_human") and current_stage is None:
            current_stage = stage

    final_path = project_dir / "renders" / "final.mp4"
    final_ready = final_path.is_file()

    if current_stage is None and final_ready:
        current_stage = "done"

    return {
        "stages": stages,
        "currentStage": current_stage,
        "finalReady": final_ready,
    }
