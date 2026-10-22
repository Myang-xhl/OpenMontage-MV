---
kind: build_system
name: Python 依赖与 YAML 配置驱动的 MV 流水线构建系统
category: build_system
scope:
    - '**'
source_files:
    - requirements.txt
    - config.yaml
    - pipeline_defs/music-video.yaml
    - lib/pipeline_loader.py
    - lib/config_model.py
    - backlot/__main__.py
    - schemas/pipelines/pipeline_manifest.schema.json
---

本仓库没有传统的 Makefile/Dockerfile/CI 构建脚本，而是采用 **Python 包 + YAML 运行时配置 + JSON Schema 校验** 的轻量构建方式。所有“构建”行为由 Python 模块通过 `python -m` 启动，依赖声明集中在 `requirements.txt`，流水线编排完全由 `pipeline_defs/music-video.yaml` 驱动。

## 1. 使用的系统与工具
- **依赖管理**：`requirements.txt`（pyyaml、pydantic、jsonschema、python-dotenv、requests、fastapi、uvicorn、watchfiles）
- **运行时入口**：`python -m backlot`（CLI 子命令 `open` / `serve` / `studio`），通过 `backlot/__main__.py` 解析参数并调用 uvicorn 启动 FastAPI 服务
- **流水线定义**：YAML 清单 `pipeline_defs/music-video.yaml`，经 `lib/pipeline_loader.py` 加载并用 `schemas/pipelines/pipeline_manifest.schema.json` 做 JSON Schema 校验
- **配置管理**：`config.yaml` 提供 checkpoint/output/paths 等运行时参数，由 `lib/config_model.py` 合并环境变量后以类型化模型暴露

## 2. 关键文件
- `requirements.txt` — 唯一依赖清单
- `config.yaml` — 全局运行时配置（编码、分辨率、路径等）
- `pipeline_defs/music-video.yaml` — 7 阶段 MV 流水线声明（idea→proposal→storyboard→assets→edit→compose→publish）
- `lib/pipeline_loader.py` — 流水线清单加载、缓存、子阶段过滤、扩展能力门控
- `lib/config_model.py` — YAML + 环境变量配置模型
- `backlot/__main__.py` — CLI 入口与服务自启逻辑
- `schemas/pipelines/pipeline_manifest.schema.json` — 流水线清单的 JSON Schema
- `skills/meta/checkpoint-protocol.md` — 检查点协议与审批门控规范

## 3. 架构与约定
- **无编译步骤**：纯 Python 解释执行，无需预编译或打包；部署即复制仓库 + `pip install -r requirements.txt`
- **声明式流水线**：所有阶段顺序、产物、所需工具、检查点策略、人类审批默认值均在 YAML 中声明，代码只负责解析与执行
- **Schema 强制契约**：流水线清单与制品结构均受 JSON Schema 约束，加载时即校验，避免运行时结构错误
- **扩展能力白名单**：`extensions.custom_scripts/playbooks/skills/tools` 必须显式开启才能使用自定义扩展，未开启则抛 `ExtensionNotPermitted`
- **Backlot 作为观察者**：`python -m backlot open` 非阻塞启动本地 Web 看板，失败不影响流水线继续运行

## 4. 约定与约束
- 依赖版本通过 `requirements.txt` 中的 `>=` 下限锁定，无虚拟环境或锁文件约定
- 流水线名称即文件名（不含 `.yaml`），通过 `load_pipeline(name)` 按名查找
- 每个阶段可声明 `checkpoint_required` 与 `human_approval_default`，由 `lib/checkpoint.py` 统一执行门控
- 输出格式、编解码器、分辨率、帧率、CRF 等媒体参数统一来自 `config.yaml` 的 `output.*` 字段
- Backlot 服务默认绑定 `127.0.0.1`，需设置 `BACKLOT_HOST=0.0.0.0` 才对外暴露；端口通过 `BACKLOT_PORT` 覆盖

由于仓库不包含 Dockerfile、Makefile、CI 配置文件或打包脚本，该构建系统仅覆盖 Python 依赖安装与 YAML 驱动的运行时编排，属于低侵入、配置中心的轻量方案。