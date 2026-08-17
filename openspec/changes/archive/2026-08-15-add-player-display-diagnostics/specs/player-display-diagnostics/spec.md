## ADDED Requirements

### Requirement: 逐 tick 显示漏斗产物

joint run 对每个 `(roster confirmed player, available view, canonical tick)` SHALL 生成紧凑的逐 stage 显示诊断行（`player-display-diagnostics.v1`），回答"该球员此刻为何这样显示 / 为何不显示"。产物 SHALL 独立于 `joint_debug_trace`，`debugTraceEnabled=false` 时 MUST 仍生成。漏斗行 SHALL 至少包含：`canonical_tick / timestamp_ms / player_id / view_id / frame_status`、`expected_region_status / expected_image_position`、`eligible_detections_in_expected_gate`、分层断裂状态（`eligible_detection_present / position_present / court_position_present / projection_status / projection_confidence / formal_observation_emitted`）、`global_associated / association_reason`、`binding_visibility`、`guidance_status / guidance_skip_reason`。产物中的 `player_id` SHALL 直接为 canonical `Player_N`。

#### Scenario: 常规 joint run 生成显示漏斗

- **WHEN** joint run 完成且任一 tick 存在 roster confirmed player 与 available view
- **THEN** 系统 SHALL 生成 `player-display-diagnostics.v1` 产物
- **AND** 产物中该 `(player, view, tick)` 存在一行完整诊断

#### Scenario: debugTraceEnabled=false 仍可生成

- **WHEN** joint run 完成且 `debugTraceEnabled=false`
- **THEN** 系统 SHALL 仍生成显示漏斗产物
- **AND** SHALL NOT 因缺少 debug trace 而跳过或失败

### Requirement: v1 漏斗边界为 post-lock eligible detection

`player-display-diagnostics.v1` 的漏斗起点 SHALL 为 post-tracker/post-lock 的 eligible detection（`frame_detections` 是 `PlayerLockManager` 产出 `eligible_track_ids` 后才构建的检测框，非 raw YOLO 输出）。字段 `eligible_detections_in_expected_gate` SHALL 表示"落在 expected region 门内的 eligible detection 数量"，MUST NOT 被描述为 raw YOLO hit 或检测器原始召回。raw detector / ROI filter / tracker / lock rejection 的归因 MUST NOT 属于本 Change 能力范围。

#### Scenario: eligible detection 与 raw YOLO 区分

- **WHEN** 某 tick 存在落在 expected region 门内的 `frame_detections` 候选
- **THEN** 漏斗 SHALL 记录 `eligible_detections_in_expected_gate >= 1`
- **AND** 该字段 SHALL 不宣称 YOLO 原始检测命中或 lock 之前的状态

#### Scenario: 不归因更早 stage

- **WHEN** 某候选未进入 `frame_detections`（如被 ROI filter / tracker / lock 提前过滤）
- **THEN** v1 漏斗 SHALL NOT 对 raw stage 归因（不记录"被 ROI 丢掉"/"被 lock 拒绝"）
- **AND** 该 case 表现为该 view 无对应 eligible detection 行信息

### Requirement: 分层断裂状态独立记录

漏斗对每个候选 SHALL 独立记录 `eligible_detection_present / position_present / court_position_present / projection_status / projection_confidence / formal_observation_emitted`，MUST NOT 合并为单个布尔。`eligible_detection_present=true, position_present=false` 与 `position_present=true, court_position_present=false` SHALL 可区分（根因不同，但都导致 formal observation 缺失）。

#### Scenario: 检测存在但 position 缺失

- **WHEN** `frame_detections` 有该 track、`frame_positions` 无该 track
- **THEN** 漏斗 SHALL 记录 `eligible_detection_present=true`、`position_present=false`、`formal_observation_emitted=false`
- **AND** SHALL NOT 记录为"无检测候选"

#### Scenario: position 存在但 court projection 缺失

- **WHEN** `frame_positions` 有该 track、但 `court_position` 为 None
- **THEN** 漏斗 SHALL 记录 `position_present=true`、`court_position_present=false`、`formal_observation_emitted=false`
- **AND** `projection_status` SHALL 保留原始失败原因

#### Scenario: 检测与身份分离

- **WHEN** 某候选 `eligible_detection_present=true` 但未被分配 local player_id
- **THEN** 漏斗 SHALL 记录 `formal_local_observation=false` 且 `local_player_id` 为空
- **AND** SHALL NOT 将该候选标记为对应 Player_N 的检测命中

### Requirement: 查询 API 按 Player_N 与时间窗口

系统 SHALL 提供 `GET /analysis/jobs/{job_id}/multiview/players/Player_1/display-diagnostics?timestamp_ms=7000&window_ms=500` 查询接口。API SHALL 直接按 `player_id == "Player_1"` 过滤产物行，MUST NOT 在 API 层反查内部 global id。查询 SHALL 返回窗口内该球员两路 view 的漏斗行（按 canonical tick 升序），并 SHALL 合并 fused overlay 的展示层 evidence_type（若 overlay 产物存在）。

#### Scenario: 窗口查询返回两路证据链

