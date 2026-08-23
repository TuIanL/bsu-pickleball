## Context

当前 joint 双摄球链在 `CanonicalAnalysisClock` 的 tick 上各运行一次 detector，但随后直接对两个视角的原始候选做跨视角笛卡尔积关联，并在分析结束时将整个窗口的全部单摄/双摄观测交给唯一的 B-spline 段。真实样本中 1815 个 canonical tick 仅产生 26 个 stereo measurement，重投影误差约 197.5px，却有 1572 个已被本地 tracker 接受的单摄观测；这些单摄证据没有被组装成可交付的逐拍球路。

仓库已有 `BallContactEventDetector`、`BallEventResolver`、`BallFlightSegmenter`、事件锚定 2.5D 重建、质量评估以及 Three.js 球场渲染，但 canonical v3 主链没有复用分段链路。现有前端还在 v3 `UNAVAILABLE` 时禁止回退 2.5D，这符合旧规范，却不符合“优先看到明确标注的近似球路”的新产品目标。

历史产物还暴露两个实现问题：stride=2 时击球检测用相邻 frame index 差必须为 1，导致击球候选为零；单锚点重建无论锚点位于哪一端都把第一个有效点对齐锚点。弹地坐标越过标准边线也不能被直接视为误检，因为比赛中的球确实可能出界，且球在击打前后允许处于场地矩形外。

## Goals / Non-Goals

**Goals:**

- 每个真实飞行段独立生成球路，禁止跨击球、弹地和回合连接。
- 在双摄配对稀疏时仍从连续单摄观测交付可读的估算 2.5D 弧线。
- 让双摄证据成为段级增强和校正，而不是逐帧发布前提。
- 在视频、球路页和报告中复用同一版本化轨迹与事件语义。
- 区分真实界外落点、正常场外飞行、标定不确定和环境离群误检。
- 保持所有估算值的 provenance、quality 和 metric eligibility 可审计。

**Non-Goals:**

- 不承诺第一版输出真实瞬时球速、真实旋转或毫米级三维位置。
- 不要求更换现有 YOLO 权重，也不把训练新模型作为交付前置条件。
- 不根据一条估算轨迹自动裁决比分、犯规或界内/界外结果。
- 不修改历史已完成任务的不可变原始 evidence；重跑产生新版本任务。

## Decisions

### 1. 采用“事件切段优先”的统一球路编排

canonical processor 将保存每视角经过基础过滤和 tracker 接受的时序观测。事件层以 hit、bounce、serve reset、长丢失和 end-of-stream 建立边界，之后每个 `FlightSegment` 分别完成视角选择、跨视角增强和重建。

选择该方案是因为球的物理连续性只在一次飞行内成立。继续增加整窗 B-spline control points 虽可能降低总体残差，却仍会跨多拍连接，并产生不可解释的速度和高度。

### 2. 连续性使用时间语义，不使用固定帧差

所有 hit 上下文、重新锁定、短缺口和 refractory period 使用 `timestamp_sec` 或由 effective FPS 与 frame stride 推导的容差。frame index 仅用于定位原视频帧和确定性排序。

这同时支持 30/60 FPS、stride 1/2/更大值以及两路不同的真实曝光时刻，避免把合法抽帧当成长缺失。

### 3. 主视角按飞行段动态选择

每段分别计算两视角的有效观测覆盖、平均置信度、拟合残差、静态误检比例、预测比例、球框尺度趋势和遮挡情况。球飞向某摄像头所在半场时，可见性更好的该视角通常成为主视角；具体选择以评分为准，而不是硬编码固定方向。

另一视角提供三类增强：事件时间验证、短缺口观测补充、可信 stereo anchor。若两路评分接近且可关联证据充分，则运行段级 3D 优化；否则使用主视角 2.5D。

### 4. 使用稀疏双摄锚点，不要求逐帧配对

跨视角关联消费基础过滤后的候选集合，并使用 pre-tick tracker 预测、候选尺度/方向、上一可信 3D 路径和同段时间范围评分。高残差配对可保留在审计 evidence，但不能成为高可信锚点。

段级优化在每个摄像机自己的真实观测时刻做回投。stereo measurement 只负责初始化或锚定，单视角观测仍可约束同段曲线。

### 5. 混合重建按段降级

每段选择以下模式之一：

