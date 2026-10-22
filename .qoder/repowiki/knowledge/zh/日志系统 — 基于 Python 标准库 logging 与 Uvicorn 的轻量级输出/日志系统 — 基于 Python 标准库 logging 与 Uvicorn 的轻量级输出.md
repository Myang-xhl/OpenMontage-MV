---
kind: logging_system
name: 日志系统 — 基于 Python 标准库 logging 与 Uvicorn 的轻量级输出
category: logging_system
scope:
    - '**'
source_files:
    - lib/checkpoint.py
    - backlot/__main__.py
---

本仓库未引入第三方日志框架（如 loguru、structlog），而是采用 Python 标准库 `logging` 模块进行局部警告输出，并通过 Uvicorn 的内置日志能力处理 Web 服务日志。整体属于“无集中式日志配置”的轻量实现。

1. 使用的系统与工具
- 标准库 logging：仅在 `lib/checkpoint.py` 中通过 `import logging; logging.getLogger(__name__).warning(...)` 输出关键路径异常与回退信息。
- Uvicorn 日志：在 `backlot/__main__.py` 中以 `uvicorn.run(..., log_level="info")` 启动 FastAPI 服务，所有 HTTP 请求与服务器事件由 Uvicorn 控制台日志记录。
- 自定义文件日志：`backlot/__main__.py` 中的 `_open_log_file()` 将 Backlot 子进程的标准输出/错误追加到 `.studio/server.log`，并在超过 5MB 时滚动为 `.log.1`。

2. 关键文件与位置
- `lib/checkpoint.py`：使用 `logging.getLogger(__name__).warning(...)` 记录检查点归档失败、门策略不可用等警告。
- `backlot/__main__.py`：定义 `LOG_PATH = Path(...)/".studio/server.log"`，负责日志文件打开、大小判断与滚动；同时通过 `uvicorn.run(..., log_level="info")` 设置服务日志级别。
- `pipeline_defs/music-video.yaml`：仅引用 `decision_log` 字段名，不涉及日志框架配置。

3. 架构与约定
- 无全局 logger 初始化：各模块按需 `import logging` 并直接调用 `getLogger(__name__)`，未统一设置 handler、formatter 或 level。
- 日志级别策略：Uvicorn 固定为 `info`；checkpoint 模块仅输出 `warning` 级别的降级/异常提示，不输出 debug/info 常规流程。
- 输出目标：Web 服务日志走 Uvicorn 控制台；Backlot CLI 子进程的 stdout/stderr 被重定向到 `.studio/server.log` 文件，形成单一可追踪的服务日志。
- 结构化程度：checkpoint 警告为纯文本字符串，未使用结构化字段；决策日志（decision_log）是业务产物而非运行日志。

4. 约定与约束
- checkpoint 模块的 warning 调用均为“降级回退”场景（缺少 pipeline_type、manifest 加载失败、历史归档 I/O 异常），属于容错性日志，非主流程输出。
- Backlot 服务日志级别硬编码为 `info`，未提供环境变量覆盖；如需调整需修改源码。
- 日志文件滚动阈值固定为 5MB，超过后以 `.log.1` 命名覆盖旧文件，未实现多份轮转或保留策略。
- 未发现统一的日志收集、聚合或远程发送机制；日志仅落盘于本地 `.studio/server.log`。