# player-display-diagnostics Specification

## Purpose
joint 模式逐球员逐 stage 显示漏斗：对每个 `(roster confirmed player, available view, canonical tick)` 生成 `player-display-diagnostics.v1` 紧凑诊断，回答"该球员此刻为何这样显示 / 为何不显示"。v1 漏斗起点为 post-lock eligible detection，不依赖 `joint_debug_trace`，`debugTraceEnabled=false` 时仍生成；产物 `player_id` 直接为 canonical `Player_N`。
## Requirements
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

显示诊断构建失败 MUST NOT 导致核心 joint 分析失败。当漏斗构建器抛错或产物写盘失败时，核心 joint result SHALL 保持成功，`player_display_diagnostics_status` SHALL 为 `failed` 并附结构化 reason。产物缺失或构建失败时，composer SHALL 仍写盘一个占位 artifact（`status=failed` 或 `status=unavailable`），使查询 API 能返回结构化响应，MUST NOT 留下"文件不存在"状态导致 API 404。

#### Scenario: 诊断构建失败不影响核心结果

- **WHEN** joint run 完成但显示漏斗构建器抛出异常
- **THEN** 核心 joint result SHALL 仍为成功
- **AND** 系统 SHALL 记录 `player_display_diagnostics_status=failed` 与 reason
- **AND** composer SHALL 写盘占位 artifact（`status=failed`），查询 API 可读

#### Scenario: joint output 缺少 payload 时写占位产物

- **WHEN** joint run 完成但 `joint_output.display_diagnostics_payload` 缺失或非 dict（如构建失败、行数为空且校验拒绝）
- **THEN** composer SHALL 写盘一个占位 artifact（`status=unavailable`，`detail` 说明原因）
- **AND** 查询 API SHALL 返回该占位响应，MUST NOT 返回 404 "no artifact"

#### Scenario: 无确认球员/可用视角时仍产出空产物

- **WHEN** joint run 全程没有 roster confirmed player 或任何 available view
- **THEN** 系统 SHALL 产出 `status=unavailable` 的空 rows 产物（`rows=[]`）
- **AND** 查询 API SHALL 返回结构化 `unavailable` 而非 404

### Requirement: 产物体积控制

`player-display-diagnostics.v1` SHALL 为紧凑 flat 行结构（每行 < 300 字节量级），MUST NOT 膨胀为 debug trace 规模。MVP SHALL 全量落盘（不采样），但 SHALL 只记录 roster confirmed player × available view，MUST NOT 记录未确认候选或不可用帧的完整检测明细。

#### Scenario: 体积与 debug trace 可比性

- **WHEN** joint run 的 debug trace 为 127MB 量级
- **THEN** 同 run 的显示漏斗产物 SHALL 至少小一个数量级
- **AND** 产物只含确认球员 × 可用视角的漏斗行

### Requirement: 漏斗行展示 available_miss_streak

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `available_miss_streak` 字段（int，缺省 0），表示该 `(player, view)` 在该 tick 的连续 available global-view miss 计数（来源 `ViewBinding.consecutive_available_misses`，语义为"attempted available tick 但无 AssociationUpdate"）。该字段 SHALL 与 `binding_visibility` 并列展示，使"binding 仍为 observed 但已有连续 available miss"这类正交状态可见。查询 API SHALL 直接透传该字段（向后兼容：旧产物缺失时前端按 0 显示）。漏斗行构建 MUST 在 available-miss ledger 之后执行（当前 tick 的 miss 状态不得晚一拍呈现）。

#### Scenario: fast path 触发前后可观测

- **WHEN** 某 `(player, view)` 出现 available miss 并触发 fast path guidance
- **THEN** 漏斗行 SHALL 同时展示 `binding_visibility`（可能仍为 observed）与 `available_miss_streak`（>= 1）
- **AND** `guidance_skip_reason` 或 `guidance_status` 可反映 fast path 触发

#### Scenario: 漏斗不晚一拍

- **WHEN** 某 tick 首次出现 available miss
- **THEN** 该 tick 的漏斗行 SHALL 已显示 `available_miss_streak=1`
- **AND** MUST NOT 显示 0

#### Scenario: 旧产物向后兼容

- **WHEN** 查询历史任务的显示诊断产物（无 `available_miss_streak` 字段）
- **THEN** 前端 SHALL 按 0 展示该字段
- **AND** 查询 API SHALL NOT 因字段缺失报错

### Requirement: 漏斗行展示 pre-association 与 same-tick guidance

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `pre_association_status`（`candidate_found / projection_failed / ambiguous / not_assessed`）与 `same_tick_guidance_status`（`generated / not_generated_no_cross_candidate / not_needed_observed / geometry_unavailable`），使"本 tick 为什么没被 same-tick 救"可观测。字段缺省兼容旧产物（前端按未评估显示）。

#### Scenario: same-tick 触发过程可观测

