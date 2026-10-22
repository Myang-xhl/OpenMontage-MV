---
kind: external_dependency
name: FFmpeg - 音视频处理核心工具
slug: ffmpeg
category: external_dependency
category_hints:
    - client_constraint
scope:
    - '**'
source_files:
    - tools/video/video_stitch.py
    - tools/audio/audio_mixer.py
    - backlot/server.py
---

### 本地音视频处理引擎
- **角色**: 项目核心的本地音视频处理工具，用于剪辑、混音、字幕烧录等
- **集成点**: `video_stitch`、`audio_mixer`、`color_grade` 工具都依赖 FFmpeg
- **必需功能**: 视频拼接、ASS 字幕烧录、音频混合、缩略图生成
- **环境要求**: 必须在系统 PATH 中可用，否则所有视频处理步骤失败
- **Backlot 集成**: 服务器端使用 FFmpeg 生成视频缩略图和海报帧
- **关键命令**: 包括 `-ss` 时间戳定位、`-vf` 视频滤镜、`-af` 音频滤镜等
- **错误处理**: 所有 FFmpeg 调用都有超时和错误码检查机制