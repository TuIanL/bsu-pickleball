# singles-aware-player-selection Specification

## Purpose
定义赛制感知的球员选择与锁定机制，包括 PlayerGroupProfile、分侧配额、fallback_tentative 状态和 formal eligibility 链。

## Requirements

### Requirement: PlayerGroupProfile 替代硬编码分组一致性

系统 SHALL 定义 `PlayerGroupProfile` 作为赛制感知的期望分组结构，替换 `_group_consistency_scores()` 中硬编码的 `same_side_expected=1`、`opposite_side_expected=2`。

#### Scenario: 单打分组评分

- **WHEN** `PrimaryPlayerSelector` 在单打上下文中计算 `group_consistency_score`
- **THEN** `expected_same_side_others` SHALL 为 0（除自身外同侧不应有其他人）
- **AND** `expected_opposite_players` SHALL 为 1（对侧应有 1 人）

#### Scenario: 双打分组评分

- **WHEN** `PrimaryPlayerSelector` 在双打上下文中计算 `group_consistency_score`
- **THEN** `expected_same_side_others` SHALL 为 1（除自身外同侧有 1 名队友）
- **AND** `expected_opposite_players` SHALL 为 2（对侧应有 2 人）

#### Scenario: 偏差匹配分

- **WHEN** `_count_match_score(actual=0, expected=0)` 被调用
- **THEN** 返回值 SHALL 为 1.0（完全匹配）

- **WHEN** `_count_match_score(actual=2, expected=0)` 被调用
- **THEN** 返回值 SHALL 为 0.0（完全不匹配）

- **WHEN** `_count_match_score(actual=1, expected=1)` 被调用
- **THEN** 返回值 SHALL 为 1.0（完全匹配）

#### Scenario: 单打同侧出现路人时评分下降

- **WHEN** 单打视频中同侧出现 1 名路人（`same_side_count=1`，expected=0）
- **THEN** `same_score` SHALL 为 0.0
- **AND** 总体 `side_score` SHALL 显著低于正常值

### Requirement: Selector quota-aware 最终组合选择

系统 SHALL 在 PrimaryPlayerSelector 评分排序后，按 near/far 分侧配额进行最终组合选择，而非简单取前 N 名。此配额选择必须覆盖 rule 和 attention 两条路径。

#### Scenario: 单打排序 A近端(0.90)、B近端(0.85)、C远端(0.82)

- **WHEN** `near_side_quota=1, far_side_quota=1` 且排序为 `[A_near, B_near, C_far]`
- **THEN** `_select_balanced_candidates` SHALL 选择 A_near + C_far
- **AND** SHALL NOT 选择 A_near + B_near

#### Scenario: Attention 路径不绕过配额

- **WHEN** attention 选择的 track 集合包含两名同侧球员
- **THEN** quota-aware final selection SHALL 仍按照分侧配额从 attention 集合中选择
- **AND** 最终输出 SHALL 满足 near/far side quota

### Requirement: PrimaryPlayerSelector 每 tracking run 重建

系统 SHALL 在每次 `_run_tracking` 开始时创建新的 `PrimaryPlayerSelector`，以 `match_context.expected_player_count` 作为 `max_subjects`，避免跨任务状态污染。

#### Scenario: 单打 selector 创建

- **WHEN** `_run_tracking` 在单打上下文中执行
- **THEN** `PrimaryPlayerSelector` SHALL 以 `max_subjects=2` 创建
- **AND** `select()` SHALL 最多返回 2 个候选

#### Scenario: 双打 selector 创建

- **WHEN** `_run_tracking` 在双打上下文中执行
- **THEN** `PrimaryPlayerSelector` SHALL 以 `max_subjects=4` 创建
- **AND** `select()` SHALL 最多返回 4 个候选

### Requirement: Formal eligibility 链使用 LockManager 输出

系统 SHALL 确保正式分析链路（PlayerIdentityManager、tracking overlay、pose、trajectory、heatmap、metrics）只消费 `lock_update.eligible_track_ids`。`suggested_track_ids` 仅作为 LockManager 输入、bootstrap 排序提示和诊断信息。

#### Scenario: Selector 建议被 LockManager 拒绝

- **WHEN** Selector 建议 3 个 track（A_near, B_near, C_far）但 LockManager 因 near_quota=1 只接纳 A_near 和 C_far
- **THEN** `formal_eligible_track_ids` SHALL 为 `{A_near, C_far}`
- **AND** `frame_detections` SHALL 只包含 A_near 和 C_far
- **AND** `PlayerIdentityManager` SHALL 只处理 A_near 和 C_far
- **AND** B_near SHALL 不出现在任何正式 artifact 中

#### Scenario: suggested_track_ids 仅用于诊断

- **WHEN** LockManager 拒绝 B_near
- **THEN** B_near SHALL 仍然出现在 selector diagnostics 或 debug overlay 中
- **AND** B_near SHALL NOT 出现在 tracking overlay、pose、trajectory 或 metrics 中

### Requirement: PlayerLockManager 分侧配额与 fallback_tentative

