# guided-player-redetection Specification

## Purpose
guided ROI 重检:global prediction → target ROI → lower-threshold 检测 → **candidate PRE-GATE(在 tracker 之前)** → accepted → 与 base merge → `tracker.update ONCE` → `detection_origin` provenance。
## Requirements
### Requirement: guided candidate pre-gate 在 tracker 之前

系统 SHALL 对 guided ROI 检测结果先执行 **candidate PRE-GATE**,仅保留 accepted guided candidates,再与 base detections 合并,最后 `tracker.update` 恰好一次。**pre-gate 拒绝的 guided detection SHALL 绝不触碰 tracker。**

```text
base detection + guided ROI detection
    → guided candidate PRE-GATE (bbox/image sanity → candidate footpoint → Homography projection → canonical residual → motion residual)
    → 只保留 accepted guided candidates
    → 与 base detections merge / deduplicate
    → tracker.update ONCE
```

#### Scenario: pre-gate 拒绝不碰 tracker

- **WHEN** 一个 guided candidate 未通过 residual pre-gate(如 canonical residual 过大)
- **THEN** 该 candidate SHALL NOT 进入 `tracker.update`
- **AND** 不创建/改写任何 track state(invariant 9)

#### Scenario: candidate 无需 track id

- **WHEN** 对 guided candidate 做 pre-gate validation
- **THEN** 系统 SHALL 从 `Detection.bbox → 临时 footpoint → image_to_court → canonical` 计算,无需既有 track id

### Requirement: 每 source frame 至多一次 tracker update

当某 source frame 同时有 base detections 与 accepted guided detections 时,系统 SHALL 在合并后对该帧执行一次 `tracker.update`,SHALL NOT 因 guided 重检对该帧二次调用(结合 clock 不重复喂帧,invariant 2)。

#### Scenario: 合并后一次 update

- **WHEN** 某 source frame 有 base 与 guided 两类 detections
- **THEN** 系统 SHALL 去重合并后执行一次 `tracker.update`
- **AND** SHALL NOT 对该帧二次调用 `tracker.update`

### Requirement: residual gate 与 accept/reject

accepted guided detection 经 court projection 后 SHALL 通过 residual gate(court 残差相对预测位置合理 + motion continuity)才成为 observed sample;否则 SHALL 拒绝且不进入 tracker 正式状态。

#### Scenario: 接受真实证据

- **WHEN** guided detection 有真实像素证据、court residual 合理、运动连续
- **THEN** 系统 SHALL 接受该 detection 为 observed sample
- **AND** 标记 `detection_origin=guided_roi`

#### Scenario: 拒绝纯预测

- **WHEN** guidance 预测位置附近无真实像素证据
- **THEN** 系统 SHALL 拒绝该 guided detection
- **AND** SHALL NOT 因 global prediction 存在而创造观测(invariant 3)

### Requirement: detection_origin provenance

每个 joint observation SHALL 记录 `detection_origin: base | guided_roi`,并保留进 `fused_player_trajectory.v2` 的 `view_observations`。

#### Scenario: 来源可追溯

- **WHEN** 一个 fused sample 的某视角观测来自 guided ROI 重检
- **THEN** 该视角观测 SHALL 携带 `detection_origin=guided_roi`
- **AND** 与 `base` 来源可区分,供质量/诊断消费

### Requirement: guided 观测可进指标

真实 accepted guided detection SHALL 可进入运动指标(`metric_eligible=true`);`predicted` 样本 SHALL 永远 `metric_eligible=false`(invariant 4)。

#### Scenario: accepted guided 进指标

- **WHEN** 一个 guided detection 被 residual gate 接受
- **THEN** 其 fused sample SHALL `metric_eligible=true`
- **AND** 参与距离/速度/热力图等指标计算

#### Scenario: predicted 不进指标

- **WHEN** 某 tick 无任何观测、仅输出 motion estimator 预测
- **THEN** 该样本 SHALL `metric_eligible=false`
- **AND** SHALL NOT 参与运动指标

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

### Requirement: evidence-aware merge 与 surviving-track filtering

base/guided merge SHALL 消费 `DetectionEvidence` 而非裸 detection。base/guided 高 IoU 重合时 SHALL 保留 base，并将 guided 记为 `duplicate_of_base`；多个 guided evidence 重合时 SHALL 按 residual 升序、donor quality 降序、`guidance_id` 稳定顺序保留唯一项。assignment 后，只有 `DuplicateTrackSuppressor` 最终保留的 track evidence 才可形成 joint observation。

#### Scenario: base 与 guided 同 tick 重合
- **WHEN** base detection 与 guided detection 命中同一人且超过 dedup overlap 阈值
- **THEN** 系统 SHALL 保留 base evidence
- **AND** guided evidence SHALL 不计为 recovery success

#### Scenario: 两条 guidance 命中同一 candidate
- **WHEN** 两个重叠 ROI 产生同一人的 guided candidates
- **THEN** 系统 SHALL 确定性地仅保留一份 guided evidence
- **AND** 被丢弃 evidence 的 reason SHALL 可在 diagnostics 中追溯

