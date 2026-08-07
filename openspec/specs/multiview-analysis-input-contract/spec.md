# multiview-analysis-input-contract Specification

## Purpose
TBD - created by archiving change add-multiview-player-trajectory-fusion. Update Purpose after archive.
## Requirements
### Requirement: MultiViewFusionRun 输入组合

`MultiViewFusionRun` MUST 持有完整多视角输入：`capture_take_id / source_analysis_job_ids / view_inputs[] / sync_calibration_ref / canonical_frame_ref`。每个 `MultiViewViewInput` MUST 包含 `capture_track_id / video_id / analysis_job_id / calibration_id / court_orientation`。输入 MUST 基于两个已完成单视角 AnalysisJob，MUST NOT 将 AnalysisJob 改造为混合多视角对象。

#### Scenario: 基于两个 source job

- **WHEN** 用户为双摄 take 发起多视角分析
- **THEN** 系统 SHALL 创建 `MultiViewFusionRun`，引用 `cam_1` 与 `cam_2` 两个已完成 AnalysisJob
- **AND** 两个 source job SHALL 保持单视角 AnalysisJob 契约不变

#### Scenario: view input 组成

- **WHEN** `MultiViewFusionRun` 构造输入
- **THEN** 每个 `MultiViewViewInput` SHALL 含 `capture_track_id / video_id / analysis_job_id / calibration_id / court_orientation`
- **AND** `court_orientation` 缺失 SHALL 表示为 `None`（未声明），不引入第五种朝向

### Requirement: 权威时间同步输入

Multi-view 分析输入 MUST 引用权威 `dual_camera_sync_calibration.v1`，而不是仅依赖 `CaptureTrack.offset_ms`。该契约 SHALL 至少包含 `reference_camera / offset_ms / rate / drift_ppm / residual_rms_ms / valid interval / sync_quality`。

#### Scenario: 权威 artifact 可用

- **WHEN** 某 `CaptureTake` 存在权威 `dual_camera_sync_calibration.v1`
- **THEN** Multi-view 输入 SHALL 引用该 artifact 的映射参数
- **AND** 系统 SHALL 用 `map_reference_time` / `build_frame_map` 类既有逻辑计算共同时间轴与帧选择误差

#### Scenario: 输入契约字段

- **WHEN** Multi-view 输入被构造
- **THEN** 输入 SHALL 携带 `reference_camera / offset_ms / rate / drift_ppm / residual_rms_ms / valid interval / sync_quality`
- **AND** 缺失或非法的字段 SHALL 将同步质量标记为 `unknown`

### Requirement: Canonical Timeline 与 pairing tolerance

Fusion 的融合时刻来源 MUST 冻结为 **reference track 的 analysis-frame timeline**。对每个 `take_timestamp_ms = t`，系统 MUST 用 sync mapping 寻找另一视角最近真实 source sample，并要求 `abs(selection_error_ms) <= max_pairing_error_ms`，否则该视角该时刻 `view_status = unavailable`。`max_pairing_error_ms` MUST 作为独立于 `valid interval` 的 pairing tolerance 契约存在。

#### Scenario: reference 时间轴

- **WHEN** 系统确定融合时刻
- **THEN** 融合时刻 SHALL 取自 reference track 的 analysis-frame timeline
- **AND** 每个时刻 SHALL 携带 `take_timestamp_ms` 与 `reference_frame_index`

#### Scenario: pairing 容差

- **WHEN** 为某 reference 时刻寻找另一视角样本
- **THEN** 系统 SHALL 计算 `selection_error_ms`
- **AND** 若 `abs(selection_error_ms) > max_pairing_error_ms`，该视角该时刻 SHALL 标记 `view_status = unavailable`

#### Scenario: 逐帧可追溯

- **WHEN** 某 fused sample 需要解释组成
- **THEN** 每路 `view_observations` SHALL 记录 `source_frame_index / source_timestamp_ms / mapped_take_timestamp_ms / selection_error_ms`
- **AND** 该信息 SHALL 足以回答"该 fused 点由两路哪两个真实帧组成"

### Requirement: 同步质量门控

Multi-view 融合的同步门控 MUST 满足：`good` → 正常双视角融合；`degraded` → 允许融合但降低时间同步质量权重并输出诊断；`unknown / unavailable` → 禁止伪装为 synchronized fusion，自动退化到最佳单视角轨迹。

#### Scenario: good 正常融合

- **WHEN** `sync_quality = good`
- **THEN** 系统 SHALL 允许双视角位置融合
- **AND** 时间同步权重为正常水平

#### Scenario: degraded 降权并诊断

- **WHEN** `sync_quality = degraded`
- **THEN** 系统 SHALL 允许融合
- **AND** 系统 SHALL 降低时间同步质量权重
- **AND** 系统 SHALL 在 diagnostics 中记录降级原因

#### Scenario: unknown 退化为单视角

- **WHEN** `sync_quality = unknown` 或 sync authority `unavailable`
- **THEN** 系统 SHALL NOT 标记输出为 synchronized fusion
- **AND** 系统 SHALL 自动退化到最佳单视角轨迹（job-level fallback）

### Requirement: 无 artifact 不等于零偏移

当某 track 缺少 `dual_camera_sync_calibration.v1` 时，系统 MUST 将同步状态视为 `sync authority unavailable`，MUST NOT 将其等同于 `offset_ms = 0` 的假设对齐。

#### Scenario: 缺 artifact 状态

- **WHEN** 多视角输入未提供 sync_calibration artifact
- **THEN** 系统 SHALL 标记该输入 `sync authority unavailable`
- **AND** 系统 SHALL NOT 使用 `offset_ms = 0` 作为对齐假设

### Requirement: 时间有效区间

共同时间轴的构建 MUST 遵守 `dual_camera_sync_calibration.v1` 的 `valid_start / valid_end`。落在某一路有效区间之外的时刻，该路 MUST 标记为 `unavailable` 而非外推或伪造帧。

#### Scenario: 区间外时间

- **WHEN** 目标时刻位于某一路 `valid interval` 之外
- **THEN** 该路 SHALL 标记为 `unavailable`
- **AND** 系统 SHALL NOT 为该时刻生成看似有效的对齐观测

