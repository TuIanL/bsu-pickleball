## ADDED Requirements

### Requirement: Bootstrap display 离线展示回填
系统 SHALL 在 joint_tracking_v2 任务完成后，基于首次 lock 映射（slot 第一次进入 locked 时记录的 `player_id` / `track_id` / `locked_frame_index`），对 bootstrap 窗口内已真实存在的原始 track 观测做 retrospective 展示回填，仅用于展示，MUST NOT 影响 authoritative 身份与指标。

#### Scenario: 首次 lock 映射为 authoritative source
- **WHEN** 系统需要确定某 Player_N 在 lock 之前的真实观测归属
- **THEN** 系统 SHALL 使用 `initial_lock_assignments`（首次进入 locked 时记录一次、永不覆盖），MUST NOT 依赖 `lock_diagnostics.player_locked` 反推

#### Scenario: 仅在有真实观测时填充
- **WHEN** 某 Player_N 的最终锁定 `track_id` 在 `locked_frame_index` 之前存在连续真实观测（bbox + local court_position）
- **THEN** 系统 SHALL 将这些观测经 `local_to_canonical(orientation=reference_orientation)` 转为 `canonical_court_position_ft`，原样（非插值）填入展示轨迹
- **AND** 回填记录 SHALL 标注 `evidence_type=bootstrap_backfill`、`display_only=true`、`metric_eligible=false`

#### Scenario: 无观测则自然为空
- **WHEN** bootstrap 窗口内该 `track_id` 无任何真实观测（如 pre-roll 阶段无人上场）
- **THEN** 系统 SHALL NOT 生成任何回填框或轨迹点
- **AND** MUST NOT 通过 backward-hold 首帧或位置插值制造假数据

#### Scenario: track temporal / spatial continuity guard
- **WHEN** 该 `track_id` 在 `locked_frame_index` 之前存在观测间隙（detector miss、frame_stride>1 的稀疏序列）
- **THEN** 系统 SHALL 允许自然间隙，不因此截断
- **AND** 对相邻真实观测，仅当 `Δt` 合理且 `displacement/Δt ≤ display_backfill_max_speed` 且空间连续时接受
- **AND** 若出现异常空间跳变，系统 SHALL 从跳变处截断该 Player_N 的历史，丢弃异常段（宁可少填）

#### Scenario: 不污染指标与融合
- **WHEN** 指标层、fusion 层或 global roster 消费数据
- **THEN** 系统 SHALL 仅从 authoritative 数据源读取
- **AND** MUST NOT 引用 `bootstrap_backfill` 数据，保证指标零影响

#### Scenario: 范围限定为 reference view
- **WHEN** 系统执行回填
- **THEN** 回填 SHALL 仅从 `reference_view_id` 的原始 tracking 轨道取 bbox / court，MUST NOT 混合 donor view 未归因观测
