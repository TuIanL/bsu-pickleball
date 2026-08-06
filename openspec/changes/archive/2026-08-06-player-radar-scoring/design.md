## Context

视频分析页（`VisionPage` jobId 视图）需要新增"球员打分"能力：每名球员按六维（发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性）给出 10 分制（1 位小数）雷达评分，P1-P4 切换查看。该功能前置要求是球员身份区分与对齐必须无问题。

现状审计（已完成）：
- **身份层已按场地位置区分**：`PlayerLockManager` 槽位语义 `Player_1..4 = 近左/近右/远左/远右`（`player_lock_manager.py:_slot_home_quadrant`），bootstrap 按象限分配身份。
- **干净线（已 canonical）**：球员轨迹 artifact、`metrics.speeds/kitchen_dwell/distances`（`track_id=Player_N`）、render trajectory v2（`player_id` + `slot_N` 对齐）、`serve_events.player_id`、HUD 检测框标签（`Player_2`→`P2`）。
- **断线**：`visualization_data_builder.py` 与 `zone_stats.py` 的 `heatmaps` / `scatter_plots` / `zone_stats` / `player_trajectories` 用排序索引重新编号：`id=str(index)`、`label=display_player_label(label)`→`"球员N"`、`color=PLAYER_HEX_COLORS[index]`。目前数字对齐纯属巧合（`Player_N` 自然排序 = 数字序），且 id/label 无法 join 回 canonical 身份。
- **前端数据结构**：`result.tracks[]` 的 `track_id` 即 canonical `Player_N`（`to_projected_track_points` 输出）；`getPlayerRenderTrajectory` 的 `players[]` 也是 canonical；`StructuredHeatmap` / `StructuredScatterPlot` / `StructuredZoneHeatmap` 对 `id/label/color` 是通用字段，无索引硬编码。

约束：保持现有调色板；分数先上 mock 但键为 canonical；球员数量按结果自适应；打包成一个 change。

## Goals / Non-Goals

**Goals:**
- 结构化可视化产物（heatmaps / scatter / zone_stats / player_trajectories）的球员 `id` 为 canonical `Player_N`、`label` 为 `P1`..`P4`，与 HUD 身份对齐；颜色保持现有调色板、视觉零变化。
- 视频分析页底部新增整行球员评分面板：六轴 SVG 雷达图 + P1-P4 自适应切换 tab + 10 分制 1 位小数。
- 评分数据模型键为 canonical `player_id`，mock 填充，为真实算法接入预留（不改键）。
- 前后端测试覆盖对齐与评分面板。

**Non-Goals:**
- 不实现真实评分算法（后续独立接入，数据源替换为 API/派生指标）。
- 不改动 HUD 颜色与现有结构化可视化调色板。
- 不触碰 demo 视图（无 jobId）的 `SkillRatings` / `RecommendedDrills` / `ProgressChart`。
- 不引入第三方图表库（雷达图为纯 SVG）。

## Decisions

### D1. 后端结构化可视化产物 canonicalize

修改 `display_player_label`（`visualization_schemas.py`）输出 `P1`..`P4`（解析失败回退原始 label）。该函数仅被 `zone_stats.py` 与 `visualization_data_builder.py` 两处调用，一次改动同时生效，无需新增辅助函数。

`compute_zone_stats`（`zone_stats.py`）：
- `id`：`str(index)` → `canonical_player_id(label)`。
- `color`：`colors[index % len]` → 按 canonical 序号显式分配 `colors[(player_number - 1) % len]`；`canonical_player_id` 解析不出数字时回退 `colors[index % len]`。

`visualization_data_builder.py` 的 `_build_heatmaps` / `_build_scatter_plots` / `_build_player_trajectories` / `_build_zone_stats`：
- `id=canonical_player_id(label)`，`label=display_player_label(label)`（已改为 `P1` 风格），`color` 按 canonical 序号（同 D1）。

**理由**：身份是单一事实源，产物不应重新编号。canonical 数字分配颜色与现状完全一致（现有排序 == canonical 数字序），只是从"巧合对齐"变为"显式对齐"。前端三组件读通用字段，标签自动变 `P1`，无需前端改动。
**备选**：仅在前端 join 标签解析 `"球员2"`→`P2`——脆弱且不改颜色错位，否决。

### D2. 评分数据模型与 mock（前端）

`src/types/report.ts` 新增：
- `PLAYER_SCORE_DIMENSIONS` 常量：6 个维度 `{ key, label }`（发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性）。
- `PlayerScore`：`{ player_id: "Player_1".."Player_4"; serve; return_serve; offense; defense; agility; shot_consistency }`，每项 0–10、1 位小数。
- `PlayerScoring`：`{ players: PlayerScore[] }`（与后端结构化产物风格一致）或 `Record<string, PlayerScore>` 索引。

