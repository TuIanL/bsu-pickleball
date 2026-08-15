# multiview-analysis-result-composer Specification (Delta)

## Purpose

本 delta 收紧 joint compose 的产物契约：除视觉层产物外，joint 路径 SHALL 产出 `global-player-roster.v1`（诊断 / 映射 contract）与 Global→canonical Player 映射（reference view display anchor），公开轨迹身份一律 `Player_1..4 / P1..P4`；joint 路径 SHALL 生成与单摄同契约的 structured visualization data（22×10 网格、canonical label）；球员计数按明确语义区分；F1 不得改变 roster 映射。

## Requirements

## MODIFIED Requirements

### Requirement: joint compose 视觉层产物契约

joint_tracking_v2 模式的 `compose_joint_result` SHALL 产出或继承前端视觉层产物（tracking_overlay / pose_overlay / heatmaps / player_render_trajectory 等），并补齐 `*_url` / `*_status` / `*_detail` 契约，使前端框架、骨架、热力图与小地图可用。热力图 / scatter / structured data SHALL 使用 canonical `Player_N / Pn` 标签（经 roster 映射），MUST NOT 直接使用 `global_player_N` 作为用户可见标签。joint 路径 SHALL 生成与单摄同契约的 `structured/data.json`（22×10 visual grid、每球员独立 grid、`heatmaps.players[].id ∈ {Player_1..4}`），复用 `PositionVisualizationDataBuilder`，使前端 `StructuredHeatmap` 走 SVG 渲染而非旧 PNG 降级。

#### Scenario: joint 结果含视觉层产物

- **WHEN** joint Parent 完成分析
- **THEN** Parent artifacts SHALL 包含 `tracking_overlay_url`、`pose_overlay_url`、`heatmaps_url` 等
- **AND** 前端视觉层 SHALL 可加载（非 unavailable）

#### Scenario: 产物来源如实标注

- **WHEN** joint 模式产出视觉层产物
- **THEN** 产物 SHALL 标注来源（joint run / canonical player 标签）
- **AND** SHALL NOT 伪装为 child 单摄产物

#### Scenario: joint 产出 structured data

- **WHEN** joint 分析完成且 roster confirmed
- **THEN** 系统 SHALL 生成 `position_visualizations/structured/data.json`
- **AND** `heatmaps.players[].id` SHALL 仅含 `Player_1..Player_4`
- **AND** `heatmaps.players[].label` SHALL 为 `P1..P4`

#### Scenario: 公开产物无 global id

- **WHEN** joint 分析完成
- **THEN** 用户可见的轨迹身份 / 热力图标签 / report SHALL NOT 包含 `global_player_`
- **AND** 全部使用 canonical `Player_N / Pn`

## ADDED Requirements

### Requirement: global-player-roster.v1 产物（诊断 / 映射 contract）

joint compose SHALL 产出 `global-player-roster.v1` 产物（JSON，定位为**内部诊断 / 映射 contract**，非用户展示 identity）：包含 `schema_version`、`expected_player_count`、`roster_occupied_count`、`confirmed_player_count`、`status`（`bootstrap` / `confirmed`）与每个 roster 玩家的 `global_player_id`、canonical `player_id`（`Player_N`）、`label`（`Pn`）及 `bindings`（各 view 的 `view_player_id` 与 track provenance）。该产物与内部 diagnostics 可保留 internal `global_player_N`；用户可见的 trajectory / metrics / structured visualization / report 中 SHALL NOT 出现 `global_player_`。Composer 将 fused 样本转 tracks 时 SHALL 以 roster 映射将 `global_player_id` 转换为 canonical `Player_N`。**canonical `Player_N` 由 reference view 的 formal local identity 决定（display anchor）**：稳定绑定 reference view 的 `Player_N` 则公开身份为该 `Player_N`；仅有 non-reference evidence 时暂缓分配，reference binding 出现后再确定；整场 reference 缺失使用 deterministic fallback（如 slot 顺序）并在产物中标注。

#### Scenario: roster 产物可发布

- **WHEN** joint 分析完成
- **THEN** Parent artifacts SHALL 包含 roster.v1 的 `*_json_path` / `*_url`
- **AND** 每个 roster 玩家 SHALL 有 `global_player_id ↔ Player_N ↔ Pn` 完整映射

#### Scenario: 轨迹身份为 canonical

- **WHEN** Composer 由 fused 样本生成 `ProjectedTrackPoint`
- **THEN** `track_id` SHALL 为 canonical `Player_N`（经 roster 映射，reference binding 决定）
- **AND** 同一物理球员在不同重跑中的公开身份 SHALL 保持一致（非 slot 顺序编号）

#### Scenario: 诊断产物保留 internal id

- **WHEN** 检查 `global-player-roster.v1` 或内部 diagnostics
- **THEN** 其中 SHALL 可包含 internal `global_player_N`
- **AND** 用户可见产物 SHALL NOT 包含该字符串

### Requirement: 球员计数语义

Composer / report 的球员统计 SHALL 区分并明确语义：`expected_player_count`（赛制人数）、`roster_occupied_count`（已占 slot 数）、`confirmed_player_count`（已确认玩家数）、`observed_player_count`（实际有观测的玩家数）。报告摘要 SHALL 按实际确认 / 观测人数如实呈现，MUST NOT 为避免大量碎片轨迹而硬写 `expected_player_count`。

#### Scenario: 遮挡致只确认 3 人

- **WHEN** 双打任务因遮挡最终只确认 3 名玩家
- **THEN** 摘要 SHALL 如实报告确认 / 观测人数（如 3）
- **AND** 不得为凑数报告"检测到 4 条球员轨迹"

#### Scenario: 碎片轨迹不计入

- **WHEN** 分析产生大量 transient candidate（从未晋升）
- **THEN** 球员计数 SHALL 基于 roster / confirmed / observed 玩家
- **AND** candidate 数 SHALL NOT 计入公开球员计数

### Requirement: F1 offline refinement 冻结 roster 映射

F1 offline refinement SHALL NOT 改变 roster 身份映射：不得修改 `global → Player_N` 对应关系，SHALL NOT 在 F1 阶段分配新 roster slot。roster snapshot SHALL 与 F0 snapshot 一起冻结；F1 仅可补充 observation、改善 fused position。

#### Scenario: F1 不改身份

- **WHEN** F1 运行于已确认 roster 之上
- **THEN** F1 输出 SHALL 保持 F0 的 global→canonical 映射
- **AND** SHALL NOT 新增或重分配 roster slot
