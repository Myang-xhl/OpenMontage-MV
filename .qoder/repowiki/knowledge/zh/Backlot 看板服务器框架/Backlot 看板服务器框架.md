---
kind: external_dependency
name: Backlot 看板服务器框架
slug: fastapi-uvicorn
category: external_dependency
category_hints:
    - framework_behavior
scope:
    - '**'
source_files:
    - backlot/server.py
    - requirements.txt
---

### 项目看板和服务框架
- **角色**: Backlot 看板服务器的后端框架，提供 REST API 和 SSE 实时通信
- **技术栈**: FastAPI 作为 Web 框架，Uvicorn 作为 ASGI 服务器
- **核心功能**: 项目状态管理、SSE 事件推送、媒体文件服务、会话管理
- **实时通信**: 基于 Server-Sent Events 实现项目变更的实时通知
- **文件监控**: 使用 watchfiles 监听 projects/ 目录变化
- **静态资源**: 提供 UI 界面和媒体文件的 HTTP 服务
- **健康检查**: `/api/health` 端点用于服务状态监控