- **WHEN** 某 `(player, view)` 本 tick 因另一路有 strong base candidate 而生成 same-tick guidance
- **THEN** 漏斗行 SHALL 展示 `pre_association_status=candidate_found` 与 `same_tick_guidance_status=generated`
- **AND** 补检结果（formal observation 是否形成）SHALL 由既有分层断裂字段呈现

#### Scenario: 两路投影失败可观测

- **WHEN** 两路均有 raw box 但两路 projection 均失败（本 Change 不补检的场景）
- **THEN** 漏斗行 SHALL 展示 `pre_association_status=projection_failed`
- **AND** 该情况 SHALL 明确呈现为 projection repair 问题（非 same-tick 机制失败）

#### Scenario: 旧产物兼容

- **WHEN** 查询历史任务的显示诊断产物（无该两字段）
- **THEN** 前端 SHALL 按未评估显示
- **AND** 查询 API SHALL NOT 因字段缺失报错

### Requirement: 身份冲突显式观测

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `roster_conflict` 字段（bool，缺省 false），表示该 `(player_id, view_id)` 行对应的 reference 槽位在本 tick 存在多 global 竞争（数据来源：`GlobalPlayerAssociator` 的 `reference_slot_conflict` 事件或等价只读观测）。duplicate 去重（保留首行）SHALL 保留，但身份冲突 SHALL 通过 `roster_conflict=true` 显式呈现，MUST NOT 仅靠"保留首行"掩盖。字段缺省兼容旧产物（前端按 false 显示）。

#### Scenario: 冲突槽位的行标记

- **WHEN** 某 tick cam_1 的 Player_1 槽位存在 gid_1/gid_3 竞争
- **THEN** 该 tick 的 `(Player_1, cam_1)` 漏斗行 SHALL `roster_conflict=true`
- **AND** 去重仍保留首行，但冲突可被观测

#### Scenario: 无冲突行不标记

- **WHEN** 某 tick 无多 global 竞争该槽位
- **THEN** 漏斗行 SHALL `roster_conflict=false`（或缺省）

#### Scenario: 旧产物兼容

- **WHEN** 查询历史任务的显示诊断产物（无 `roster_conflict` 字段）
- **THEN** 前端 SHALL 按 false 展示
- **AND** 查询 API SHALL NOT 因字段缺失报错

### Requirement: 查询 API 产物缺失时返回结构化 unavailable

`GET /analysis/jobs/{job_id}/multiview/players/{player_id}/display-diagnostics` 在产物文件缺失、产物 `status=unavailable/failed`、或窗口内无该球员行时，SHALL 返回结构化 `unavailable` 响应（携带 `reason` 与 `job_id`），前端据此显示"诊断暂不可用"状态。API SHALL NOT 以 404 HTTP 状态码表达"产物未生成"这一业务状态。

#### Scenario: 产物文件缺失

- **WHEN** `player_display_diagnostics_json_path(job_id)` 不存在（历史任务或构建完全失败）
- **THEN** API SHALL 返回结构化 `unavailable` 响应与 reason
- **AND** 响应 SHALL 携带 `job_id` 且 HTTP 状态码为非 404（如 200 或 422 语义错误之外的状态）

#### Scenario: 窗口内无该球员行

- **WHEN** 产物存在但窗口内没有 `player_id` 匹配的行
- **THEN** API SHALL 返回空 `rows` 列表的结构化响应
- **AND** SHALL NOT 返回错误或伪造数据

### Requirement: 全时间范围序列获取

display-diagnostics 查询 SHALL 支持为前端热力图提供跨窗口的时间序列数据。客户端 SHALL 以分段窗口（如 `window_ms=2000`）多次调用现有 `timestamp_ms + window_ms` 查询并本地拼接为 `(stage × tick)` 矩阵；服务端 SHALL 对 `window_ms` 不设低于 2000ms 的硬限制，或在超限时返回结构化 `partial` 与 reason，MUST NOT 报错或伪造缺失行。

#### Scenario: 分段拉取拼接

- **WHEN** 前端以 `window_ms=2000` 从 `timestamp_ms=0` 开始逐段查询某球员显示诊断
- **THEN** 前端 SHALL 按 canonical tick 升序拼接各段结果
- **AND** 拼接矩阵 SHALL 覆盖视频全时长，缺失段以"未触发"占位且不伪造行

#### Scenario: 大窗口请求

- **WHEN** 客户端请求 `window_ms=10000` 或更大窗口
- **THEN** 服务端 SHALL 返回窗口内全部漏斗行（受现有产物存在性约束）
- **AND** 若服务端存在窗口上限，SHALL 返回结构化 `partial` 与 reason 而非 500

#### Scenario: 球员切换重取

- **WHEN** 热力图切换球员
- **THEN** 前端 SHALL 以新 `player_id` 重新分段拉取
- **AND** 旧球员热力图 SHALL 被替换，不残留旧数据

