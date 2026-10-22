---
kind: external_dependency
name: Yinghe Video - 唯一视频生成 Provider
slug: yinghe-video
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
source_files:
    - tools/video/yinghe_video.py
    - .env
---

### 项目唯一的视频生成服务
- **角色**: OpenMontage-MV 项目中唯一的视频生成 provider，无备选方案
- **集成点**: `tools/video/yinghe_video.py` 通过 ToolRegistry 注册为 `yinghe_video`
- **认证方式**: 通过 `VIDEO_API_KEY` 环境变量配置 Bearer Token 认证
- **API 端点**: `https://api-aigc.fzyinghe.com/video/generation/tasks` (异步任务模式)
- **使用模型**: 默认 `doubao-seedance-2.0`，可通过 `VIDEO_MODEL` 环境变量覆盖
- **依赖要求**: 必须设置 `VIDEO_API_KEY`，否则预检失败并阻止生产流程
- **错误处理**: 任务状态轮询机制，支持 SUCCESS/FAILED/CANCELLED 三种终态
- **限制**: 不支持离线生成，参考图片必须是公网可访问的 URL