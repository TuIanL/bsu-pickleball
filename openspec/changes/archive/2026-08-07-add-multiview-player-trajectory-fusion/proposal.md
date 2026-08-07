# add-multiview-player-trajectory-fusion

## Why

当前双摄录制已经能为同一 `CaptureTake` 保存两条独立 `CaptureTrack`，并分别完成视频注册、场地标定与单视角分析，但两条视频仍作为独立 AnalysisJob 处理，分析结果之间不存在协同关系——双摄目前只实现了"两个角度分别分析"，没有发挥多视角互补价值。

在实际固定对向机位中，同一名球员通常在一个视角处于远端（像素尺寸小、检测与脚点投影质量低），而在另一视角处于近端（观测质量明显更高）。当前系统无法用后者修正或补偿前者，最终球员球场轨迹仍受单一摄像头远端模糊、遮挡、投影误差和短时检测失败影响。

探索进一步确认：两路单视角球场坐标还不能直接比较。现有四角标定实际产生 `local y=0 = 摄像机远端`、`local y=44 = 摄像机近端`；当两台摄像头位于球场相反端时，同一物理点在两路中形成约 180° 对称坐标。同时，已有 `dual_camera_sync_calibration.v1` 能表达跨机位 `offset / rate / drift / residual / quality`，但尚未成为 `CaptureTake` 或分析任务的正式输入契约，缺少权威共同时间轴。

本 Change 建立一层独立于现有单视角 `AnalysisPipeline` 的 **Multi-view Player Trajectory Fusion Layer**：由新实体 `MultiViewFusionRun` 持有两次单视角分析，将两路观测映射至统一时间与统一物理球场坐标，执行跨视角身份关联、观测质量评估与二维位置融合，生成一个全局球员轨迹。

## What Changes

### 1. 建立 Canonical Court Frame Contract

引入两级球场坐标系，避免继续混淆"near/far 相对于谁"：

```text
Legacy / Local Camera Court Frame
        ↓ CourtOrientation
Canonical Physical Court Frame
```

- **Legacy / Local Camera Court Frame**：现有单视角体系沿用当前 local coordinate 行为，其语义限定为 `local y=0 = image-top / camera-far end`、`local y=44 = image-bottom / camera-near end`。本 Change 不修改现有 near/far 侧判定，不重解释历史 artifact。
- **Canonical Physical Court Frame**：Fusion 层使用独立的物理球场坐标系，端点命名采用 `end_a / end_b`（或 `canonical_y_min / canonical_y_max`），**不再使用 `near/far` 作为端点名称**。每个 take 的 canonical 定义由操作者首次配置后**持久化**（`CanonicalCourtFrameDefinition`），不得每次分析重新选定，避免同一 take 两次分析整体翻转。

**P0 支持范围**：本 Change 仅保证 axis-preserving（保轴）标定视角——典型为对向底线机位、底线类高位机位；不保证任意 sideline 朝向、不保证 local x/y 轴发生交换的标定。超出范围的多视角输入按不支持处理。

每条参与多视角分析的 `MultiViewViewInput` 必须携带 `court_orientation`，表示该 view（CaptureTrack + Calibration）的 local→canonical 变换：

```python
CourtOrientation = Literal[
    "identity",      # (x, y) -> (x, y)
    "rotate_180",    # (x, y) -> (20 - x, 44 - y)
    "mirror_x",      # (x, y) -> (20 - x, y)
    "mirror_y",      # (x, y) -> (x, 44 - y)
]

court_orientation: CourtOrientation | None   # None = 尚未声明
```

Multi-view Fusion 只允许消费经过 Canonical Court Normalizer 转换后的坐标。

### 2. 新增 MultiViewFusionRun 运行实体

**不把单视频 AnalysisJob 改造成半单摄半多摄的混合对象。** 两路单视角分析各自保持单 `video_id` + 单 `calibration_id` 的 AnalysisJob；新增独立的运行实体 `MultiViewFusionRun` 消费它们：

```text
AnalysisJob cam_1 ─┐
                   ├─→ MultiViewFusionRun
AnalysisJob cam_2 ─┘

MultiViewFusionRun:
    capture_take_id
    source_analysis_job_ids[]
    view_inputs[]          # 每个含 track/video/job/calibration/court_orientation
    sync_calibration_ref
    canonical_frame_ref
    fused artifacts        # fused_player_trajectory.v1 归属该 Run
```