mock 数据：新模块 `src/data/mockPlayerScores.ts` 导出 `MOCK_PLAYER_SCORES: Record<string, PlayerScore>`，键为 `Player_1`..`Player_4`，覆盖 4 人。

**理由**：键用 canonical 是硬性对齐要求；mock 只是填充源，接口形状（`Record<Player_N, PlayerScore>`）即未来真实数据形状。
**备选**：mock 分数按"整场一条"复用 `SkillRating`——不区分球员、不满足需求，否决。

### D3. 自适应球员列表（前端）

面板 roster 提取：`result?.tracks` 去重 canonical `track_id`（`to_projected_track_points` 输出 `track_id=Player_N`），`formatPlayerId` 映射 `P1`..`P4`，按 canonical 自然序排序。

无真实结果（demo / 数据缺失）：兜底 `Player_1`..`Player_4`（结合 `match_context.expected_player_count` 决定 2 或 4）。

**理由**：`result.tracks` 已在 VisionPage 加载，无需额外请求；canonical 键天然与评分 mock、HUD 对齐。
**备选**：`getPlayerRenderTrajectory` 的 `players[]`——需要额外请求且与 tracks 等价，否决。

### D4. RadarChart 组件（纯 SVG）

`src/components/platform/RadarChart.tsx`：
- 六轴等角（60°）六边形雷达，`viewBox` 自适应；中心 0、外缘 10。
- 环形网格（0 / 2 / 4 / 6 / 8 / 10），顶点维度标签（中文）+ 分值文本（`toFixed(1)`）。
- 球员多边形填充用该球员 canonical 色；选中球员颜色来自 `PLAYER_ID_TO_COLOR`（镜像后端 `PLAYER_HEX_COLORS`：`Player_1=#22C55E`、`Player_2=#F97316`、`Player_3=#A855F7`、`Player_4=#3B82F6`，保持现有调色板）。

**理由**：无第三方依赖，符合现有纯 SVG 可视化风格；1 位小数显式 `toFixed(1)`。

### D5. PlayerScoringPanel 组件与接入

`src/components/platform/PlayerScoringPanel.tsx`：
- 整行 `sport-card`：左侧 `RadarChart`，右侧 P1-P4 球员 tab（chip，选中高亮）+ 该球员六项分值列表 + 六项均分。
- 默认选中 roster[0]，点击切换。
- props：`roster: string[]`（canonical player ids）、`scores: Record<string, PlayerScore>`（缺省回退 `MOCK_PLAYER_SCORES`）。

`VisionPage` jobId 视图：在可视化产物 gallery 之后追加整行 `<section>` 接入面板。

**理由**：贴合"最下方再加一行窗口"的布局描述；mock 作为缺省源，真实数据接入时仅传参替换。

### D6. 测试

- 后端：更新 `test_zone_heatmap.py` 中 `"球员N"` / `id="0"` 断言为 `P1` / `Player_N`；新增 heatmaps/scatter/zone 的 canonical id+label+按序颜色的断言。
- 前端：`RadarChart`（六轴渲染、`toFixed(1)` 分值）、`PlayerScoringPanel`（tab 切换、默认选中、自适应 roster、mock 回退）、`PLAYER_SCORE_DIMENSIONS` 形状。

## Risks / Trade-offs

- **[BREAKING 数据契约] `/visualization-data` 球员 id/label 变更** → 前端三组件通用处理、已 grep 无索引硬编码；唯一代价是更新后端测试断言。Mitigation：任务重跑即生成新格式 JSON，旧磁盘 JSON 展示期可接受。
- **[用户可见文案变化] `"球员N"` → `P1`** → 有意为之（与 HUD 对齐），proposal 已标注 BREAKING；影响 heatmap/zone/scatter 图例与下拉。
- **[非 canonical 标签混入]** 若产物出现非 `Player_N` 标签（如 fallback `"Player"`），`canonical_player_id` 原样返回、颜色回退索引 → 该 artifact 无法 join P1-P4。Mitigation：当前管线球员点必带 canonical id（`player_points_from_artifact` / `player_render_points_from_artifact` 均以 `player_id` 为键）；文档记录该边缘情况，不做额外处理。
- **[mock 分数与真实数据并存]** 真实 job 的面板也显示 mock 分数 → 暂态，明确标注"演示数据"；键为 canonical，真实算法接入时只换数据源、UI 不变。

## Migration Plan

单仓库、无外部部署。回滚 = revert commit。`/visualization-data` 契约变更随新任务产物生效；展示期旧 JSON 可直接删除重跑。
## Open Questions

- 评分面板是否每个维度附一句评分依据/说明？→ 本期不实现，作为候选后续需求（避免本期范围膨胀）。
- 单打（2 人）时 mock 是否按 2 人准备？→ 已定：mock 固定 4 人，roster 裁剪，不随格式分支。
