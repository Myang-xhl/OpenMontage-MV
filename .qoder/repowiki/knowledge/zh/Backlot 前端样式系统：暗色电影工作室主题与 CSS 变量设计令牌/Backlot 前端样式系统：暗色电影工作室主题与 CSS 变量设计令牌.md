---
kind: frontend_style
name: Backlot 前端样式系统：暗色电影工作室主题与 CSS 变量设计令牌
category: frontend_style
scope:
    - '**'
source_files:
    - backlot/ui/board.css
    - backlot/ui/studio.css
    - backlot/ui/index.html
    - backlot/ui/studio.html
---

## 1. 使用的系统与方案
- 纯原生 CSS + HTML + Vanilla JS，无框架、无构建工具、无预处理器。
- 通过 `@import` 引入 Google Fonts（Inter、JetBrains Mono、Courier Prime），字体选择服务于“暗室剪辑台”的电影工业感。
- 使用 CSS 自定义属性（`:root` 变量）作为设计令牌中心，配合 `[data-theme="light"]` 实现明/暗双主题切换。
- 响应式策略基于 CSS Grid + Flexbox + `@media` 断点，未使用任何 CSS-in-JS 或 Tailwind。

## 2. 核心文件与包
- `backlot/ui/board.css` — 主设计系统：颜色、字体、动画、布局、胶片条、分镜卡片、审批面板等全部样式。
- `backlot/ui/studio.css` — Studio 聊天工作台样式，复用 board.css 的变量与 chip/live badge 等通用组件。
- `backlot/ui/index.html` / `studio.html` / `board.html` / `preview.html` — 页面骨架，仅引用 CSS 与对应 JS 模块。
- `backlot/ui/lib.js` / `library.js` / `board.js` / `studio.js` / `preview.js` — 行为脚本，不内联样式。

## 3. 架构与约定
- **设计令牌集中化**：所有颜色、字号缩放比例（`--fs-scale`）、阴影、滚动条、背景渐变等均定义在 `:root`，主题切换只需覆盖同名变量。
- **双主题机制**：默认暗色（near-black matte canvas, amber/green/red 语义色），通过 `:root[data-theme="light"]` 覆盖为暖色调浅色主题，包括胶片纹理、投影、边框等细节。
- **字体层级**：`--sans`（Inter）用于正文，`--mono`（JetBrains Mono）用于 UI 标签/状态，`--screenplay`（Courier Prime）用于剧本卡片，形成清晰的视觉层次。
- **动画与动效**：统一的 `rise` 入场动画 + 延迟序列（`.stage:nth-child(n)` 递增 delay），以及 shimmer 生成态、pulse 实时指示、grain 胶片颗粒叠加。
- **组件化命名**：采用 BEM-like 类名（如 `.script-card`、`.scene-card`、`.approval-review`、`.st-*`），避免冲突且可读性强。
- **响应式断点**：`900px`（board 单列）、`1100px`（studio 隐藏右侧 board 面板），保证移动端可用。

## 4. 约定与约束
- **禁止内联样式**：所有样式必须写在 `.css` 文件中，HTML 仅通过 `<link>` 引用。
- **主题一致性**：新增 UI 元素必须优先使用 `var(--*)` 设计令牌，不得硬编码颜色值。
- **字体缩放**：全局字号通过 `calc(<px> * var(--fs-scale))` 计算，确保可访问性缩放时整体比例一致。
- **交互状态语义**：`.done` / `.active` / `.await` / `.failed` / `.generating` / `.missing` 等状态类名需严格遵循已有语义。
- **性能约束**：首屏动画仅在首次加载触发（通过 `body:not(.first)` 控制），后续 SSE 刷新不重复播放入场动画。
- **可访问性**：焦点可见性通过 `:focus-visible` 显式设置蓝色轮廓，滚动条自定义但保持可操作。
- **无第三方依赖**：不使用任何 CSS 框架或库，所有效果（胶片颗粒、渐变、阴影）均用原生 CSS/SVG 实现。