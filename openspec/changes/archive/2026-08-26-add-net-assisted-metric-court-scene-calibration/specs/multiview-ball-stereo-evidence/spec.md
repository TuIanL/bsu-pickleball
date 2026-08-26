## ADDED Requirements

### Requirement: 逐 tick 立体测量记录场景标定来源

系统 SHALL 在双视角均观测到的 tick 产生 `BallStereoMeasurement`，作为不可变空间测量证据，不得直接当作最终三维球路。每个 measurement SHALL 记录其使用的 scene calibration revision、camera model source 和高度不确定度语义。

#### Scenario: metric 场景测量
- **WHEN** 双视角观测使用 `ready` 的 net-assisted scene calibration
- **THEN** measurement SHALL 包含既有时间、像素、`estimated_x_ft`、`estimated_y_ft`、`estimated_z_ft`、回投误差、epipolar residual、geometry quality 和 confidence
- **AND** SHALL 额外包含 `scene_calibration_revision`、`camera_model_source` 和 `height_uncertainty_ft`
- **AND** source SHALL 区分 `dual_view_metric_estimated` 或等价的 metric provenance

#### Scenario: approximate 场景测量
- **WHEN** 双视角观测没有 ready scene calibration而使用 Homography virtual camera
- **THEN** measurement SHALL 保留现有 approximate evidence
- **AND** SHALL 标记 `camera_model_source = homography_constrained_virtual`
- **AND** SHALL NOT 被下游当作 metric height evidence

#### Scenario: 单视角不可用
- **WHEN** 某 tick 只有单一视角观测到球
- **THEN** 该 tick SHALL 不产生双视角立体测量
- **AND** 由分层降级或短 gap prediction 处理

### Requirement: 场景质量进入 stereo 几何质量

stereo evidence SHALL 将 scene calibration 的 net/court reprojection residual、相机模型来源和 ray geometry 纳入 geometry quality 或其可审计质量分量。场景质量不足时，证据可以保留用于诊断，但不得成为高可信 metric anchor。

#### Scenario: 场景质量不足
- **WHEN** net residual、hold-out residual 或 ray geometry 未达到高可信阈值
- **THEN** evidence SHALL 保存该 measurement 及 rejection/quality reason
- **AND** `high_quality_anchor` SHALL 为 false
- **AND** 下游 SHALL 降级 metric height 或转入 approximate/2.5D
