# cross-view-player-guidance Specification

## Purpose
CrossViewGuidance 生成 + `CrossViewGuidancePolicy` 触发策略:confirmed + cross_view_anchored 的目标视角才生成 ROI 搜索先验,不直接制造 observation。
## Requirements
### Requirement: CrossViewGuidance 契约

系统 SHALL 提供 `CrossViewGuidance`,包含 `global_player_id`、`target_view`、`predicted_canonical_position`、`uncertainty_ft`、`predicted_local_position`、`expected_image_position`、`roi`(目标视角图像空间)、`confidence`、`expires_at`。该 guidance SHALL 由 `confirmed AND cross_view_anchored` 的 global player 的 motion estimator 预测驱动。

#### Scenario: 完整 guidance 字段

- **WHEN** 为某 confirmed + anchored global 生成 guidance
- **THEN** guidance SHALL 包含目标视角、预测位置(canonical/local)、预期图像位置、ROI、置信度与过期时间

#### Scenario: 过期失效

- **WHEN** guidance 的 `expires_at` 已过
- **THEN** 系统 SHALL NOT 再以其指导检测

### Requirement: CrossViewGuidancePolicy 触发语义

系统 SHALL 提供 `CrossViewGuidancePolicy`,冻结 guidance 触发条件:`min_global_confidence` / `max_uncertainty_ft` / `missing_after_ticks` / `guidance_cooldown_ticks` / `max_regions_per_view_per_tick`。`ViewBinding` SHALL 包含 `visibility: observed | weak | missing | lost`、`last_seen_take_timestamp_ms`、`quality`、`consecutive_available_misses`。目标视角的 guidance 触发资格 SHALL 由共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)` 判定：`visibility in {"weak","missing","lost"}` 或（`fast_recovery_enabled` 且 `consecutive_available_misses >= 1`）时 SHALL 允许触发 high-recall ROI；两者均不满足（observed 且无 available miss）的 global SHALL 不重复补跑 guided ROI。

#### Scenario: 仅弱/缺/失触发（fast path 无 miss）

- **WHEN** 某 confirmed+anchored global 的目标视角 binding 为 `observed` 且 `consecutive_available_misses == 0`
- **THEN** 系统 SHALL NOT 为该 tick 生成 guided ROI
- **AND** `GuidanceDecision.reason` SHALL 为 `target_not_missing`

#### Scenario: available miss 快速触发

- **WHEN** 某 confirmed+anchored global 的目标视角 binding 仍为 `observed`，但上一 canonical tick 出现 available miss（`consecutive_available_misses >= 1`）且 `fast_recovery_enabled=true`
- **THEN** 系统 SHALL 允许为该 tick 生成 guided ROI
- **AND** `GuidanceDecision.trigger_source` SHALL 为 `available_miss`

#### Scenario: cooldown 与上限

- **WHEN** 已触发过一次 guidance
- **THEN** 在 `guidance_cooldown_ticks` 内 SHALL NOT 重复触发（按现有单位解释与消费语义）
- **AND** 每 view 每 tick 的 guided region 数 SHALL 不超过 `max_regions_per_view_per_tick`

### Requirement: GuidanceDecision 触发来源可观测

`GuidanceDecision` SHALL 携带 `trigger_source`（`"visibility_age" | "available_miss" | None`）以区分"为什么有资格"，同时保留 `reason` 表示"最终为什么生成/拒绝"。系统 MUST NOT 将 fast path 语义写入 `reason` 而丢失真正的拒绝原因。

#### Scenario: 有资格但被拒绝时双字段独立

- **WHEN** fast path 有资格（`trigger_source=available_miss`）但 donor 不合格
- **THEN** `GuidanceDecision.reason` SHALL 为 `donor_low_quality`（或对应 donor 原因）
- **AND** `trigger_source` SHALL 保持 `available_miss`

### Requirement: canonical→local→image 投影

guidance 的 ROI SHALL 通过 `canonical → canonical_to_local() → H^-1 → image` 投影链计算(复用既有 `canonical_to_local` 与单应逆变换)。

#### Scenario: ROI 投影

- **WHEN** 已知 canonical 预测位置与 covariance 推导的 uncertainty
- **THEN** 系统 SHALL 投影到目标视角图像空间得到 `roi`
- **AND** ROI 尺寸 SHALL 由 uncertainty 决定

### Requirement: guidance 不创造 measurement

guidance SHALL 仅提供 ROI 搜索先验,SHALL NOT 直接产生 observed sample。只有目标摄像机自身重新检测出的真实像素证据才能成为 observed sample(invariant 3)。

#### Scenario: 仅搜索先验

- **WHEN** 目标视角在 guidance ROI 内未检测到人
- **THEN** 该 global 在该 tick SHALL 无该视角观测
- **AND** 系统 SHALL NOT 因 guidance 存在而伪造观测

### Requirement: donor-aware 双向 guidance

`CrossViewGuidance` SHALL 包含 `guidance_id`、`donor_view`、`donor_view_player_id`、donor source frame/take timestamp、`donor_quality`、`donor_origin`、`expected_global_player_id` 与原有 target prediction/ROI 字段。系统 SHALL 对任意 target view 独立生成 guidance，不得将 reference view 作为唯一 donor。

#### Scenario: 非 reference view 帮助 reference view
- **WHEN** Cam1 为 reference view 但其 binding weak，Cam2 有合格 donor
- **THEN** 系统 SHALL 能生成 target=Cam1、donor=Cam2 的 guidance

### Requirement: donor 与 target availability 门

强 guidance SHALL 要求 donor 为不同 view 的 recent `base` observation、quality 达阈值且 global confirmed + anchored；target binding 为 weak/missing/lost 且 target frame `available`。target frame unavailable 时 SHALL 不生成 ROI 且不消耗 cooldown。

#### Scenario: guided evidence 不得作为 donor
- **WHEN** 唯一候选 donor 的 observation origin 为 `guided_roi`
- **THEN** 系统 SHALL NOT 为其生成强 guidance

#### Scenario: target frame 不可用
- **WHEN** target binding 已 weak 但该 canonical tick 的 target frame status 非 `available`
- **THEN** 系统 SHALL 不调用 target ROI detection
- **AND** diagnostics SHALL 记录 availability skip 而非视觉 recovery failure

### Requirement: pre-tick cooldown 消费语义

guidance SHALL 仅由 pre-tick snapshot 决定；same-tick base detection 不得改变已建立的 snapshot。cooldown 仅在 target source frame 成功 decode 且实际调用 ROI `detect_regions` 后消费。target geometry 缺失、decode 失败或 detector 无 ROI 能力时 SHALL 记录 skip/error，且 SHALL NOT 消费 cooldown。

#### Scenario: available 但 decode 失败
- **WHEN** target `FrameSample` 为 `available` 但 source frame decode 失败
- **THEN** 系统 SHALL 记录 recovery decode error
- **AND** SHALL NOT 消费该 global/target 的 guidance cooldown

#### Scenario: target geometry 缺失
- **WHEN** target view 不具完整 orientation、inverse homography 或 frame dimensions
- **THEN** 系统 SHALL 记录 `recovery_skip_missing_target_geometry`
- **AND** SHALL NOT 使用 reference view geometry 生成 ROI

### Requirement: target per-view geometry 投影

每条 guidance 的 `predicted_local_position`、expected image position 与 ROI SHALL 使用 target view 自己的 orientation、inverse homography、frame width 和 frame height 计算。

#### Scenario: 异构视角 ROI
- **WHEN** 两路具有不同尺寸或 calibration transform
- **THEN** 对每个 target 的 ROI SHALL 使用该 target 的几何上下文

### Requirement: GuidanceDecision 只读可观测

`GuidanceGenerator` SHALL 提供 side-effect-free 的 `GuidanceDecision` 只读记录（如 `last_decisions`），对每次未生成 guidance 的评估 SHALL 记录 `status`（`generated | not_eligible`）与结构化 `reason`（如 `target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / not_confirmed_anchored`）。该 observability SHALL NOT 改变 `generate()` 的返回、触发语义或任何门限。

#### Scenario: 未生成 guidance 时原因可追溯

- **WHEN** 某 `(global_player, target_view)` 在 tick 未生成 guidance（binding 未 weak、或 donor 不可用、或 uncertainty 超限、或 cooldown 未过、或 geometry 缺失）
- **THEN** 系统 SHALL 记录 `GuidanceDecision(status=not_eligible, reason=<具体原因>)`
- **AND** guidance 生成逻辑与触发语义 SHALL 保持不变

#### Scenario: 生成 guidance 时状态确认

- **WHEN** 某 `(global_player, target_view)` 在 tick 成功生成 guidance
- **THEN** 系统 SHALL 记录 `GuidanceDecision(status=generated)` 及该 guidance 标识
- **AND** 该记录 SHALL 不影响 guidance 返回与消费

### Requirement: build_expected_player_region 共享纯函数

系统 SHALL 提供纯函数 `build_expected_player_region(predicted_position, uncertainty, target_geometry, policy)`，按 guidance 现有 ROI 计算规则（`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`）构建 expected player region。guidance 与 player display diagnostics SHALL 共用该函数，MUST NOT 各写一套固定半径的 expected region。

#### Scenario: guidance 与 diagnostics 共用同一 region

- **WHEN** 同一 `(predicted_position, uncertainty, target_geometry)` 输入
- **THEN** guidance ROI 与 diagnostics expected region SHALL 由同一纯函数产生一致的几何
- **AND** 不得出现 diagnostics 计数使用的 region 与 guidance 实际搜索 region 不一致

### Requirement: 触发语义扩展（pre-tick + same-tick + 共享 budget）

目标视角的 guidance 触发资格 SHALL 由共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)` 判定（#2 已交付）：`visibility in {"weak","missing","lost"}` 或（`fast_recovery_enabled` 且 `consecutive_available_misses >= 1`）时允许 **pre-tick guidance**。本 Change 扩展：当 `same_tick_recovery_enabled=true` 且**本 tick pre-association 发现另一路当前帧有 strong base candidate、本路无 usable candidate** 时，SHALL 允许生成 **same-tick guidance**（在 commit 前，不依赖 binding age）。same-tick guidance SHALL 复用 `CrossViewGuidance` 契约与 `guided_detection.py` 的 pre-gate/merge，MUST NOT 新增第二套检测路径；ROI 中心 SHALL 使用 donor 当前 canonical evidence（非仅旧 prediction），尺寸复用 `build_expected_player_region`；**donor 严格限定为当前 source frame 的 base evidence**（origin=base）。pre-tick 与 same-tick SHALL 共享 `RecoveryAttemptLedger` 预算：`pre_tick_count[view] + same_tick_count[view] ≤ max_regions_per_view_per_tick`，同一 `(global, target)` 一 tick 至多一次 ROI。

