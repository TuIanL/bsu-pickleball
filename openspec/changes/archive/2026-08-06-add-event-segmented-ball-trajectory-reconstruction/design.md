# 事件切分球轨迹重建 — 技术设计

## Context

### 当前处理链

```
YOLO 球候选
  → BallTracker（SEARCHING/TENTATIVE/LOCKED/LOST 跟踪状态机
     + 动态物理门控 + 静态误检抑制）        [已实现,保持不变]
  → TrajectoryCleaner（孤立跳点剔除 + ≤12 帧线性插值）  [已实现,复用]
  → BounceDetector（滑动窗口规则弹跳检测）   [已实现,复用]
  → 产物: ball_trajectory.json / cleaned_ball_trajectory.json / bounce_events.json
  → 前端 buildBallTrajectoryVisualization
     （按时间间隙>0.55s、平面跳变>12ft 切段 + 统一高度弧线）
  → BallTrajectoryScene（单条 CatmullRomCurve3 样条渲染）
```

### 三个叠加问题与一个隐藏问题

1. 检测点本身有误检、抖动和跳点。
2. 击球、弹地、丢球后的轨迹被错误连接成一条线——**击球事件完全不存在,弹跳事件虽已检出但未参与段结构**。
3. 空中球被当作地面点套单应矩阵:`court_adapter.py` 对每个被接受检测点直接 `image_to_court(point, homography)`,空中球投影天然产生位置偏差(球越靠近相机、高度越高,偏差越大),这是"长弧线横穿球场"的数学根因。
4. **隐藏问题**:前端对每一段统一生成 `z = 4 × peak × progress × (1-progress)`,端点被 clamp 到 progress=0/1,所以**所有段起点和终点被强制落到 z=0**——无论该段实际是击球开始、丢失结束还是跳变切断,都会人为制造"假弹地"和不合理拱形。

根因是分段、拟合、空间重建与高度生成全部发生在渲染端,而渲染端在已被单应投影过的球场点上做样条平滑,Catmull-Rom 不尊重事件边界。

### 约束

- 标定引擎只有 ground homography,没有相机内参/外参 → 无法做真实三维重建与重投影优化。
- pipeline 的球分析上下文只有 `player_motion_pixels`,没有手腕/球拍关键点。
- 现有 `ball-physics-gating`、`ball-track-state-machine` 规格描述的是**跟踪层**,与本 Change 的**事件层**正交,不得污染。
- 系统定位是"运动表现可视化",不是精密三维测量。

## Goals / Non-Goals

**Goals:**

- 让球路页面立即可信:击球/弹地/丢失/回合重置正确切段,段内无折返与尖峰,段端不再被强制当作落地点。
- 建立"事件锚定的 2.5D 视觉重建"作为正式第三套产物,替代前端临时建模。
- 前端退化为哑渲染器:只读取重建结果并按段绘制。
- 处理链、算法、数据契约、前后端接线全部闭合,不依赖相机内参、姿态关键点或完整 Rally 状态机。

**Non-Goals:**

- 重新实现候选关联、物理门控、跟踪状态机(`ball-physics-gating` / `ball-track-state-machine` 需求不变)。
- 完整相机内外参标定、重投影优化。
- 真实三维速度与真实最高点测量。
- RTMPose 手腕/球拍辅助击球检测(事件来源保留 `pose_assisted` 扩展位)。
- 权威 Rally 状态与 `rally_id` 填充。
- 双摄三角测量。
- 过网高度判定、擦网检测等依赖真实高度的能力。

## Decisions

### D1: 事件锚定的 2.5D 视觉重建（两个模型层）

**选择**:在图像坐标完成观测拟合与异常点判断;在球场坐标仅使用可信事件锚点重建展示轨迹。正式命名为 `event-anchored 2.5D visual reconstruction`。

无内参外参时,从拟合后的二维像素轨迹无法唯一恢复真实三维轨迹,因此**不得**称其为"物理三维重建"。

**测量模型(第一层)** — 输入 `image_xy + timestamp + confidence`,输出:

- 鲁棒拟合后的 `u(t)`、`v(t)`(带置信度权重的 Huber 回归;存在严重离群点时先 RANSAC 初始化,固定随机种子保证确定性);
- 异常观测标记;
- 事件发生时刻;
- 观测覆盖率;
- 图像拟合残差 RMSE(像素)。

