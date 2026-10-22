---
kind: error_handling
name: 错误处理体系：分层异常、SSE 事件与检查点门控
category: error_handling
scope:
    - '**'
source_files:
    - backlot/server.py
    - backlot/agent/harness.py
    - backlot/__main__.py
    - lib/events.py
    - lib/checkpoint.py
    - tools/base_tool.py
---

本仓库的错误处理采用“分层异常 + 可观测事件 + 检查点门控”的复合策略，覆盖 CLI/服务器层、Agent 循环层、工具执行层与流水线状态层。

1. 系统与方法
- FastAPI HTTP 层：通过 fastapi.HTTPException 返回标准 HTTP 状态码（400/403/404/409），在 backlot/server.py 中集中用于会话不存在、路径越界、媒体缺失等场景。
- Agent 循环层：定义领域异常 ModelError（继承自 RuntimeError）表示模型不可用；配合 with_retry 实现 429/529 退避重试、连续 529 切换备用模型、max_tokens 升级与上下文压缩（reactive compact）。
- 工具执行层：tools/base_tool.py 提供 DependencyError、ToolCommandError（封装 subprocess.CalledProcessError）以及统一的 ToolResult(success, error, cost_usd, ...) 结构；所有 execute() 被 _instrument_execute 自动包装，失败时向 lib/events.py 写入 event: error 条目，且事件层本身永不抛错（“Observability must never break production”）。
- 流水线状态层：lib/checkpoint.py 定义 CheckpointValidationError(ValueError)，在写入检查点时校验阶段、状态、制品 schema 与人工审批门控（GATE VIOLATION），失败直接抛出以阻止非法状态持久化。

2. 关键文件与包
- backlot/server.py — FastAPI 路由与 HTTP 异常映射、SSE 心跳、路径安全校验。
- backlot/agent/harness.py — ModelError、RecoveryState、with_retry、上下文压缩与 max_tokens 升级。
- backlot/__main__.py — CLI 入口，对子进程启动/浏览器打开等调用做 try/except 兜底，保证非致命性。
- lib/events.py — 项目级 append-only 事件日志（events.jsonl），读写均吞掉异常，确保零副作用。
- lib/checkpoint.py — 检查点读写、schema 校验、人工审批门控与历史归档。
- tools/base_tool.py — 工具基类、统一结果结构、依赖检查、命令执行异常封装与事件埋点装饰器。

3. 架构与约定
- 异常分类清晰：HTTP 层用 HTTPException，Agent 层用 ModelError，工具层用 DependencyError/ToolCommandError，状态层用 CheckpointValidationError，各层职责不交叉。
- 可观测优先：工具执行通过装饰器自动记录 start/error/finish 三态事件，事件写入失败静默丢弃，不影响主流程。
- 恢复策略内聚：with_retry 集中处理速率限制与过载，结合 RecoveryState 跟踪是否已升级 tokens、是否已尝试 reactive compact，避免无限重试。
- 门控即错误：检查点写入时对 awaiting_human → completed 的跳过视为硬错误（GATE VIOLATION），强制人类审批链路不被绕过。

4. 约定与约束
- 事件层“永不失败”：emit_event/read_events 内部 try/except 包裹所有 I/O，任何异常都被吞掉，保证观察能力不会破坏生产。
- CLI 非致命设计：open 命令即使无法启动服务器或打开浏览器也仅打印提示并返回非零码，不中断管线。
- SSE 心跳与队列限流：SSE 连接每 15 秒发送一次 heartbeat；ChangeHub 队列满时丢弃多余通知，防止背压。
- 路径安全：所有 /media、/thumb 路由先校验目标路径是否在 PROJECTS_DIR 下，越界直接 403。
- 检查点原子写：先写 .json.tmp 再 os.replace，并对已存在的完成态检查点归档至 history/，保证幂等与可审计。
- 工具依赖声明式：通过 dependencies 列表声明 cmd/env/python 依赖，check_dependencies 失败抛出 DependencyError，由上层决定降级或报错。