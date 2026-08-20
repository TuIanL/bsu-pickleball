## ADDED Requirements

### Requirement: bootstrap display 证据分支（最低优先级兜底）
`fused_overlay_builder` 既有「五种 evidence（`base_observed` / `guided_observed` / `refined_observed` / `cross_view_projected` / `predicted_only`）+ hidden outcome」决策链 SHALL 增加最低优先的 `bootstrap_backfill` 分支：仅当五级证据全部缺失、且 `frame < 该 player 的 locked_frame_index`、且存在 `bootstrap_backfill` 真实观测时启用。该分支 MUST NOT 覆盖任何更高级别证据，也 MUST NOT 产生「不渲染」之外的额外 outcome。

#### Scenario: 填补 bootstrap 空窗
- **WHEN** 五级证据在 bootstrap 窗口内均缺失，但存在该 player 的 `bootstrap_backfill` 真实观测
- **THEN** `evidence_type` SHALL 为 `bootstrap_backfill`
- **AND** 展示状态映射 SHALL 将其归为带真实 bbox 的展示态（如 `REAL_BOX`）

#### Scenario: 不降级既有证据
- **WHEN** 某帧某 player 同时存在 stronger 证据与 `bootstrap_backfill` 数据
- **THEN** 系统 SHALL 优先采用 stronger 证据
- **AND** `bootstrap_backfill` 数据 SHALL 被抑制，不替换原证据

#### Scenario: 契约一致性
- **WHEN** overlay 写出 player entity 且 `evidence_type=bootstrap_backfill`
- **THEN** 后端 `EvidenceType` Literal 与前端 `FusedPlayerEvidenceType` SHALL 均包含 `bootstrap_backfill`，且 `FUSED_EVIDENCE_STYLE` SHALL 提供其展示样式；否则验证/构建 SHALL 失败

### Requirement: player entity 携带 canonical court position
`fused_player_overlay` 的每个 player entity SHALL 携带 `canonical_court_position_ft`（由回填或既有路径经 `local_to_canonical` 得到），使人物框与小地图共用同一展示时间语义、同源同 tick。

#### Scenario: 小地图同源
- **WHEN** 前端 `CourtMinimap` 读取展示轨迹
- **THEN** SHALL 可从 overlay 的 `canonical_court_position_ft` 获取球员位置（joint 模式 display authority = fusedPlayerOverlay）
- **AND** 单摄模式仍保持 `pipelineTracks` 路径；joint 模式若 fused overlay 可用则用 overlay-derived display tracks，仅旧任务/不可用时 fallback `result.tracks`
- **AND** MUST NOT 新增第三个 `display_player_trajectory` artifact，也 MUST NOT 直接修改 authoritative `result.tracks` 语义

#### Scenario: 坐标契约
- **WHEN** overlay 写出 `canonical_court_position_ft`
- **THEN** 字段 SHALL 为 `[x, y] | null`（英尺，canonical court 坐标系）
- **AND** 建议同时携带 `court_frame_version="canonical_court_frame.v1"` 与 `court_unit="ft"` 以强化契约，避免前端单位猜测