它明确回答三个问题：**谁等待两个 source job 完成（Run 的编排者）**、**谁执行 Fusion（Run 的执行管线）**、**fused artifact 存在哪个目录（Run 的产物目录，不挂 cam_1/cam_2 Job，也不挂 CaptureTake）**。

### 3. 将双摄同步校准提升为 Multi-view Input Contract，并冻结 Canonical Timeline

Multi-view 分析输入必须引用权威 `dual_camera_sync_calibration.v1`，而非仅依赖 `CaptureTrack.offset_ms`。输入契约至少包含：

```text
reference_camera
offset_ms
rate
drift_ppm
residual_rms_ms
valid interval
sync_quality
```

**Canonical Timeline**：Fusion 的融合时刻来源必须冻结，不能含糊。P0 冻结为：

```text
Canonical timeline = reference track 的 analysis-frame timeline
```

对每个 `take_timestamp_ms = t`，用 sync mapping 找另一视角最近真实 source sample，并要求：

```text
abs(selection_error_ms) <= max_pairing_error_ms
```

否则该视角该时刻 `view_status = unavailable`。`max_pairing_error_ms` 是除 `valid interval` 之外的独立 **pairing tolerance** 契约。

执行策略：

```text
good     → 正常双视角融合
degraded → 允许融合，但降低时间同步质量权重并输出诊断
unknown / unavailable → 禁止伪装为 synchronized fusion，自动退化到最佳单视角轨迹
```

原始视频与单视角分析结果始终保留。

### 4. 区分 View Identity 与 Global Identity

`cam_1 / Player_1` 与 `cam_2 / Player_1` 不具有身份等价关系。新增 `CrossViewPlayerAssociator` 建立：

```text
(view_id, view_player_id)  →  global_player_id
```

P0 不引入 Appearance ReID 模型，优先使用 `canonical court distance / motion prediction / temporal continuity / previous association / physical court constraints` 建立小规模二分图匹配。跨视角关联不得使用现有 artifact 的 `side` 字段作为身份依据（该字段是摄像机相对且物理反转的）。

### 5. 拆分 Observation Quality 为 Intrinsic + Pair Consistency

观测质量拆成两个正交概念，避免 pairwise 关系污染单视角质量评分：

- **ViewIntrinsicQuality**：某一路自身的质量——`detector confidence / normalized bbox height / projection confidence / footpoint method / tracking state / calibration quality / sync selection error`。bbox 使用 `bbox_height / frame_height`（或归一化面积），不使用原始像素面积（不同分辨率/zoom/裁切下不可比）；它是 P0 的重要特征之一，具体权重由 Spike/A-B 冻结，而非写死的"主导特征"。
- **PairConsistency**：两路观测之间的成对关系——`inter-view distance / residual to predicted global position / association cost`。

```text
ViewIntrinsicQuality
       + PairConsistency
       + Global prediction
       ↓
Conflict / Fusion decision
```

### 6. 新增 Position Fusion，预测职责移出

`PlayerPositionFusion` 在同一 canonical timestamp、同一 global player 下融合有效观测，状态只保留：

```text
dual_observed
single_view_fallback
conflict
unavailable
```

**`predicted` 不再属于 Fusion 状态**。是否在无观测时刻输出预测点，由 `GlobalTrackFilter` 决定（见第 7 条），避免"Fusion 预测一次、GlobalTrackFilter 再预测一次"的双重状态估计。Fusion 不采用固定 50/50 平均，按观测质量加权。

### 7. 建立 GlobalTrackFilter predict/update 状态估计循环

时间滤波 SHALL 前置于关联与融合，形成真正的时序状态循环，而非排在最后：

```text
上一时刻 Global State
        │
        ▼
GlobalTrackFilter.predict(t)  →  predicted global positions
        │
        ▼
CrossViewPlayerAssociator
        ↓
ViewIntrinsicQuality
        ↓
PairConsistency
        ↓
Conflict Gate
        ↓
PlayerPositionFusion（measurement fusion）
        ↓
GlobalTrackFilter.update(measurement)
        ↓
新的 Global State
```

