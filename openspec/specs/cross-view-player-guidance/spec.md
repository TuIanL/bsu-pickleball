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

系统 SHALL 提供 `CrossViewGuidancePolicy`,冻结 guidance 触发条件:`min_global_confidence` / `max_uncertainty_ft` / `missing_after_ticks` / `guidance_cooldown_ticks` / `max_regions_per_view_per_tick`。`ViewBinding` SHALL 包含 `visibility: observed | weak | missing | lost`、`last_seen_take_timestamp_ms`、`quality`。仅当目标视角 binding 为 `weak / missing / lost` 时 SHALL 触发 high-recall ROI;上一 tick 已稳定 observed 的 global SHALL 不重复补跑 guided ROI。

#### Scenario: 仅弱/缺/失触发

- **WHEN** 某 confirmed+anchored global 的目标视角 binding 为 `observed`
- **THEN** 系统 SHALL NOT 为该 tick 生成 guided ROI
- **AND** 仅当 binding 变为 `weak / missing / lost` 才触发

#### Scenario: cooldown 与上限

- **WHEN** 已触发过一次 guidance
- **THEN** 在 `guidance_cooldown_ticks` 内 SHALL NOT 重复触发
- **AND** 每 view 每 tick 的 guided region 数 SHALL 不超过 `max_regions_per_view_per_tick`

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

