---
kind: configuration_system
name: OpenMontage-MV 配置系统：YAML + Pydantic 模型与环境变量覆盖
category: configuration_system
scope:
    - '**'
source_files:
    - config.yaml
    - lib/config_model.py
    - lib/env_loader.py
    - lib/paths.py
    - pipeline_defs/music-video.yaml
---

## 1. 使用的系统与框架
- **配置文件格式**：YAML（`config.yaml`、`pipeline_defs/music-video.yaml`）
- **配置模型**：Pydantic `BaseModel`，提供类型校验与默认值
- **环境变量加载**：`python-dotenv` 的 `load_dotenv`，从 `.env` 文件注入
- **路径解析**：`pathlib.Path` 配合单一仓库根常量 `REPO_ROOT`

## 2. 核心文件与包
- `config.yaml` — 运行时配置入口（checkpoint、output、paths 三段）
- `lib/config_model.py` — Pydantic 配置模型与 `OpenMontageConfig.load()` 加载器
- `lib/env_loader.py` — `.env` 加载与 `get_env` / `require_env` 工具
- `lib/paths.py` — 仓库根与 `PROJECTS_DIR`（可通过 `OPENMONTAGE_PROJECTS_DIR` 覆盖）
- `pipeline_defs/music-video.yaml` — 音乐视频流水线清单（阶段、技能、检查点策略等）

## 3. 架构与约定
- **分层加载顺序**：`OpenMontageConfig.load()` 先读取 `config.yaml`，通过 `model_validate` 转为强类型对象；缺失时回退到 Pydantic 默认值。
- **环境变量覆盖**：`env_loader` 在应用启动时调用 `load_dotenv(project_root)` 加载 `.env`；`paths.py` 中 `PROJECTS_DIR` 通过 `os.environ.get("OPENMONTAGE_PROJECTS_DIR")` 覆盖默认 `projects` 目录。
- **路径解析约定**：`resolve_path(key, project_root)` 以 `project_root` 为基准拼接 `paths.*` 中的相对路径，保证所有子模块对同一仓库根的一致性。
- **流水线配置即代码**：`music-video.yaml` 用声明式 YAML 描述 stage → skill → artifacts → tools → checkpoint_policy 的完整编排，被 `schemas/pipelines/pipeline_manifest.schema.json` 约束。

## 4. 约定与约束
- **配置文件位置**：默认位于仓库根 `config.yaml`，可通过 `OpenMontageConfig.load(config_path=...)` 指定其他路径。
- **必填环境变量**：`require_env(key)` 在未设置时报 `EnvironmentError`，用于强制外部依赖（如 API Key）存在。
- **项目根可覆盖**：`OPENMONTAGE_PROJECTS_DIR` 环境变量可重定向所有 checkpoint、事件与 Backlot 看板指向的根目录，便于 staging/test。
- **流水线清单必须通过 Schema 校验**：`pipeline_manifest.schema.json` 定义了 stages、required_skills、default_checkpoint_policy 等字段的约束，违反则加载失败。
- **Checkpoint 策略枚举**：`CheckpointPolicy` 限定为 `guided` / `manual_all` / `auto_noncreative`，不允许任意字符串。
- **输出参数集中管理**：`OutputConfig` 统一封装 codec、resolution、fps、crf 等 FFmpeg 相关默认值，避免散落在各工具中。