关联/融合所用的 "global prediction" 统一由 `GlobalTrackFilter.predict(t)` 产生，单一来源。不得将两路已经大量插值和平滑后的轨迹互相作为独立证据重复平滑。

### 8. 生成 FusedPlayerTrajectoryArtifact

新增版本化 artifact（如 `fused_player_trajectory.v1`），每个 sample 至少记录：

```text
global_player_id
timestamp_seconds
take_timestamp_ms
reference_frame_index
x_ft
y_ft
fusion_status
fusion_confidence
contributing_views
selected_view
view_observations      # 每路: source_frame_index / source_timestamp_ms
                       #       mapped_take_timestamp_ms / selection_error_ms / x_ft / y_ft / quality
association_confidence
sync_quality
court_frame_version
measurement_source
metric_eligible
```

每个 sample 必须能回答：**这个 fused 点由两路哪两个真实帧组成、各帧映射误差多少**。并提供独立 diagnostics artifact，记录 `orientation normalization / frame mapping errors / association decisions / view quality scores / view disagreement / fallback & conflict counts`。

### 9. 区分 Job-level 与 Sample-level Fallback

两个 fallback 语义 MUST 分离：

- **Job-level fallback**：整个 `MultiViewFusionRun` 无法合法启动（任一 view `court_orientation` 未声明，或 sync authority `unavailable`）→ 不生成 fused artifact，下游继续消费原有单摄 artifact。
- **Sample-level fallback**：Run 合法（两路 orientation 已知、sync 已知），但某个时刻某一路 `unavailable` → 该 fused sample 状态为 `single_view_fallback`，Run 继续运行。

### 10. 下游消费 Fused Trajectory 且受 metric eligibility 约束

P0 完成后 `minimap / movement distance & speed / heatmap / court-position visualization` 能够消费 `FusedPlayerTrajectoryArtifact`，但**哪些点允许进入指标**必须有合同：

```text
dual_observed        → metrics yes
single_view_fallback → metrics yes
conflict             → 取决于是否接受某一路真实 observation，必须携带 metric_eligible 标志
predicted            → visualization yes；movement / heatmap 默认 no
unavailable          → no
```

sample 上直接携带 `measurement_source` 与 `metric_eligible`，避免预测/插值点污染真实移动量。现有单视角 artifact 不删除、不覆盖。

## Non-Goals

```text
- 不修复或重新定义现有单摄 near/far 语义。
- 不修改历史 calibration artifact 的坐标含义。
- 不把单视频 AnalysisJob 改造成半单摄半多摄的混合对象。
- 不重写现有 PersonDetector、MultiObjectTracker、PlayerLockManager 或 PlayerIdentityManager。
- 不把两个视频直接塞进现有 _run_tracking() 同步逐帧执行。
- 不支持任意 sideline / 轴交换标定视角（P0 仅 axis-preserving）。
- 不实现跨视角 Appearance ReID 深度模型。
- 不实现多视角人体 3D Pose。
- 不实现匹克球 3D 轨迹或三角测量。
- 不融合球检测、击球动作和 Pose artifact。
- 不要求实时在线融合，P0 为赛后离线分析。
- 不删除现有单摄分析和单视角 fallback 路径。
```

尤其第一条：**P0 将历史 local coordinate 视为既成输入协议，而不是借此 Change 修复整个单摄坐标领域模型。**

## Capabilities

### New Capabilities

- `multiview-fusion-run`: Multi-view 分析运行实体，负责等待 source job、持有 view inputs、执行融合管线与 fused artifact 所有权。
- `multiview-court-frame-normalization`: 两级球场坐标系、`court_orientation` 声明、`CanonicalCourtFrameDefinition` 持久化与 Canonical Court Normalizer（P0 仅 axis-preserving 视角）。
- `multiview-analysis-input-contract`: Multi-view 输入契约，涵盖 sync authority、Canonical Timeline 与 pairing tolerance。
- `multiview-player-association`: 跨视角身份关联，`(view_id, view_player_id) → global_player_id`。
- `multiview-player-trajectory-fusion`: ViewIntrinsicQuality + PairConsistency、位置融合状态机、GlobalTrackFilter predict/update 循环、`FusedPlayerTrajectoryArtifact` 与 metric eligibility。

