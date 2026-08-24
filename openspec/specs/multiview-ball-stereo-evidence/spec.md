# multiview-ball-stereo-evidence Specification

## Purpose
TBD - created by archiving change add-multiview-3d-ball-reconstruction. Update Purpose after archive.
## Requirements
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

### Requirement: 生产 joint 球链路消费 canonical evidence
生产 joint 球链路 SHALL 使用 canonical tick 的双摄 frame bundle 与共享候选生成 evidence。离线 `real_data_runner` 可作为调试或回归入口，但不得作为绕过主编排、独立解码或独立 detector 的正式发布路径。

#### Scenario: 正式 joint 运行
- **WHEN** 用户提交 joint 双摄任务
- **THEN** evidence 生成 SHALL 记录 canonical clock 与 source frame decision
- **AND** 正式路径 SHALL 不再通过两个独立 detector/读取循环生成可发布证据

#### Scenario: 离线回归运行
- **WHEN** 测试或调试直接调用离线 runner
- **THEN** runner 输出 SHALL 明确标记为 offline/debug context
- **AND** 不得被误当作已完成 Parent 的正式 artifact

### Requirement: evidence 的帧选择与时间配对严格一致
双摄 evidence SHALL 只使用实际可用帧；两路观测的配对 SHALL 使用统一时间单位和显式阈值，超出时间门的观测 SHALL 不得生成 stereo measurement。每个 measurement SHALL 保留两路真实 timestamp 与 frame index。

#### Scenario: 时间差在门限内
- **WHEN** 两路观测的真实时间差不超过配置门限
- **THEN** 系统 SHALL 允许生成该 tick 的 stereo measurement
- **AND** SHALL 记录时间差与门限结果

#### Scenario: 时间差超过门限
- **WHEN** 两路观测时间差超过球侧严格时间门
- **THEN** 系统 SHALL 拒绝该 stereo 配对
- **AND** SHALL 在统计中记录 unmatched / rejected 原因

### Requirement: evidence 记录三角测量几何质量
每个可用 stereo measurement SHALL 尽可能记录三角测量射线夹角、重投影误差、深度/空间范围检查与质量等级；缺少必要几何质量时，用户轨迹不得将该点标为高可信三维点。

#### Scenario: 几何质量达标
- **WHEN** 射线夹角、重投影误差与空间范围均满足阈值
- **THEN** measurement SHALL 标记为可用于高可信三维重建
- **AND** v3 SHALL 能引用该质量等级

#### Scenario: 几何质量不达标
- **WHEN** 射线夹角过小或重投影误差过大
- **THEN** measurement SHALL 保留在审计 evidence 中但标记为低质量/无效
- **AND** 不得无标记地进入权威三维轨迹

### Requirement: evidence 文件发布后不可变
正式发布的 `multiview_ball_stereo_evidence.v1` SHALL 在生成后保持内容不可变，后续轨迹重建或页面读取 SHALL 通过引用消费。重跑 SHALL 生成新的版本化任务 artifact，不得原地覆盖已完成任务的 evidence。

#### Scenario: 页面读取 evidence
- **WHEN** 前端或调试工具读取已完成任务的 evidence
- **THEN** 读取结果 SHALL 与 Composer 发布时一致
- **AND** 不得因页面加载改变 evidence 内容

#### Scenario: 任务重跑
- **WHEN** 用户对同一输入重新运行分析
- **THEN** 系统 SHALL 生成新任务作用域的 evidence
- **AND** 原任务 evidence SHALL 保持可复现

### Requirement: 跨视角关联消费时序连续性
跨视角 associator SHALL 消费基础视觉过滤后的共享候选集合、两个本地 tracker 的 pre-tick 预测快照、上一可信 3D 路径连续性与当前飞行段上下文，MUST NOT 将连续性参数长期保留为默认零值。

#### Scenario: 原始候选包含真球和静态误检
- **WHEN** 一个视角同时包含真球与静态高置信候选，另一视角只有真球候选
- **THEN** associator SHALL 结合 tracker 预测、尺度/运动一致性和几何残差选择真球配对
- **AND** 选择结果及各评分分量 SHALL 写入 evidence

#### Scenario: 高残差配对仍通过宽松空间门
- **WHEN** 候选配对虽位于比赛环境范围内但回投或 epipolar 残差超过高可信阈值
- **THEN** evidence SHALL 保留该配对用于审计并标记低质量
- **AND** 该配对 MUST NOT 成为高可信 stereo anchor、速度或最高点依据

### Requirement: stereo evidence 按飞行段组织
系统 SHALL 将配对观测、单视角观测与 stereo measurement 关联到具体 `segment_id`，使三维增强只在同一飞行段内发生。

#### Scenario: 分析窗口包含多拍
- **WHEN** canonical evidence 跨越多个 hit/bounce 边界
- **THEN** 每个 observation 和 measurement SHALL 关联一个 segment 或明确标记为待分配
- **AND** 后置重建 MUST NOT 把不同 segment 的观测送入同一曲线优化

#### Scenario: 仅有稀疏双摄重叠
- **WHEN** 同段只在少数时刻具有合格的 stereo measurement
- **THEN** 合格 measurement SHALL 作为稀疏 anchor 参与该段重建
- **AND** 同段连续单视角观测 SHALL 保留为图像回投约束