**展示模型(第二层)** — 输入飞行段起止事件、可信空间锚点、图像拟合结果、飞行持续时间,输出 `court_x(t)`、`court_y(t)`、`estimated_z(t)`。

**空间锚点分级**:

| 锚点类型 | 可信度 | 单应映射 | 语义 |
|---|---|---|---|
| `bounce anchor` | 高(硬锚点) | **无条件可信**(z=0,单应在弹地点精确) | 弹地点 |
| `contact anchor` | 中/低(软锚点) | 仅作软估计,须保存空间不确定度 | 击球点(球仍在空中,不能因其是事件边界就认为映射准确) |
| `raw endpoint` | 弱约束 | 不视为地面位置 | 普通检测段端点 |
| `loss boundary` | 非空间锚点 | — | 丢失边界,不参与空间重建 |

> 只有弹地点可以无条件通过地面单应转换成可信球场坐标。若一个飞行段连一个可靠空间锚点都没有,保留在"原始检测模式",不生成看似准确的三维球场轨迹。

**备选方案**:方案 A 为"球场坐标鲁棒拟合 + 整段统一高度弧线"(简单但继承投影偏差);方案 B(选中)为"图像空间拟合 + 锚点重建"。B 绕开"无相机内参"硬依赖,同时消除空中球投影偏差。

### D2: 启发式击球候选 + 事件仲裁层

**选择**:第一版采用纯启发式 `BallContactEventDetector`,不强接入 RTMPose 手腕关键点。不能只实现"方向反转→击球"(弹地、误检、短时跟踪漂移都会导致相同现象)。

击球候选至少要求:

- 突变前有连续有效观测;
- 突变后有连续有效观测;
- 速度方向变化达到阈值,或速度幅值发生明显变化;
- 拟合前后分别具有较低残差;
- 当前不是长缺失后的首次重新锁定;
- 当前不位于已确认弹地事件的抑制窗口;
- 满足最小事件间隔 refractory period。

事件仲裁层 `BallEventResolver`:同一时间窗口内同时出现击球候选与弹地候选时:

- 已有高可信 bounce → 抑制 hit candidate;
- 明显靠近球员区域且 bounce 证据较弱 → 接受 hit candidate;
- 两者都不充分 → `event_type = ambiguous`,只切段或降低质量,不武断分类。

现有 `player_motion_pixels` 作为弱证据,不作为确定击球的硬条件。事件来源字段:`heuristic / pose_assisted / manual_corrected`(第一版只用 `heuristic`)。

### D3: 事件边界数据硬切段、视觉共享锚点

**语义**:`语义断开:必须;几何断裂:不需要`。

- 弹地前后是两个独立 `flight_segment`(`hit → bounce`、`bounce → hit`),但共享同一弹地点:`segment_01.end_anchor_id == segment_02.start_anchor_id`。前端球路连续到橙色弹地点再从同一点弹起,不出现"球凭空消失"。
- 击球同理:前后是两个不同拟合段,允许速度和方向突变,可共享同一接触位置,不显示空间空隙。
- 只有以下边界需要视觉上真正断开:长时间检测丢失、身份重建但无法证明同一颗球、回合结束、跨越无法解释的数据空洞。短时间缺失用虚线模型预测连接。

**渲染单位**:`一个 flight_segment → 一个独立 geometry`。多个 segment 可共享 endpoint,但**绝不共享同一条样条**。后端已生成足够密集的重建采样点后,前端直接以重建样本构造 line strip(不依赖 Catmull-Rom,避免样条过冲和跨越锚点)。

### D4: 过网约束只作诊断与质量评分

第一版可判断:起止锚点是否位于球网两侧、轨迹是否预计跨越 `y=22ft` 球网平面、跨网大致时间。但**不可靠**判断:真实过网高度、是否高于网带、是否擦网、真实最高点。

定义 `net_crossing_status: not_expected / expected / estimated / implausible / unknown`,只进入 `physical_plausibility_score` 与 `diagnostics`,**不**因估算过网高度不足就删除轨迹或强行抬高轨迹。

### S1: 不构建权威 Rally;Serve 仅作可选上下文重置锚点

不采用"相邻 serve 之间 = rally"(会把捡球/等待/报分时间包含进去,且发球漏检会大范围错误分组)。V1:

- 不生成权威 `rally_id`,不修改 `BounceEvent.rally_id` 语义;
- 高可信 serve event 仅作为可选硬重置边界:关闭此前未结束的飞行段、开启新球路上下文、`boundary_reason = "serve_reset"`。它回答"这里不应再与前面连续连接",而非"系统识别出了一个 Rally"。