### Modified Capabilities

无。现有单视角 AnalysisJob 契约（含 `recording-analysis-bridge`）不改变。

## Impact

- **后端**：新增 `MultiViewFusionRun` 及其编排与产物目录；新增 Fusion 层模块（Court Normalizer、CrossViewPlayerAssociator、ViewIntrinsicQuality、PairConsistency、PlayerPositionFusion、GlobalTrackFilter）；`MultiViewViewInput` 携带 `court_orientation`；`dual_camera_sync_calibration.v1` 进入 take 存储契约；新增 `fused_player_trajectory.v1` 与 diagnostics artifact。
- **数据**：历史 view `court_orientation` 默认 `None`（未声明），不猜测；无 sync artifact 时 `sync authority unavailable`，绝不按 `cam_2` 自动填 `rotate_180`。
- **前端**：P0 仅让位置型视图（minimap / heatmap / metrics）可消费 fused trajectory（受 metric eligibility 约束）；单视角产物与视图保留。

## Migration / Compatibility

采用 additive migration。`court_orientation` 挂在 `MultiViewViewInput` 上（`CaptureTrack + Calibration` 的绑定关系），**不写入 CaptureTrack 本身**，避免污染轨道媒体语义。未声明时 `court_orientation = None`（语义为"尚未声明"，不是第五种朝向）。Multi-view run 遇到 `None` 时：进入 orientation resolution，或 job-level 单视角 fallback。**不要根据 `cam_2` 自动填 `rotate_180`**（应成为测试硬断言）。Sync 同理：没有 sync_calibration artifact ≠ `offset_ms=0`，而是 `sync authority unavailable`。

## Recommended Architecture

```text
                         CaptureTake
                             │
             ┌───────────────┴───────────────┐
             │                               │
      AnalysisJob cam_1                 AnalysisJob cam_2
             │                               │
             └───────────────┬───────────────┘
                             ▼
                     MultiViewFusionRun
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
CanonicalCourtFrame    SyncCalibration      ViewInputs[]
        │                    │
        └──────────┬─────────┘
                   ▼
            Canonical Timeline
                   │
                   ▼
        GlobalTrackFilter.predict(t)
                   │
                   ▼
        CrossViewPlayerAssociator
                   │
                   ▼
        ViewIntrinsicQuality
                   │
                   ▼
           PairConsistency
                   │
                   ▼
        PlayerPositionFusion（conflict gate）
                   │
                   ▼
        GlobalTrackFilter.update()
                   │
                   ▼
       FusedPlayerTrajectory.v1
                   │
        ┌──────────┼───────────┐
        ▼          ▼           ▼
     minimap    heatmap      metrics（metric eligibility 门控）
```

Fusion 逻辑拆为 `CrossViewPlayerAssociator` 与 `PlayerPositionFusion` 两个独立概念——"这两个人是不是同一个人"与"确认同一个人后位置怎么融合"是两个独立问题，不得用一个 `FusionEngine` 混在一起。预测职责统一归属 `GlobalTrackFilter`，单一来源。

## Risks

P0 的成功指标不能是"成功生成 fused JSON"，而必须证明 Fusion 相对最佳/默认单视角确实提升球场位置质量。Design 阶段需定义 A/B 指标：

```text
single cam_1  /  single cam_2  /  configured default view  /  multiview fused
```

比较：人工标注球场位置 RMSE、轨迹缺失率、异常跳点率、跨视角冲突率、identity association switch count、可连续轨迹覆盖率。

Ground Truth 必须满足两条独立性约束，避免循环验证：
- identity switch 的 GT 必须包含 `global_player_id`，否则无法统计 ID switch。
- GT 的 court coordinate 不能直接依赖正在被评估的同一套 Homography（如"人工点图像脚点 → 用当前 Homography 投影当 GT → 再评价该 Homography"是循环验证）。P0 采用有限成本独立方案：抽选已知球场线附近帧 + 人工确认物理坐标 + 两视角交叉复核。

**不使用事后 oracle baseline**（每帧知道哪个 camera 更准后再选 best 的 baseline 过强且不真实）。重点验证 `Cam1 far-side subset / Cam2 far-side subset / overall`，这最直接证明"双摄互补"价值。
