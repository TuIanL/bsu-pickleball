# Design: Multi-view Player Trajectory Fusion

## Context

仓库已具备双摄录制（`CaptureTake` + 两条 `CaptureTrack`，含 `slot / offset_ms / sync_quality`）与逐机位独立分析（每个机位一个 `AnalysisJob`，单 `video_id` + 单 `calibration_id`）。但探索确认两路球场坐标尚不可直接比较：

1. **坐标系实际方向与文档相反**：四角标定把画面顶部（远端）映射到 `court y≈0`、画面底部（近端）映射到 `court y≈44`，而领域层 `near/far` 判定按 `y<22 = near`。单摄内部自洽，但这是"Local Camera Court Frame"，其语义是 `local y=0 = image-top / camera-far end`。
2. **两路坐标呈约 180° 镜像**：对向机位下，`cam_1` 与 `cam_2` 的 `local y=0` 指向相反物理端，`x` 方向通常也镜像。
3. **物理朝向无记录**：`cameraAngle` 只是 `baseline/sideline/elevated` 拍摄类型；`cam_1/cam_2` 槽位按 stream 配置顺序分配，无任何字段记录"相机在哪个物理端、画面左侧对应哪条边线"。
4. **sync authority 游离**：权威 `dual_camera_sync_calibration.v1`（含 `offset/rate/drift/residual/quality`）由独立脚本产出、写到任意路径，未进入 take 存储契约，`annotation_manifest.json` 恒写 `status=unknown`，无任何 AnalysisJob 消费。
5. **单摄分析强耦合单一视频流**：`AnalysisPipeline.run()` 与 `_run_tracking()` 全部状态围绕一个 `VideoCapture`，不应改造为双流同步执行。
6. **多视角分析没有所有者**：两个独立 AnalysisJob 跑完后，"谁等待、谁执行融合、fused artifact 存在哪"均无契约——这是实施前最需要补的硬契约。
7. **Spike 数据源与质量模型的真实契约**（已核验代码）：`player_render_trajectory.v2` 的 sample 字段为 `frame_index / timestamp_seconds / x_ft / y_ft / source / confidence / player_id / render_slot / side / segment_id / identity_epoch / source_track_id / projection_status / projection_confidence / footpoint_method`。**`source ∈ {"observed", "interpolated"}`**（不是 "detector"/"detected"），**无 `bbox` 字段**，`x_ft/y_ft` 为 raw（未平滑），`confidence` 为观测置信度。

## Goals / Non-Goals

**Goals:**
- 在两路独立单视角结果之上，建立 Multi-view Player Trajectory Fusion Layer，产出单一全局球员轨迹，且**由 `MultiViewFusionRun` 明确持有运行所有权**。
- 显式建立 Canonical Physical Court Frame 并**持久化**（`CanonicalCourtFrameDefinition`），使两路 local 坐标可归一化到同一物理坐标系比较。
- 将 `dual_camera_sync_calibration.v1` 提升为 Multi-view 输入的权威时间同步来源，冻结 **Canonical Timeline**（reference analysis-frame timeline + pairing tolerance），定义 `good / degraded / unknown` 门控。
- 用确定性规则（非训练模型）实现跨视角关联与观测质量评估，先验证"近端机位能否改善远端轨迹"这一核心假设。
- 保持现有单视角 Pipeline 与 artifact 完全不动，additive 迁移。

**Non-Goals:**
- 不修复或重定义现有单摄 `near/far` 语义；历史 local coordinate 视为既成输入协议。
- 不把单视频 AnalysisJob 改造成混合对象。
- 不重写 `PersonDetector / MultiObjectTracker / PlayerLockManager / PlayerIdentityManager`。
- 不把两路视频塞进 `_run_tracking()` 同步逐帧执行。
- 不支持任意 sideline / 轴交换标定视角（P0 仅 axis-preserving）。
- 不做跨视角 ReID、3D Pose、3D 球轨迹。
- 不做实时在线融合（P0 为赛后离线分析）。

## Decisions

### 1. 两级球场坐标系，端点用物理命名

**Decision**：引入两级坐标系，`Legacy / Local Camera Court Frame`（现有单摄语义，`local y=0 = image-top / camera-far end`）与 `Canonical Physical Court Frame`（端点命名 `end_a`（canonical y=0）/ `end_b`（canonical y=44），边线命名 `sideline_a`（canonical x=0）/ `sideline_b`（canonical x=20））。Fusion 层只消费 canonical 坐标。

**Rationale**：`near/far` 在两级坐标里含义不同（单摄里相对相机，canonical 里相对物理端），混用必然再次踩坑。改用 `end_a/end_b` 消除歧义。历史 artifact 不重解释，避免爆炸半径扩散。