系统 SHALL 在 `PlayerLockManager` 中增加 near/far side 配额约束，阻止单打中同侧锁定两名球员。fallback 分配的身份处于 `fallback_tentative` 状态，可被缺失侧的高质量候选替换。

#### Scenario: 单打严格分侧

- **WHEN** `PlayerLockManager` 使用 `near_side_quota=1`、`far_side_quota=1` 运行
- **THEN** `_assign_candidate_to_slot()` SHALL 拒绝向已满的 near side 分配新候选
- **AND** 拒绝原因 SHALL 记录为 `side_quota_exceeded`

#### Scenario: 同一分配路径覆盖所有入口

- **WHEN** 候选通过 `_try_early_lock` 分配
- **THEN** `assignment_side` SHALL 非空

- **WHEN** 候选通过 `_finalize_bootstrap` 分配
- **THEN** `assignment_side` SHALL 非空

- **WHEN** 候选通过 `_try_lock_slot` 在 bootstrap 后分配
- **THEN** `assignment_side` SHALL 非空

#### Scenario: Bootstrap 截止降级

- **WHEN** `bootstrap_max_frames` 到达且 near_side 仍未被占满
- **THEN** `allow_quota_fallback=True` SHALL 允许将 side=unknown 或 side=far 的候选分配到 near slot
- **AND** 系统 SHALL 写入 `side_quota_fallback` diagnostic

#### Scenario: 降级不静默

- **WHEN** 降级触发
- **THEN** 对应 diagnostic SHALL 包含 `match_format`、`expected`（各侧配额）、`assigned`（实际分配数）

#### Scenario: BootstrapTracklet 中位数分侧

- **WHEN** `_BootstrapTracklet.inferred_side()` 处理一批 court_ys
- **THEN** 使用 `statistics.median()` 而非均值确定 side
- **AND** 距离中线 `SIDE_DEAD_ZONE_FT` 以内的候选返回 `None`

#### Scenario: Fallback 分配进入 fallback_tentative

- **WHEN** `allow_quota_fallback=True` 且候选通过 fallback 分配到 slot
- **THEN** slot.state SHALL 为 `fallback_tentative`（而非 `tentative` 或 `locked`）
- **AND** slot SHALL 输出为低置信度临时候选

#### Scenario: fallback_tentative 可被缺失侧候选替换

- **WHEN** 一个 `fallback_tentative` slot 当前占据 side=near
- **AND** 一名新的 side=far 候选出现且 `confidence > slot.confidence_ema * fallback_replacement_margin`
- **THEN** slot SHALL 被新候选替换
- **AND** 系统 SHALL 记录 `{"event": "side_quota_fallback_replaced", "old_track_id": ..., "new_track_id": ...}` diagnostic

#### Scenario: fallback_tentative 达到 promotion 条件后转为 locked

- **WHEN** `fallback_tentative` slot 持续存在超过 `fallback_promotion_frames`
- **THEN** slot.state SHALL 转为 `locked`
- **AND** 该 slot SHALL 不再被普通候选抢占

### Requirement: PlayerIdentityManager 任务级人数上限

系统 SHALL 使用 `match_context.expected_player_count` 而非全局固定值设置身份管理器的最大球员数。

#### Scenario: 单打身份管理

- **WHEN** `PlayerIdentityManager` 以 `max_players=2` 创建
- **THEN** 系统 SHALL 最多创建 `Player_1` 和 `Player_2` 两个身份
- **AND** SHALL NOT 生成 `Player_3` 或 `Player_4`

#### Scenario: 双打身份管理

- **WHEN** `PlayerIdentityManager` 以 `max_players=4` 创建
- **THEN** 系统 SHALL 支持创建 `Player_1` 至 `Player_4`

### Requirement: 全局配置作为安全上限

系统 SHALL 将全局球员数量配置从"目标值"重构为"系统硬限制"，运行时取 `min(match_context.expected_player_count, setting_hard_limit)`。

#### Scenario: 硬限制不低于目标

- **WHEN** `settings.player_identity_hard_limit=4` 且 `match_context.expected_player_count=2`
- **THEN** 有效值 SHALL 为 `min(4, 2) = 2`

#### Scenario: 硬限制低于目标

- **WHEN** `settings.player_identity_hard_limit=2` 且 `match_context.expected_player_count=4`
- **THEN** 有效值 SHALL 为 `min(2, 4) = 2`
- **AND** 系统 SHALL 记录配置限制告警

### Requirement: 球员框和骨架只输出正式参赛球员

系统 SHALL 确保最终叠加框、骨架、轨迹只包含赛制指定的正式球员，超出人数的路人仅进入诊断。

#### Scenario: 单打画面中的路人

- **WHEN** 单打视频中 YOLO 检测到 4 人（2 名球员 + 2 名路人）
- **THEN** `PrimaryPlayerSelector` SHALL 只选择属于比赛的两名球员
- **AND** `eligible_track_ids` SHALL 只包含这两名球员的 track_id
- **AND** `frame_detections` SHALL 只对这两名球员生成正式叠加框
- **AND** 路人 SHALL 不获得 Player_3/Player_4 身份
- **AND** 路人 SHALL 不进入姿态、热力图和小地图正式产物