切段边界优先级:

```
1. confirmed_hit
2. confirmed_bounce
3. long_tracking_loss
4. high_confidence_serve_reset
5. end_of_stream
```

artifact 保留 `{ "rally_id": null, "context_reset_event_id": "serve_12", "boundary_reason": "serve_reset" }`,后续接入比赛状态机后填充权威 `rally_id`。

### S2: 可配置接触高度先验（不按球场区域硬修正）

`estimated_contact_height` 必须有来源,否则 `hit → bounce`、`bounce → hit`、`hit → hit` 的高度边界无法闭合。但**不**把固定范围当作硬范围,也**不**根据球场区域自动微调(Dink、低位防守、抽球、高压击球接触高度差异大;底线/NVZ 位置不能可靠证明击球高度)。

初始配置:

```yaml
ball_reconstruction:
  default_contact_height_m: 1.10
  contact_height_min_m: 0.45
  contact_height_max_m: 2.40
  contact_height_uncertainty_m: 0.60
```

- `1.10m` 是生成可视化曲线的默认值;`0.45–2.40m` 是合理性裁剪范围(不代表精确测量);`uncertainty` 必须进入质量评分;第一版不按 near/far、底线/NVZ 自动修改高度。
- 后续接入球员 bbox、手腕关键点或球拍检测后,替换为 `player_relative_estimate` / `pose_assisted`。

边界高度规则:

```
hit      → 低可信 contact prior
bounce   → 高度严格为 0
loss     → 高度未知,不把端点强制落到地面
serve    → 按 hit 类型处理,来源标记 serve_prior
unknown  → 不生成伪造的确定高度
```

> 当前前端统一 `4 × peak × p × (1-p)` 的逻辑必须删除——它让所有段端点回到零高度。

### S3: 单调约束的锚点校正（五步）

选中方案 A("锚点校正"而非"两点直线生成"),但升级为单调约束——仅对两端线性偏移不够,pseudo-ground path 可能保留局部折返、弹道视差导致的纵向回退、横向残差过大、锚点间绕行。

**第一步:图像空间鲁棒拟合**。对每个飞行段拟合 `u(t)`、`v(t)`,带检测置信度权重的 Huber 回归;严重离群时 RANSAC 初始化。损失函数在测量空间,**不能使用已失真的 `court_xy`**。

**第二步:生成 pseudo-ground path**。

```python
pseudo_court(t) = homography(image_fit(t))
```

该路径只提供大致运动方向、横向弯曲趋势、时间进度、观测路径形状,不能直接作为最终球场坐标。

**第三步:根据空间锚点建立主轴**。起止锚点 `A0`、`A1`,主轴 `axis = normalize(A1 - A0)`,将 pseudo path 分解为 `longitudinal_progress(t)` 与 `lateral_residual(t)`。

**第四步:纵向进度单调约束**。同一无击球/弹地飞行段内,球不能无事件地沿主运动方向来回折返:

```
longitudinal_progress(t) → isotonic regression 或 monotonic cubic fitting
约束: s(t0)=0, s(t1)=1, ds/dt >= 0
```

这是真正消除"段内折返"的关键。

**第五步:保留但限制横向形状**。横向残差可从 pseudo-ground path 保留,但必须鲁棒平滑、限制最大幅度、限制横向加速度、端点残差逐渐归零。

```python
court_xy(t) = A0 + s(t)*(A1 - A0) + bounded_lateral_residual(t)
```

**锚点数量降级策略**(必须在实现前写死):

| 锚点情况 | 模式 | 规则 |
|---|---|---|
| 双锚点(bounce→hit、hit→bounce、hit→hit、bounce→bounce) | `dual_anchor_warp` | 完整双端锚定重建;bounce 硬锚点、hit 软锚点 |
| 单锚点(bounce→loss、hit→loss、unknown→bounce) | `single_anchor_warp` | 锚点端严格对齐,另一端用 pseudo path 相对位移;只显示有观测支持的区间;越靠近未知端透明度越低;不生成精确终点;总体质量上限受限 |
| 无锚点(loss→loss、unknown→unknown) | `image_only` | `status = insufficient_spatial_anchors`;仅出现在"原始检测/图像拟合调试"模式,不出现在默认球场视图 |
| 锚点距离过小(`< minimum_anchor_distance`) | `local_visual_arc` 或不出段 | 主轴不稳定,不能强行除以极小距离 |