**Alternative considered**：以 `cam_1` 坐标系作为 canonical，`cam_2` 相对归一。缺点：canonical 语义绑定到具体机位，换主摄即全局翻转，可迁移性差。已否决。

### 2. `CanonicalCourtFrameDefinition` 持久化，不随次分析重选

**Decision**：canonical 帧定义由操作者首次配置后持久化为独立记录：

```text
CanonicalCourtFrameDefinition
    frame_id
    capture_take_id / court_setup_id
    end_a_definition
    end_b_definition
    created_at
    schema_version
```

同一 take 的多次分析 MUST 引用同一 `frame_id`，不得每次重新选定端点。

**Rationale**：否则同一 take 今天 `end_a=北端`、明天 `end_a=南端`，两次 artifact 整体翻转却都自称 canonical，无法比较。这是数据合同，不是算法参数，必须在 Design 冻结。

### 3. `CourtOrientation` 用 4 元素显式枚举，`None = 未声明`

**Decision**：

```python
CourtOrientation = Literal[
    "identity",      # (x, y) -> (x, y)
    "rotate_180",    # (x, y) -> (20 - x, 44 - y)
    "mirror_x",      # (x, y) -> (20 - x, y)
    "mirror_y",      # (x, y) -> (x, 44 - y)
]

court_orientation: CourtOrientation | None   # None = 尚未声明
```

不引入第五个 `"unknown"` 朝向值；未声明用 `None` 表示。`court_orientation` = 该 view 的 Local Camera Court Frame → Canonical Physical Court Frame 仿射变换。

**Rationale**：四角标定把两路都贴到同一组标准关键点，local frame 恒为轴对齐，故变换只可能是矩形二面体群的 4 个元素。枚举化消除数学术语歧义，且每个值可单测。**示例**：相机位于 `end_a`、画面左侧对应 `sideline_a` 时，`local y=0 = end_b`，故需 `mirror_y` 把近端（local y=44 = end_a）送回 canonical y=0；相机位于 `end_b` 时通常为 `mirror_x`；两路之间恰好相差 `rotate_180`。

### 4. P0 仅支持 axis-preserving 标定视角

**Decision**：`court_orientation` 四元素只对保轴（local x/y 不交换）标定成立。P0 声明支持范围：对向底线机位、底线类高位机位；不保证任意 sideline 朝向或 local x/y 轴交换的标定，超出范围按不支持处理（job-level fallback 或拒绝）。

**Rationale**：为"通用"直接设计 8 元素甚至自由矩阵，需要额外推导轴交换后的区域/身份语义，P0 无此场景。收缩范围避免设计过度。以后支持任意机位再扩展 orientation contract。

### 5. `court_orientation` 挂 `MultiViewViewInput`，不挂 `CaptureTrack`

**Decision**：`court_orientation` 属于 `CaptureTrack + Calibration` 的绑定关系，而非轨道自身。结构：

```text
MultiViewViewInput {
    capture_track_id
    video_id
    analysis_job_id
    calibration_id
    court_orientation
}
```

`MultiViewFusionRun` 持有两个 `MultiViewViewInput`。

**Rationale**：同一 track 重新标定（calibration_A / calibration_B）时 orientation 可能改变；放 Track 上会污染媒体语义，放 view input 上与 Late Fusion 更一致。

### 6. `MultiViewFusionRun` 运行实体与产物所有权

**Decision**：新增运行实体，明确三件事：

```text
MultiViewFusionRun {
    capture_take_id
    source_analysis_job_ids[]        # 谁等待：Run 编排者等待两路 source job 完成
    view_inputs[]                    # 两个 MultiViewViewInput
    sync_calibration_ref
    canonical_frame_ref
    fused artifacts                  # 谁拥有：fused_player_trajectory.v1 挂 Run 产物目录
}
```

**Rationale**：不把单视频 AnalysisJob 改造成半单摄半多摄混合对象。Fusion 的执行管线、等待与产物归属集中到 Run，下游只依赖 Run 的 fused artifact；fused artifact 不挂 cam_1/cam_2 Job，也不挂 CaptureTake。

### 7. 权威 Sync 进入 take 存储契约并门控

**Decision**：`dual_camera_sync_calibration.v1` 落在 take 存储规划的约定路径 `take_dir/timeline/sync_calibration.json`（与 tasks 保持一致，在此冻结），`annotation_manifest.json` 的 `sync_calibration` 字段在权威 artifact 可用时指向它而非恒写 `unknown`。门控：`good` → 正常融合；`degraded` → 允许融合但降低时间同步权重并输出诊断；`unknown / unavailable` → 禁止伪装为 synchronized fusion，退化到最佳单视角。

