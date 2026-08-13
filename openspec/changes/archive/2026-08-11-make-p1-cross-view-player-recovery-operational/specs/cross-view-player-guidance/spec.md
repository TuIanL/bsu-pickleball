## ADDED Requirements

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
