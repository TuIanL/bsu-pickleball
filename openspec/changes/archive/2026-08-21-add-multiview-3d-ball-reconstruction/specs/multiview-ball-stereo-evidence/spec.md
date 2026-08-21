## ADDED Requirements

### Requirement: 候选证据三级模型，detector 每帧一次
系统 SHALL 在 joint runtime 中，为每个视角每个 canonical tick 运行一次球 detector，经基础视觉过滤得到 `BallViewCandidate[]`（未经本地 `BallTracker` 唯一选择），并同时供本地 `BallTracker` 与跨视角 Stereo Layer 使用。固定执行序：detect/filter → snapshot 本地 predictor → stereo association → local tracker update。

#### Scenario: 单次检测多消费者
- **WHEN** 某视角某 tick 需要球检测
- **THEN** detector SHALL 只运行一次
- **AND** 经基础视觉过滤（bbox/aspect/ROI/明显静态误检）得到 `BallViewCandidate[]`
- **AND** 同一候选集合 SHALL 同时喂给本地 tracker 与 stereo associator
- **AND** `BallTracker` SHALL 通过 `update_from_candidates(...)` 消费该集合，不再自行重复 detect

#### Scenario: 本地误检可被跨视角挽救
- **WHEN** Cam1 候选集合包含 `{A=真球, B=误检}`、Cam2 候选为 `{A=真球}`
- **THEN** stereo associator SHALL 能通过集合内匹配选择 `A↔A`
- **AND** 不得因本地 tracker 已选唯一候选而丢失跨视角挽救机会

#### Scenario: stereo 不得反向修改 tracker 状态
- **WHEN** stereo associator 完成跨视角关联后
- **THEN** 关联结果 SHALL NOT 反向修改 `BallTracker` 状态（stereo 可救 evidence，不改单摄 tracker 行为）
- **AND** 执行序 SHALL 为 detect/filter → snapshot predictor → stereo association → local tracker update

### Requirement: 跨视角关联的硬门与排序分离
系统 SHALL 将跨视角候选关联的物理合理性硬门与几何排序严格分离，几何只用于帮助挑选，不用于 hard-reject。关联只消费 `frame_status == "available"` 的真实源帧观测。

#### Scenario: 硬门
- **WHEN** 系统判定两视角候选是否可关联
- **THEN** 硬门 SHALL 仅包括：源帧时间足够接近（`sync_quality` 合格）且三角化位置不荒谬、`z` 不严重低于地面、位置不严重飞出球场环境
- **AND** epipolar residual 高 SHALL NOT 单独作为硬拒绝条件

#### Scenario: 排序融合
- **WHEN** 多个候选配对通过硬门
- **THEN** 排序 SHALL 融合 dual-view 回投残差、epipolar residual、本地 tracker 连续性（读 pre-tick snapshot）、上一帧 3D 路径连续性、detector 置信度

### Requirement: 逐 tick 近似三角测量证据（非最终球路）
系统 SHALL 在双视角均观测到的 tick 产生 `BallStereoMeasurement`，作为不可变空间测量证据，不得直接当作最终三维球路。

#### Scenario: 采样结构
- **WHEN** 产生一次立体测量
- **THEN** 该测量 SHALL 包含 `take_timestamp_ms`、`cam1_timestamp_ms`、`cam2_timestamp_ms`、`cam1_image_xy`、`cam2_image_xy`、`estimated_x_ft`、`estimated_y_ft`、`estimated_z_ft`、`sync_error_ms`、`reprojection_error_cam1_px`、`reprojection_error_cam2_px`、`epipolar_residual_px`、`geometry_quality`、`confidence`
- **AND** `source` SHALL 为 `dual_view_estimated`

#### Scenario: 单视角不可用
- **WHEN** 某 tick 只有单一视角观测到球
- **THEN** 该 tick SHALL 不产生双视角立体测量
- **AND** 由分层降级或短 gap prediction 处理

### Requirement: 球侧更严格的时间门
系统 SHALL 为球链保存 `stereo_time_delta_ms`（两摄真实曝光差），并使其实际影响 association quality、3D confidence 与 speed eligibility，而非仅作为 diagnostics。时间处理 SHALL 不做先二维内插，保留每个真实 observation 的 `source_timestamp_ms`。

#### Scenario: 高速球曝光差降级
- **WHEN** 两摄真实曝光差较大（如 20ms）且球速高
- **THEN** 该测量 `stereo_time_delta_ms` SHALL 进入关联质量与 3D 置信度计算
- **AND** speed/height 的 confidence SHALL 相应下降

#### Scenario: 各自真实观测时刻回投
- **WHEN** 双视角源帧曝光时刻不同
- **THEN** 系统 SHALL 保留 Cam1@t1 与 Cam2@t2 各自真实时刻，不做先二维内插
- **AND** 三角测量 SHALL 生成时间约在 canonical/midpoint 的 approximate stereo initialization
- **AND** 最终段优化 SHALL 在每个摄像机自己的 `source_timestamp_ms` 时刻做回投（而非强制同时曝光）

### Requirement: P2 perception 仅消费 available 帧
系统 SHALL 使球检测/跟踪/立体仅消费 `frame_status == "available"` 的源帧；`available_extrapolated` 只用于 Debug Replay，不得进入球链。

#### Scenario: 外推帧不进立体
- **WHEN** 某 canonical tick 的 Cam2 为 `available_extrapolated`
- **THEN** 该帧 SHALL NOT 用于球检测/跟踪/跨视角关联/三角测量
- **AND** SHALL NOT 因"画面可显示"而被当作双摄证据

### Requirement: 单视角缺口仅作预测不作权威
系统 SHALL 在双视角证据不足的短缺口允许预测，且预测样本 `source = predicted`，不得冒充 detection，也不得作为 landing / speed / peak-height 的权威依据。缺口阈值使用独立参数 `ball_stereo_prediction_max_gap_ms`（不复用球员 short-gap 时长）。

#### Scenario: 短缺口预测标注
- **WHEN** 短时序缺口（同一球、同一 segment、gap ≤ `ball_stereo_prediction_max_gap_ms`，第一版约 200ms）内仅单视角可观测
- **THEN** 该缺口球位 SHALL 标记 `source = predicted`
- **AND** 不得作为落点权威、球速权威或最高点权威

### Requirement: 立体证据产物不可变
系统 SHALL 输出不可变的 `multiview_ball_stereo_evidence.v1` 产物，保存两路候选、配对、立体测量与回投诊断，供审计与后续重建引用。

#### Scenario: 证据产物结构
- **WHEN** 系统写入立体证据
- **THEN** 产物 SHALL 包含两个视角的候选列表、跨视角配对、`BallStereoMeasurement` 列表与 reprojection diagnostics
- **AND** 文件名 SHALL 为 `multiview_ball_stereo_evidence.json`
- **AND** 产物为不可变原始证据，不得被后续重建覆盖