**Rationale**：`CaptureTrack.offset_ms` 只有粗粒度 offset，无 `rate/drift/residual`。既有 `fit_affine_calibration / map_reference_time / build_frame_map` 已实现所需数学，P0 消费而不重写。

### 8. Canonical Timeline + pairing tolerance

**Decision**：融合时刻来源冻结为：

```text
Canonical timeline = reference track 的 analysis-frame timeline
```

对每个 `take_timestamp_ms = t`，用 sync mapping 找另一视角最近真实 source sample，并要求 `abs(selection_error_ms) <= max_pairing_error_ms`，否则该视角该时刻 `view_status = unavailable`。`max_pairing_error_ms` 是独立于 `valid interval` 的 pairing tolerance 契约。

**Rationale**：不定义融合时刻来源，就无法回答"secondary-only observation 能否出现""GlobalTrackFilter 的 dt 与 gap 判定""速度计算""A/B GT 对齐""artifact timestamp"。冻结为 reference analysis-frame timeline 最简单，天然保证 reference 侧每帧都有观测，pairing tolerance 显式控制另一侧是否可用。

### 9. GlobalTrackFilter 前置于关联，predict/update 单一状态源

**Decision**：时间滤波 SHALL 前置，形成时序状态循环：

```text
GlobalTrackFilter.predict(t) → predicted global positions
        ↓
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
```

`PlayerPositionFusion` 状态只保留 `dual_observed / single_view_fallback / conflict / unavailable`，**不含 `predicted`**——是否在无观测时刻输出预测点由 `GlobalTrackFilter` 决定。关联/融合使用的 global prediction 统一来自 `GlobalTrackFilter.predict(t)`。

**Rationale**：原设计将 predict 排最后，Association/Fusion 却引用 global prediction，来源不明。若 Fusion 与 GlobalTrackFilter 各自预测一次，会形成双重状态估计（比双重平滑更严重）。

### 10. 拆分 Observation Quality 为 ViewIntrinsicQuality + PairConsistency

**Decision**：

```text
ViewIntrinsicQuality    # 某路自身质量
    detector confidence
    normalized bbox height  (bbox_height / frame_height)
    projection confidence
    footpoint method
    tracking state
    calibration quality
    sync selection error

PairConsistency         # 两路成对关系
    inter-view distance
    residual to predicted global position
    association cost
```

决策输入 = `ViewIntrinsicQuality + PairConsistency + Global prediction`。bbox 使用归一化尺寸（`bbox_height / frame_height`），不使用原始像素面积（不同分辨率/zoom/裁切下不可比）；它是 P0 重要特征之一，具体权重由 Spike/A-B 冻结，而非写死的"主导特征"。

**Rationale**：`cross-view disagreement` 是 pairwise relation，不是单视角 intrinsic quality，混在一起会让"分歧很大"污染"谁更可信"的判定，形成循环。

### 11. 区分 Job-level 与 Sample-level Fallback

**Decision**：两个 fallback 语义 MUST 分离：

- **Job-level**：Run 无法合法启动（任一 view `court_orientation=None`，或 sync authority `unavailable`）→ 不生成 fused artifact，下游继续消费单摄 artifact。
- **Sample-level**：Run 合法但某时刻某路 `unavailable` → 该 fused sample `fusion_status = single_view_fallback`，Run 继续。

**Rationale**：orientation 未知时连该单摄点都无法转 canonical，此时 fallback 是"整个分析不可行"；而单时刻单路丢失是"分析内部降级"。混用会导致 diagnostics 与前端语义混乱。

### 12. 下游接线受 metric eligibility 约束

**Decision**：fused sample 携带 `measurement_source` 与 `metric_eligible`：

```text
dual_observed        → metrics yes
single_view_fallback → metrics yes
conflict             → 取决于是否接受某一路真实 observation，必须带 metric_eligible 标志
predicted            → visualization yes；movement / heatmap 默认 no
unavailable          → no
```

**Rationale**：否则连续丢失后 Kalman/EWMA 预测出的轨迹会被算进"真实移动距离"，污染 movement / speed / heatmap。

### 13. 复用 `CourtPositionSmoother` 模式做 GlobalTrackFilter

**Decision**：`GlobalTrackFilter` 复用现有 `CourtPositionSmoother` 的 EWMA + outlier（raw 帧间位移判定）+ gap（stride 感知）模式，按 `global_player_id` 维护状态，并增加 `predict(t)` / `update(measurement)` 接口。不引入新滤波算法。

**Rationale**：该 smoother 已修复抽帧 stride 导致的 gap 误判（`frame_stride` 感知），逻辑聚焦球员球场坐标平滑，与 fused trajectory 场景匹配。超参先复用单摄默认值，A/B 后再定。

### 14. Spike 数据源按真实契约冻结

