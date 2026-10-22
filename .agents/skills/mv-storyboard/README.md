# mv-storyboard（Layer 3 技能）— 移植说明

来源：mv-storyboard 插件 v0.2.0（ASS 歌词 → MV 分镜脚本生成器），逐字移植，不改写、不精简。

## 已移植文件

- `SKILL.md` — 7 步全流程主规则文档（598 行全量）
- `assets/camera-language-reference.md` — 运镜语言参考
- `assets/narrative-style-guide.md` — 7 种叙事风格编排策略
- `assets/seedance-prompt-guide.md` — Seedance 2.0 prompt 规范（八大要素）
- `assets/storyboard-template.md` — Markdown 输出模板
- `assets/storyboard-schema.json` — 原始 JSON Schema（OpenMontage 侧的机器校验版见 `schemas/artifacts/storyboard.schema.json`）

## 移植时的唯一文本修正（M0）

`seedance-prompt-guide.md` 原文错别字：「颜抖」→「颤抖」、「嘴匯」→「嘴唇」（3 处，语义不变）。

## 未移植文件及原因

| 原文件 | 原因 |
|---|---|
| `.qoder-plugin/plugin.json` | 另一平台的插件清单，且存在 JSON 语法错误（version 行缺逗号） |
| `.trae/rules/mv-storyboard.md`、`.cursorrules` | 其他平台的路由跳板；OpenMontage 用 `AGENT_GUIDE.md` + `pipeline_defs/music-video.yaml` 路由 |
| `prompts/mv-storyboard-prompt.md` | SKILL.md 的精简副本（子集），无信息损失 |
| `assets/avatar.svg` | 插件市场图标，与生产无关 |
| `README.md`、`SETUP.md` | 面向原插件安装场景的文档，被本说明取代 |

## 在 OpenMontage 中的位置

本目录是 Layer 3 厂商/领域知识。编排入口是 `music-video` 流水线
（`pipeline_defs/music-video.yaml`），各阶段导演技能位于
`skills/pipelines/music-video/`，只引用本目录章节、不复制内容。
ASS 解析（SKILL.md Step 1）由确定性工具 `tools/analysis/ass_parser.py` 实现，
Step 2 起的语义判断仍由 Agent 按 SKILL.md 执行。
