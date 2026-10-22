"""Yinghe (api-aigc.fzyinghe.com) async video generation.

Task-based API: create a video generation task, then poll until
SUCCESS/FAILED/CANCELLED, and download the resulting clip. Supports
text-to-video and image-to-video via reference image URLs, with the
model configured through VIDEO_MODEL (default doubao-seedance-2.0).

API summary:
    - Create task: POST /video/generation/tasks   (header: Authorization: Bearer)
    - Query task:  GET  /video/generation/tasks/{taskId}
"""

from __future__ import annotations

import os
import time
import uuid
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

DEFAULT_BASE_URL = "https://api-aigc.fzyinghe.com"
POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 600


class YingheVideo(BaseTool):
    name = "yinghe_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "yinghe"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:VIDEO_API_KEY"]
    install_instructions = (
        "Set VIDEO_API_KEY to your api-aigc.fzyinghe.com API key in .env.\n"
        "  Optional: VIDEO_API_BASE_URL (default https://api-aigc.fzyinghe.com),\n"
        "  VIDEO_MODEL (default doubao-seedance-2.0)"
    )
    agent_skills = ["ai-video-gen", "seedance-2-0"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "native_audio": True,
        "aspect_ratio": True,
        "duration_control": True,
    }
    best_for = [
        "seedance-2.0 clips with synthesized audio via aggregator API",
        "reference-image conditioned generation (first/last frame)",
    ]
    not_good_for = [
        "offline generation",
        "local reference images (must be public URLs)",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "duration": {
                "type": "integer",
                "default": 5,
                "description": "Clip duration in seconds",
            },
            "ratio": {
                "type": "string",
                "default": "16:9",
                "description": "Aspect ratio, e.g. 16:9 / 9:16 / 1:1",
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reference image URLs (must be publicly reachable)",
            },
            "generate_audio": {"type": "boolean", "default": True},
            "watermark": {"type": "boolean", "default": False},
            "model": {"type": "string", "description": "Override VIDEO_MODEL"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "operation", "duration", "ratio", "model"]
    side_effects = ["writes video file to output_path", "calls fzyinghe video API"]
    user_visible_verification = ["Watch generated clip for motion coherence and prompt adherence"]

    @staticmethod
    def _config() -> tuple[str, str | None, str]:
        base_url = os.environ.get("VIDEO_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        api_key = os.environ.get("VIDEO_API_KEY")
        model = os.environ.get("VIDEO_MODEL", "doubao-seedance-2.0")
        return base_url, api_key, model

    def get_status(self) -> ToolStatus:
        if self._config()[1]:
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # The aggregator does not publish per-clip pricing; report 0 and let
        # the account dashboard be the source of truth.
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 180.0

    @staticmethod
    def _build_content(prompt: str, image_urls: list[str] | None) -> list[dict[str, Any]]:
        """Build the request content array: text + optional reference images."""
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in image_urls or []:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url},
                    "role": "reference_image",
                }
            )
        return content

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        base_url, api_key, model = self._config()
        if not api_key:
            return ToolResult(
                success=False,
                error="VIDEO_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        model = inputs.get("model") or model
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Idempotency key: avoids duplicate billing on network retries.
            "Idempotency-Key": str(uuid.uuid4()),
        }
        payload = {
            "model": model,
            "content": self._build_content(inputs["prompt"], inputs.get("image_urls")),
            "generate_audio": bool(inputs.get("generate_audio", True)),
            "ratio": inputs.get("ratio", "16:9"),
            "duration": int(inputs.get("duration", 5)),
            "watermark": bool(inputs.get("watermark", False)),
        }

        # 1. Create the async task.
        try:
            resp = requests.post(
                f"{base_url}/video/generation/tasks",
                headers=headers,
                json=payload,
                timeout=30,
            )
            result = resp.json()
        except Exception as e:
            return ToolResult(success=False, error=f"Yinghe video task creation failed: {e}")

        if result.get("code") != 200:
            return ToolResult(
                success=False,
                error=f"Yinghe video task rejected: {result.get('msg', 'unknown')} ({result.get('data')})",
            )
        task_id = (result.get("data") or {}).get("taskId")
        if not task_id:
            return ToolResult(success=False, error=f"Yinghe response missing taskId: {result}")

        # 2. Poll until the task reaches a terminal state.
        query_url = f"{base_url}/video/generation/tasks/{task_id}"
        deadline = time.time() + MAX_WAIT_SECONDS
        video_url: str | None = None
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                q = requests.get(query_url, headers=headers, timeout=30)
                data = (q.json() or {}).get("data") or {}
            except Exception:
                continue  # transient poll failure — keep waiting
            status = str(data.get("status", "")).upper()
            if status == "SUCCESS":
                video_url = data.get("resultUrl")
                if not video_url:
                    return ToolResult(
                        success=False,
                        error=f"Yinghe task {task_id} succeeded but returned no video URL",
                    )
                break
            if status in {"FAILED", "CANCELLED"}:
                reason = data.get("failReason") or status
                return ToolResult(
                    success=False,
                    error=f"Yinghe video task {task_id} {status}: {reason}",
                )
        else:
            return ToolResult(
                success=False,
                error=(
                    f"Yinghe video task {task_id} timed out after {MAX_WAIT_SECONDS}s; "
                    f"query later with taskId"
                ),
            )

        # 3. Download the clip to disk (media artifacts must live on disk).
        output_path = Path(inputs.get("output_path", "yinghe_video.mp4"))
        if not output_path.suffix:
            output_path = output_path.with_suffix(".mp4")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(video_url, stream=True, timeout=300) as download:
                download.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in download.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
        except Exception as e:
            return ToolResult(success=False, error=f"Yinghe video download failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "yinghe",
                "model": model,
                "prompt": inputs["prompt"],
                "task_id": task_id,
                "output": str(output_path),
                "source_url": video_url,
                "duration": payload["duration"],
                "ratio": payload["ratio"],
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