**Decision**：Spike Adapter 读取 `player_render_trajectory.v2`，过滤 `source == "observed"`（已核验枚举，**不是 "detector"/"detected"**），使用其 raw `x_ft/y_ft` 与 `projection_status / projection_confidence / footpoint_method / source_track_id`。由于 render v2 **无 `bbox` 字段**，Spike 第一轮的 ViewIntrinsicQuality 不使用 bbox；如 A/B 表明 bbox 特征必要，再通过 `source_track_id + frame_index` 与 detection/trajectory artifact join 恢复，或下沉正式 raw observation 契约。

**Rationale**：先验证三个核心假设——(a) 两路 canonical 化后同一球员空间接近；(b) association 稳定；(c) 近端机位确实改善远端轨迹。假设成立后再把 Spike adapter 下沉为正式 Raw Observation Contract，避免为一个未验证的算法先铺正式产物契约。

**Trade-off**：render artifact 是局部平滑后的渲染产物，Spike 阶段需严格丢弃 `source != observed` 点避免"插值点互相证明"；无 bbox 导致质量特征暂缺一项，可接受（Spike 目标只是验证算法价值）。

## Risks / Trade-offs

- **`court_orientation` 声明错误（用户填错）** → 融合结果整体镜像。Mitigation：声明界面提供"哪一端是 end_a"可视化确认 + 融合前用两路近端机位各自高置信观测做交叉一致性 sanity check（如 canonical 距离中位数超阈值则报警，不静默融合）。
- **`side` 字段被未来代码误用** → 身份/区域逻辑被反转信息污染。Mitigation：在 fusion 层与规范中显式标注禁用，测试断言 fusion 逻辑不含 `side` 输入。
- **render artifact 已平滑/插值，Spike 直接消费引入双重平滑** → 融合质量被稀释。Mitigation：Spike 严格过滤 `source == "observed"`，A/B 里同时统计 raw vs fused 指标；正式契约改独立 raw observation 管线。
- **Spike 过滤枚举写错** → 所有 sample 被滤光，Spike 静默失败。Mitigation：先核验并冻结 `source ∈ {"observed", "interpolated"}`，加一个"至少有一个 observed sample"的冒烟断言。
- **sync `unknown` 时强行融合** → 错位轨迹。Mitigation：`unknown` 硬回退单视角（job-level），并把"无 sync artifact ≠ offset_ms=0"设为测试硬断言。
- **预测点污染移动指标** → 真实移动量虚增。Mitigation：`metric_eligible` 契约（决策 12），predicted 不进 movement/heatmap。
- **A/B GT 循环验证** → 评价不独立。Mitigation：GT 不依赖被评估的同一套 Homography；identity switch GT 含 `global_player_id`；不用事后 oracle baseline。
- **A/B 实验成本**：人工标注同步帧真实脚点工作量大。Mitigation：限定标注窗口（抽选已知球场线附近帧），指标聚焦 RMSE / 缺失率 / 冲突率 / ID switch。
- **时间轴分段（录制重连）**：`dual_camera_sync_calibration.v1` 的 `valid_start/valid_end` 只覆盖参考时间轴区间。Mitigation：融合层按 `TrackTimelineSpan` 语义处理区间外时间，标记 `unavailable` 而非外推。

## Migration Plan

1. **数据**：新增 `CanonicalCourtFrameDefinition`（canonical 帧定义持久化）；`MultiViewViewInput.court_orientation` 默认 `None`（历史 view 不填）；`annotation_manifest.sync_calibration` 在权威 artifact 可用时指向 `timeline/sync_calibration.json`，否则维持 `unknown`。`CaptureTrack` 不改（orientation 不落 Track）。
2. **代码**：全部新增模块与现有单视角 pipeline 并列，不改任何现有 artifact 读写；`AnalysisJob` 契约不变。
3. **回滚**：删除 Fusion 层（`MultiViewFusionRun` 及模块）即恢复现状，无数据迁移成本。
4. **验证**：四组 A/B——`single cam_1` / `single cam_2` / `configured default view` / `multiview fused`，对比 `RMSE / 缺失率 / 异常跳点率 / 跨视角冲突率 / identity switch / 连续覆盖`，分近端/远端区域（重点 far-side subset）统计。

## Open Questions

仅保留算法参数类问题，交由 Spike/A-B 冻结（数据合同类已在 Design 冻结）：

1. **GlobalTrackFilter 超参**：`max_speed_ft_s / max_gap_frames / alpha` 复用单摄默认值，还是融合场景单独调参？倾向先复用默认，A/B 后再定。
2. **conflict 阈值**：`conflict` 状态下"选高质量单视角" vs "用全局预测 hold" 的分界阈值，需在 Spike 数据上标定。