1. `stereo_estimated_3d`：双摄覆盖和几何质量达标。
2. `stereo_anchored_2_5d`：只有少量可信 stereo anchor，其余由主视角轨迹约束。
3. `single_view_event_anchored_2_5d`：只有一个连续主视角和至少一个事件/空间锚点。
4. `single_view_visual_arc`：无可靠空间端点但有连续图像轨迹，仅用于视频或低可信展示。
5. `unavailable`：没有满足最低连续性和物理合理性的段。

2.5D 高度使用端点感知二次弧：bounce 为 0，hit/serve 使用低可信接触高度先验，loss/unknown 不强制落地并渐隐。所有 2.5D 模式标记 `metric_validity=visualization_only`，不得开放真实最高点或三维球速。

### 6. 场外判断采用两级边界和多证据分类

标准比赛场地矩形用于产生 `in_court`/`outside_line` 事实，不作为删除门。其外增加可配置 `play_environment_bounds`，覆盖底线外发接发空间、边线外救球空间和缓冲区。

- 在标准边线外但仍处于比赛环境内、轨迹连续且端点证据充分：保留为 `legal_out_candidate`；该名称只表示可能的真实界外落点，不自动裁决。
- 位于比赛环境外但可由标定不确定度解释：标记 `calibration_uncertain`，降低质量。
- 严重超出环境边界，同时伴随静止、跳变、反向投影残差或另一视角不支持：标记 `environment_outlier` 并拒绝。

这种设计避免把真实出界球删除，也避免为了“允许界外”而放行观众席、广告牌等静态误检。

### 7. 单一 artifact 驱动三种呈现

升级重建 artifact，保存 segment、shot、endpoint、sample provenance、每视角图像拟合、court path、estimated height、quality 和 metric eligibility。

- 视频页使用对应视角的 image-space samples/fit 绘制尾迹，播放中显示当前段，段结束后保留可配置时间。
- 球路页使用 court path + height 绘制交互式弧线。
- 报告页复用相同段和事件锚点，提供击球、弹地、可能界外和未知终点标记。

禁止前端自行从不同 artifact 重新切段，以免视频、球路页和报告出现不同拍数。

### 8. v3 状态与展示状态解耦

保留 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY`、`UNAVAILABLE` 表达真实双摄三维能力，同时增加任务级 `display_trajectory_status`。v3 为 `UNAVAILABLE` 时，只要存在合格 2.5D 段，页面仍为 `display_trajectory_status=available/degraded`。

质量门按指标生效：它可以关闭 speed、peak height、authoritative landing，却不能删除已经达到可视化门槛并清楚标注来源的估算弧线。

## Risks / Trade-offs

- [估算弧线可能被用户误认为真实三维] → 页面持续显示“估算球路/仅用于可视化”，按采样来源使用实线、虚线和透明度，隐藏无资格指标。
- [错误的 bounce/hit 会造成错误切段] → 事件保留置信度和冲突状态；低可信事件只作候选边界，结合长丢失、另一视角和球员接近度复核。
- [真实界外与误投影难以完全区分] → 不做自动判罚，保存标准边界、环境边界、标定不确定度、时序连续性和跨视角支持，让结果可审计。
- [动态主视角可能频繁切换] → 选择以完整飞行段为单位，并使用滞回阈值；段内不切换主视角，只允许另一视角补充证据。
- [时序增强增加运行时间] → detector 保持每视角每 tick 一次；后续阶段消费缓存候选和降采样 control points，不重复解码或推理。
- [历史产物字段不足] → 历史 v1/v2/v3 继续只读兼容；仅新任务生成混合字段，不原地迁移不可变 evidence。

## Migration Plan

1. 先扩展 schema、解析器和 feature flag，使新旧产物可并存。
2. 修复 stride 时间语义与单锚点对齐，增加针对历史真实样本的回归测试。
3. 在 canonical 流中记录过滤后候选与单摄观测，接入事件分段但暂不替换旧发布结果。
4. 并行生成旧 v3 与新 hybrid artifact，对比段数、事件、残差和人工抽检结果。
5. 达到验收阈值后切换 composer 和前端读取顺序，新 hybrid artifact 成为视频/球路/报告权威展示源。
6. 保留运行时开关以回滚到旧 v3 读取；回滚不删除新任务 evidence。

## Open Questions

- `play_environment_bounds` 的默认缓冲距离需要用更多真实界外球和观众席误检样本标定。
- 主视角评分中“球框尺度趋势”和“球飞向摄像头”的权重需要离线回归确定。
- 视频中已结束球路的默认保留时长，以及同时显示最近多少拍，需要通过可读性测试确定。
- 第一版是否将 `single_view_visual_arc` 默认显示在球路报告，或仅在用户开启“低可信估算”后显示。
