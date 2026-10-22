# MV分镜脚本 - {{songName}}

> 基于 Seedance AI 视频生成平台的分镜脚本
> 生成时间：{{generateTime}}

---

## 元信息

| 项目 | 内容 |
|------|------|
| 歌曲名称 | {{songName}} |
| ASS源文件 | {{assFile}} |
| 歌曲风格 | {{songStyle}} |
| 情感基调 | {{emotionalTone}} |
| 歌曲语言 | {{language}} |
| 总时长 | {{duration}} |
| 节奏 | {{tempo}} |
| 分镜数量 | {{shotCount}} |
| 叙事风格 | {{narrativeStyle}} |
| 叙事主线 | {{storyline}} |
| 视觉基调 | {{visualTone}} |

---

## 人物配置

### 女主形象

- **人物来源**：{{femaleSource}}（{{femaleCharacterId}}）
- **年龄估计**：{{femaleAge}}
- **人物形象风格**：{{femaleStyle}}
- **发型**：{{femaleHair}}
- **上装**：{{femaleTop}}
- **外套**：{{femaleCoat}}
- **下装**：{{femaleBottom}}
- **鞋子**：{{femaleShoes}}
- **饰品**：{{femaleAccessories}}

### 男主形象

- **人物来源**：{{maleSource}}（{{maleCharacterId}}）
- **年龄估计**：{{maleAge}}
- **人物形象风格**：{{maleStyle}}
- **发型**：{{maleHair}}
- **上装**：{{maleTop}}
- **外套**：{{maleCoat}}
- **下装**：{{maleBottom}}
- **鞋子**：{{maleShoes}}
- **饰品**：{{maleAccessories}}

---

## 歌曲结构总览

| 段落 | 类型 | 起始时间 | 结束时间 | 时长 | 歌手 |
|------|------|---------|---------|------|------|
| {{sectionIndex}} | {{sectionType}} | {{sectionStart}} | {{sectionEnd}} | {{sectionDuration}} | {{sectionSinger}} |

---

## 分镜列表

### Shot {{shotNumber}} - {{shotName}}

| 字段 | 内容 |
|------|------|
| 时间戳 | {{startTime}} - {{endTime}} ({{duration}}s) |
| 歌词 | {{lyrics}} |
| 歌手 | {{singer}} |
| 歌曲段落 | {{songSection}} |
| 镜头类型 | {{shotType}} |
| 人物 | {{character}} |
| 景别 | {{shotSize}} |
| 角度 | {{cameraAngle}} |
| 运镜 | {{cameraMovement}} |
| 场景描述 | {{sceneDescription}} |
| 人物动作 | {{characterAction}} |
| 色调 | {{colorTone}} |
| 光影 | {{lighting}} |
| 情绪氛围 | {{emotionalAtmosphere}} |
| 节奏 | {{pacing}} |
| 转场 | {{transition}} |

**Seedance Prompt**：

```
{{seedancePrompt}}
```

---

{{nextShotStart}}

## 附录

### 情感走向

```
{{emotionalArcChart}}
```

### 镜头统计

| 统计项 | 数值 |
|--------|------|
| 总分镜数 | {{totalShots}} |
| 人物镜数量 | {{characterShotCount}} |
| 双人镜数量 | {{duoShotCount}} |
| 空镜数量 | {{emptyShotCount}} |
| 平均分镜时长 | {{avgShotDuration}}s |
| 最长分镜 | {{maxShotDuration}}s |
| 最短分镜 | {{minShotDuration}}s |

### 段落分布

| 段落类型 | 数量 | 占比 |
|---------|------|------|
| 前奏 | {{introCount}} | {{introPercent}}% |
| 主歌 | {{verseCount}} | {{versePercent}}% |
| 副歌 | {{chorusCount}} | {{chorusPercent}}% |
| 桥段 | {{bridgeCount}} | {{bridgePercent}}% |
| 间奏 | {{interludeCount}} | {{interludePercent}}% |
| 尾奏 | {{outroCount}} | {{outroPercent}}% |