#### Scenario: same-tick guidance 触发

- **WHEN** `same_tick_recovery_enabled=true`，P1 本 tick 在 Cam1 有 strong base pre-association candidate、Cam2 无 usable candidate
- **THEN** 系统 SHALL 对 Cam2 生成 same-tick guidance（即使 pre-tick predicate 不满足）
- **AND** ROI 中心 SHALL 为 Cam1 当前 canonical position 投影

#### Scenario: donor 严格 base

- **WHEN** 某 view 仅有 pre-tick guided evidence（origin=guided_roi）作为唯一 donor
- **THEN** 系统 SHALL NOT 将其作为 same-tick donor
- **AND** same-tick 补检 SHALL NOT 触发（防 guided→guided 自我强化）

#### Scenario: 共享 budget 不翻倍

- **WHEN** 某 view 本 tick pre-tick guidance 已用 3 个 ROI、`max_regions_per_view_per_tick=4`
- **THEN** same-tick guidance SHALL 最多再分配 1 个 ROI（合计 ≤ 4）
- **AND** MUST NOT 各自独立按 4 计算

#### Scenario: 同 pair 去重

- **WHEN** 某 `(global, target)` 本 tick 已有 pre-tick ROI 尝试
- **THEN** same-tick 阶段 SHALL NOT 对该 pair 再次跑 ROI
- **AND** 记入 `RecoveryAttemptLedger.attempted_pairs`
