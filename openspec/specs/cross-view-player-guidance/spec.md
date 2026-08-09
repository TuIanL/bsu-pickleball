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
