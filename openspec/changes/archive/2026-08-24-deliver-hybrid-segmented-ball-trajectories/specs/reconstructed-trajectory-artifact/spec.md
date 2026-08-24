## MODIFIED Requirements

### Requirement: 产物新增 v3 多视角估算三维语义
系统 SHALL 通过统一 `reconstructed_ball_trajectory` 概念保存多视角 3D、稀疏双摄锚定 2.5D 与单摄事件锚定 2.5D 段；v1/v2/v3 历史产物 SHALL 保持只读兼容，新产物 SHALL 按段声明 reconstruction mode，而非要求整个任务只有一种模式。

#### Scenario: 新混合产物顶层语义
- **WHEN** 新任务输出混合重建产物
- **THEN** 顶层 SHALL 声明 schema version、3D overall status 与 `display_trajectory_status`
- **AND** 每段 SHALL 声明 `stereo_estimated_3d`、`stereo_anchored_2_5d`、`single_view_event_anchored_2_5d`、`single_view_visual_arc` 或 `unavailable`
- **AND** coordinate semantics SHALL 明确区分 approximate multiview 与 visualization-only 估算

#### Scenario: 历史产物兼容
- **WHEN** 系统读取历史 v1/v2/v3 任务
- **THEN** SHALL 继续通过统一 slug 解析其原有字段
- **AND** MUST NOT 回写或覆盖历史不可变 artifact

### Requirement: 前端按版本降级读取
系统 SHALL 使前端通过统一 `reconstructed-ball-trajectory` slug 读取历史与新产物，并按 schema version、segment reconstruction mode 与 metric eligibility 呈现；专项指标不可用 SHALL NOT 自动隐藏合格的估算展示段。

#### Scenario: v3 三维不可用但 2.5D 段存在
- **WHEN** 产物 3D overall status 为 `UNAVAILABLE` 且 `display_trajectory_status` 可用
- **THEN** 前端 SHALL 展示合格 2.5D 段并标记“估算球路/仅用于可视化”
- **AND** 平均球速、真实最高点和权威落点 SHALL 显示不可用

#### Scenario: 没有任何可显示段
- **WHEN** 三维与 2.5D 段均未通过各自最低门槛
- **THEN** 前端 SHALL 展示可解释空态与关键拒绝诊断
- **AND** SHALL NOT 生成伪造曲线

### Requirement: 分层可用状态写入产物
系统 SHALL 同时记录 3D overall status、`display_trajectory_status`、段级 display level 与指标级 validity，供前端分别控制球路和测量指标。

#### Scenario: 状态组合
- **WHEN** 写入混合产物
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE`
- **AND** `display_trajectory_status` SHALL 为 `available`、`degraded` 或 `unavailable`
- **AND** 每个速度、高度和落点指标 SHALL 自带 validity/reason

## ADDED Requirements

### Requirement: 混合轨迹 provenance 与端点分类
每个 segment 和 sample SHALL 保存来源视角、detected/interpolated/predicted/stereo-anchor provenance、质量、时间范围与端点语义；场外端点 SHALL 保存相对于标准球场和比赛环境的分类。

#### Scenario: 保存可能真实界外的 bounce
- **WHEN** bounce 位于边线外但未被判为环境离群点
- **THEN** endpoint SHALL 保存 `court_location = outside_line`、`outcome_classification = legal_out_candidate`、证据置信度和标定不确定度
- **AND** MUST NOT 将 `legal_out_candidate` 解释为自动比赛判罚
