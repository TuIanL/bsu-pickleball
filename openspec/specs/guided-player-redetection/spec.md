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
