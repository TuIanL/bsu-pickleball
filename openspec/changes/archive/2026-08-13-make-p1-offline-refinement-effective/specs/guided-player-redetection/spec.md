## MODIFIED Requirements

### Requirement: 离线第二遍检测复用 pre-gate 且只读 F0

offline refinement(F1) 的 recovered detection SHALL 复用 guided candidate pre-gate 与 `detection_origin` 机制，不重写检测链，不修改 F0 的 tracker、lock、identity、global state 或 global identity mapping。第二遍 SHALL 使用 `target_view` 自身的 `RefinementViewContext`，accepted 观测 SHALL 标记 `observation_origin=offline_refinement`。连续多帧证明 SHALL 使用窗口内轻量 `RecoveryTracklet`，不得使用 F0 tracker。

#### Scenario: 离线路径复用 pre-gate 且不碰 tracker

- **WHEN** F1 对 `RecoveryTickPlan` 的 target tick 执行 `detect_regions`
- **THEN** 结果 SHALL 经 guided candidate pre-gate 过滤
- **AND** 拒绝的 candidate 与 accepted recovered 均 SHALL NOT 调用 F0 tracker、lock、identity 或 global state update

#### Scenario: target view 使用独立 geometry

- **WHEN** `target_view` 为 Cam1 或 Cam2
- **THEN** candidate footpoint、projection、ROI 和 residual SHALL 使用 target view 自身的 homography、inverse homography、orientation 和 frame geometry
- **AND** SHALL NOT 使用 reference view geometry 或 secondary-only detector fallback

#### Scenario: RecoveryTracklet 窗口内累积

- **WHEN** 需要连续多帧证明某 recovered observation
- **THEN** 系统 SHALL 使用 `RecoveryTracklet { recovery_window_id, previous_bbox, previous_canonical_position, consecutive_hits }`
- **AND** SHALL NOT 复用或改写 F0 `MultiObjectTracker`

#### Scenario: 离线来源标记

- **WHEN** 一个 F1 第二遍检测被接受
- **THEN** 其 view observation SHALL 标记 `observation_origin=offline_refinement`
- **AND** 该 provenance SHALL 与 `base`、`guided_roi` 正交可区分

### Requirement: local-space guided candidate evidence

guided candidate pre-gate SHALL 在 target local court space 比较 candidate projection 与 donor/guidance 形成的 expected local position，并输出包含 target view、canonical tick/timestamp、expected global、donor、local position、residual、accepted/reject reason 的 evidence。reject candidate SHALL 永不进入 tracker 或 F1 refusion。

#### Scenario: 非 identity orientation residual

- **WHEN** target view orientation 为 `rotate_180`、`mirror_x` 或 `mirror_y`
- **THEN** 正确 local candidate SHALL 按 target local residual 通过 pre-gate
- **AND** 系统 SHALL 不将 local candidate 直接与 canonical prediction 比较

#### Scenario: evidence timestamp 来自 F0

- **WHEN** candidate 被接受为 recovered observation
- **THEN** evidence 的 `take_timestamp_ms` SHALL 来自对应 F0 canonical snapshot
- **AND** SHALL 保留 target source frame index/timestamp 与 timing authority provenance

### Requirement: guided provenance 贯穿 tracker assignment

本 requirement 对 online guided path 保持不变；offline recovered evidence SHALL 不进入 F0 tracker assignment。F1 refusion 时，recovered provenance 必须通过 target view observation 保留到 F1 fused sample 的 `view_observations`，不得通过 bbox 相似度重新猜测来源。

#### Scenario: offline provenance 进入 F1 evidence

- **WHEN** accepted offline recovered observation 被纳入 F1 refusion
- **THEN** F1 sample 的对应 view observation SHALL 保留 `offline_refinement`、donor、expected global、residual 和 source frame provenance
- **AND** SHALL NOT 产生 F0 tracker assignment 或修改 F0 track evidence