- **WHEN** 客户端查询 `Player_1` 在 `timestamp_ms=7000, window_ms=500` 的显示诊断
- **THEN** API SHALL 返回该窗口内 cam_1/cam_2 两路按 tick 升序的漏斗行
- **AND** 响应 SHALL 包含 `player_id=Player_1`，不包含内部 global/track id

#### Scenario: 查询未知球员

- **WHEN** 客户端查询的 `Player_N` 不在产物中
- **THEN** API SHALL 返回结构化空结果与 reason（如 `player_not_found`）
- **AND** SHALL NOT 返回错误或伪造数据

#### Scenario: 产物不存在

- **WHEN** 该 job 未生成显示漏斗产物（如非 multiview 或历史任务）
- **THEN** API SHALL 返回结构化 `unavailable` 与 reason
- **AND** 页面 SHALL 显示不适用状态而非错误

### Requirement: expected region 因果性与状态语义

漏斗的 expected region SHALL 只使用 **pre-tick global prediction**（该帧处理前系统预期位置），MUST NOT 使用 same-tick fused position（避免 hindsight bias；fused 缺失时也不得作为 fallback）。`expected_region_status` SHALL 为 `available | prediction_unavailable | uncertainty_too_high | target_geometry_unavailable`。仅 `available` 时 `eligible_detections_in_expected_gate` SHALL 为计数；否则 SHALL 为 `null`（MUST NOT 写 `0`）。expected region 几何 SHALL 复用 guidance 的 ROI 计算规则（`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`），通过共享纯函数实现，MUST NOT 各写一套固定半径。

#### Scenario: expected region 不可用时不写 0

- **WHEN** pre-tick prediction 缺失、或 uncertainty 超限、或 target geometry 不可用
- **THEN** 漏斗 SHALL 记录 `expected_region_status` 为对应原因
- **AND** `eligible_detections_in_expected_gate` SHALL 为 `null` 而非 `0`

#### Scenario: expected region 可用时计数

- **WHEN** `expected_region_status=available` 且 expected region 内有 N 个 eligible detection
- **THEN** `eligible_detections_in_expected_gate` SHALL 为 N
- **AND** 计数 SHALL 使用与 guidance 相同的 ROI 几何

### Requirement: association/guidance 决策可观测（只读）

漏斗的 `global_associated / association_reason` SHALL 来自 `GlobalPlayerAssociator.last_tick_decisions`（只读 per-observation 决策记录，如 `AssociationDecision(view_id, observation_key, result, global_id, reason)`），MUST NOT 假设 `AssociationUpdate` 自带 reason。漏斗的 `guidance_status / guidance_skip_reason` SHALL 来自 `GuidanceGenerator` 的 side-effect-free `GuidanceDecision`（如 `target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / not_confirmed_anchored`）。这些 observability SHALL 不改变 association 与 guidance 的算法结果、门限或返回。

#### Scenario: 关联决策 reason 可追溯

- **WHEN** 某观测未分配到任何 global（或按某 reason 拒绝）
- **THEN** 漏斗 SHALL 记录 `global_associated=false` 与结构化 `association_reason`
- **AND** 该 reason 来自只读决策记录，不改变关联结果

#### Scenario: guidance 未触发原因可追溯

- **WHEN** 某 tick 未为某 `(player, view)` 生成 guidance
- **THEN** 漏斗 SHALL 记录 `guidance_status=not_eligible` 与结构化 `guidance_skip_reason`
- **AND** guidance 生成逻辑与触发语义 SHALL 不变

### Requirement: 显示漏斗只读

显示漏斗产物与查询 API SHALL 为只读诊断，MUST NOT 反写 roster / tracker / association / guidance 状态；查询 MUST NOT 触发重分析或重放。

#### Scenario: 查询不改变分析状态

- **WHEN** 客户端请求某 job 的显示诊断
- **THEN** 系统 SHALL 仅读取已有产物并返回
- **AND** SHALL NOT 修改任何分析状态或产物

### Requirement: 诊断失败隔离

显示诊断构建失败 MUST NOT 导致核心 joint 分析失败。当漏斗构建器抛错或产物写盘失败时，核心 joint result SHALL 保持成功，`player_display_diagnostics_status` SHALL 为 `failed` 并附结构化 reason。

#### Scenario: 诊断构建失败不影响核心结果

- **WHEN** joint run 完成但显示漏斗构建器抛出异常
- **THEN** 核心 joint result SHALL 仍为成功
- **AND** 系统 SHALL 记录 `player_display_diagnostics_status=failed` 与 reason

### Requirement: 产物体积控制

`player-display-diagnostics.v1` SHALL 为紧凑 flat 行结构（每行 < 300 字节量级），MUST NOT 膨胀为 debug trace 规模。MVP SHALL 全量落盘（不采样），但 SHALL 只记录 roster confirmed player × available view，MUST NOT 记录未确认候选或不可用帧的完整检测明细。

#### Scenario: 体积与 debug trace 可比性

- **WHEN** joint run 的 debug trace 为 127MB 量级
- **THEN** 同 run 的显示漏斗产物 SHALL 至少小一个数量级
- **AND** 产物只含确认球员 × 可用视角的漏斗行