### 正交的状态机架构

跟踪层与事件层是正交概念,**不合并**为一个超大状态机(否则会出现 `LOCKED_FLIGHT`、`LOCKED_POSSIBLE_BOUNCE` 等组合状态爆炸):

- `BallTrackStateMachine`(已有):回答"当前系统是否稳定跟踪到了某颗球?"——负责候选关联、锁定、丢失、重新捕获。
- `BallFlightSegmenter` / `BallEventResolver`(新增):回答"球当前处于哪种运动阶段或发生了什么事件?"——负责击球、弹地、缺失、回合边界。

跟踪层产生观测,事件层消费观测,不反向污染已有跟踪逻辑。

### 高度模型:事件边界感知

不能统一"两端高度都是零"的拱形,按段类型设置边界:

```
hit → bounce   z_start = estimated_contact_height, z_end = 0
bounce → hit   z_start = 0, z_end = estimated_contact_height
hit → hit      z_start > 0, z_end > 0, 中间存在峰值
bounce → loss  z_start = 0, z_end = unknown(仅显示可信区间,末端渐隐)
unknown → unknown  不得伪造完整高度曲线
```

### 产物与接线

重建产物固定为 `reconstructed_ball_trajectory.json`,API slug `reconstructed-ball-trajectory`。

后端接线:`StorageService.reconstructed_ball_trajectory_json_path()` → `routes_analysis.py` Literal 白名单及路径映射 → `AnalysisArtifacts` 新增字段 → `AnalysisPipeline` 在弹跳检测之后写入 → mock/unavailable/skipped 产物。

前端接线:`report.ts` 新增 `ReconstructedBallTrajectoryArtifact` → `analysisClient` 新增 getter → 球路页加载第三套产物 → `ballTrajectoryVisualization.ts` 不再负责正式分段和估高 → `BallTrajectoryScene` 按 `segment.samples` 渲染独立 geometry。

每个重建点携带 `source`(`detected / interpolated / model_predicted / anchor`)与 `confidence`、可选 `reprojection_error_px` / `gap_length_frames`;不能把模型推算点伪装成真实检测点。

### 确定性

同一输入重复运行时,事件 ID、segment ID、重建结果必须确定。RANSAC 使用固定随机种子;无随机过程(cleaner、bounce detector、segmenter、高度模型)本身是确定性的。

## Risks / Trade-offs

- **[R1] 无相机内参,球场空间展示仍是估算** → 通过 `metric_validity: visualization_only` 明示,且质量评分/展示阈值约束"无锚点段不出现在默认视图",宁可少显示也不伪装高可信。
- **[R2] 启发式击球检测有误报/漏报** → 事件仲裁层 + 抑制窗口 + refractory period 收敛;切段优先级中击球 > 弹地,单条误报只影响局部段,不产生全局错误;后续升级 `pose_assisted`。
- **[R3] pseudo-ground path 保留投影偏差** → 单调约束 + 横向残差限制 + 锚点端精确对齐,把偏差限制在段内中部且幅度有界;两个端点(尤其 bounce)精确。
- **[R4] 前端删除 Catmull-Rom 后观感变化** → 用后端密集重建采样点直接构造 line strip,段内天然平滑;虚线语义(interpolated/model_predicted)由前端按 `source` 样式化。
- **[R5] 新增产物链路改动面广** → 保持第三套数据独立,不覆盖 raw/cleaned;mock/skipped 产物对齐现有 artifact 状态机,避免破坏已归档任务展示。
- **[R6] serve 事件缺失/误检时失去重置锚点** → serve 只是可选增强,基础切段仍靠 hit/bounce/long loss;serve 漏检不影响正确性,只影响"跨回合错误连接"的抑制。

## Migration Plan

1. 后端先落地事件层与重建链(独立于现有 pipeline,可单测/standalone 运行),与 `ball-trajectory-and-bounce-engine` 的 disconnected-from-pipeline 模式一致。
2. 后端写入第三套产物;期间前端仍读旧链路,两套并存(灰度)。
3. 前端切换到重建产物、删除前端分段/估高/Catmull-Rom;回滚策略:前端保留对 `ball_trajectory.json` 的降级读取,重建产物不可用时回退旧渲染。
4. 归档时更新 `ball-trajectory-visualization` 规格需求。
