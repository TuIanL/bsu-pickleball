## Context

`AnalysisPipeline._run_tracking()`（`backend/app/services/analysis_pipeline.py` 约 1591-2471 行）是单视角球员跟踪的完整实现：视频解码、抽帧、逐帧检测→跟踪→投影→平滑→选择→锁定→身份、球/姿态/调试、产物组装全部内嵌在一个 300+ 行的 while 循环（约 1881-2233 行）里。当前 P1 架构演进（`joint_tracking_v2`）要求 Cam1/Cam2 各跑一路逐帧 tracking；若不先抽出可复用组件，多视角会复制一套 tracking 循环，后续修脚点 / PlayerLock / Selector 时两边漂移。

本 Change 是**行为保护重构**：抽出 `ViewTrackingSession`，单摄输出与重构前完全一致。已确认 `position_smoother`、`_detect_frame`、`_tracks_to_frame_detections` 均只在 `_run_tracking` 内使用，迁移到 session 无外部调用方风险。

关键行为事实（重构必须保留）：`_run_tracking` 在 court-view gate 检查**之前**执行 `processed_frame_count += 1`，因此该计数统计"被 stride 采样且经过 court-view 判断的帧数"，含被 gate 挡掉的帧。

## Goals / Non-Goals

**Goals:**

- 从 `_run_tracking()` 抽出可复用组件 `ViewTrackingSession`，接口 `step(frame, *, frame_index, timestamp, guidance=()) -> ViewFrameResult`。
- 封装单视角逐帧 tracking 完整计算链，持有 per-view tracking 状态（tracker / suppressor / smoother / selector / lock / identity / footpoint / projector）。
- **保留现有依赖注入契约**：`AnalysisPipeline.__init__` 的 `tracker` / `footpoint_estimator` / `projector` 注入在重构后继续生效。
- 新增可选 ROI detector 契约 `detect_regions`（unsupported 显式抛错）。
- **行为保护**：默认 `guidance=()` 时单摄输出与重构前一致（regression = 0），以强制 differential test + 回归套件守护。

**Non-Goals:**

- 不改动 eligibility 语义（`lock | suggested` 保持现状；mode-scoped 收紧属 Change 2）。
- 不改动 `GlobalTrackFilter` / `CrossViewPlayerAssociator` / fusion / orchestration / artifact schema / Executor / Composer。
- 不实现 guided ROI detection 逻辑（`detect_regions` 仅加契约，Change 1 不调用）。
- 不改动已归档 P0 文档。
- 不把 `PoseEstimator` 纳入 session（本 Change 由 pipeline 持有）。

## Decisions

### D1: Session 边界 —— 什么进 session、什么留在 pipeline

**进入 `ViewTrackingSession`**（逐帧计算链，来自当前循环 1881-2233 行）：
1. `_detect_frame(frame)`（注入的 `PersonDetector`）
2. `filter_detections_to_roi(raw_detections, roi_artifact)` —— ROI artifact 由 pipeline 计算、构造时注入（**已冻结**，见 D1a）
3. `tracker.update(detections)`
4. `duplicate_suppressor.filter(tracks)`
5. `footpoint_estimator.estimate(...)`
6. `projector.project(...)`（homography 构造时注入）
7. `position_smoother.update(...)`（逐 pos 平滑）
8. `primary_player_selector.select(...)`
9. `player_lock_manager.update(...)` + `eligible = lock | suggested`（语义不变）
10. `_tracks_to_frame_detections(...)`
11. `identity_manager.update(...)` → `player_by_track` / `tentative_by_track`
12. 渲染观测 `CourtTrackObservation` 构建、帧检测 `player_id` 标注、生命周期事件（identity/lock diagnostics → render events + epoch 递增，顺序见 D2b）

**留在 `AnalysisPipeline`**：
- 视频解码 / 抽帧 / clip 时间裁剪、FPS 元数据
- **`processed_frame_count`**（见 D1b）
- court-view 门控（scorer / state machine / frame_samples 累积；`gated_non_court_view` 时跳过 step）
- detection ROI artifact 计算（`compute_expanded_detection_roi`）+ calibration diagnostics
- debug writers（消费 session 的 `ViewFrameResult`）
- 球检测（消费 `player_motion_pixels`）、姿态估计（消费 `frame_detections`）
- 进度日志、渲染轨迹后处理（消费 session 累积的 `render_observations` / `render_events`）
- 产物组装：`TrackingResult` / `PlayerTrajectoryArtifact` / `PlayerSelectionArtifact` / court-view ROI artifact / ball run output / metrics / visualization

**理由**：只有"逐帧 tracking 计算 + per-view 状态"是 P1 要复用的部分；解码、球、姿态、产物是单视角富分析链，P1 里仅参考视图需要，留在 pipeline 避免重复。

**替代方案**：把 court-view 门控也进 session。否决——门控产物（`CourtViewRoiArtifact`）与 pipeline 的 ROI 诊断耦合，Change 1 保持"pipeline 决定是否 step"。

### D1a: detection ROI 过滤位置（已冻结）

ROI artifact 的**计算/配置**留在 pipeline（`compute_expanded_detection_roi` 每 run 一次、构造时注入 session）；`filter_detections_to_roi()` 的**逐帧执行**进入 session（detect → filter → tracker 闭环）。理由：P1 真正需要复用的原子操作是 `frame → candidate detections → detection gating → tracker → position → identity`；若过滤留在 session 外，P1 会演变成 `session.step(frame, detections=filtered)`，session 不再掌握完整 perception 链，guided detection 又得在外面拼。该点不再列为 Open Question。

### D1b: `processed_frame_count` 归 Pipeline（MUST）

当前代码顺序：

```text
court_view_state.update(...)
processed_frame_count += 1
if gated_non_court_view: continue
```

`processed_frame_count` 统计"被 stride 采样并经过 court-view 判断的帧数"，**含被 gate 挡掉的帧**。若迁入 session（gate 之后才 step），有 gated frame 时计数会变小，直接改变 `TrackingResult` / detection stage detail / overlay artifact / coverage 诊断 / 前端展示。

因此冻结：

```text
AnalysisPipeline owns:  processed_frame_count   （保持 gate 前递增顺序）
ViewTrackingSession:    不持有、Change 1 也不暴露 tracking_step_count
```

ROI 计数（`roi_filtered_detection_count` / `full_frame_fallback_count`）仍放 session，因为它们当前本就只在通过 gate、执行 detection 的帧上递增。

### D2: `ViewFrameResult` 契约 —— step 返回什么、session 累积什么

`step()` 返回**本帧被 pipeline 实时消费**的输出：

```python
@dataclass
class ViewFrameResult:
    frame_index: int
    timestamp: float
    frame_detections: list[FrameDetection]      # 供姿态估计
    frame_positions: list[PlayerFramePosition]   # 供 debug writers / overlay
    render_raw_by_track: dict[int, dict[str, Any]]  # 平滑前原始坐标，供 projection debug
    player_motion_pixels: float | None           # 供球检测
```

**Session 内部累积**（供结束阶段读取，不逐帧返回）：
- `raw_detections` / `tracks` / `positions` / `overlay_frames`
- `render_observations` / `render_events`
- `player_multitarget_detections`
- `selection_diagnostics`（accumulate，`extend`）
- **`lock_diagnostics`**（accumulate；结束阶段必须原样参与现有合并流程：`player_trajectories.diagnostics = sorted([*identity.diagnostics, *lock_diagnostics], ...)`）
- **`latest_selection_training_samples`**（最新快照，`=` 覆盖而非 `extend`；避免实现者理解成累计列表）
- `roi_filtered_detection_count` / `full_frame_fallback_count`

**理由**：pipeline 每帧实时消费的只有姿态、调试、球三处的输入；其余是结束阶段产物，session 累积后统一暴露，避免巨型逐帧返回值。

### D2b: identity epoch 更新顺序（MUST）

当前顺序：

```text
identity_manager.update()
        ↓
构建本帧 CourtTrackObservation（使用当前 identity_epoch）
        ↓
读取 diagnostics
        ↓
若 reset → identity_epoch += 1
```

即：**reset 发生当帧的 render observation 使用旧 epoch，新 epoch 从后续帧生效**。Session 迁移 lifecycle 逻辑时 MUST 保持：

> render observation emission 在 同帧 diagnostic-driven epoch increment 之前。

否则 artifact 会 subtle 漂移。该顺序由 differential test 专门守护。

### D3: 构造 —— Session 工厂 + 保留依赖注入

`ViewTrackingSession` = **状态容器 + step 算法**，构造接受**已解析**的 components，不在内部无条件重建 tracker / footpoint / projector。新增工厂 `build_view_tracking_session(...)`：

```text
build_view_tracking_session(...)
        ↓
settings → config + 解析/构造 components（保留 DI）
        ↓
ViewTrackingSession(
    detector, tracker, duplicate_suppressor,
    footpoint_estimator, projector, position_smoother,
    selector, lock_manager, identity_manager,
    roi_artifact, config,
)
```

单摄适配时保持旧 DI 语义：

```python
tracker = self.tracker or MultiObjectTracker(max_lost=...)
footpoint = self.footpoint_estimator          # 注入优先
projector = self.projector                     # 注入优先
```

`build_view_tracking_config` 签名补全 frame dimensions：

```python
build_view_tracking_config(
    settings, match_context, *,
    fps, frame_stride, frame_width, frame_height,
) -> ViewTrackingSessionConfig
```

Session **不裸露内部 manager**，提供窄接口供结束阶段：`snapshot() -> ViewTrackingSessionOutputs`（含累积数据 + selector mode / fallback reason）、`build_player_trajectory_artifact(...)`、`projected_metric_tracks()`。避免外部 `session.identity_manager.xxx` 破坏 per-view 边界。

**理由**：`AnalysisPipeline.__init__` 明确支持 `tracker` / `footpoint_estimator` / `projector` 注入，重构不能悄悄丢失；工厂把"settings → component 构造"与"状态容器 + step 算法"分离，P1 双摄各自 `build_view_tracking_session`、但共享同一 `PersonDetector` 实例自然成立。

**替代方案**：session 内部全量构造 components。否决——破坏现有注入契约。

### D4: 行为保护 —— 强制 differential test

1. **默认 `guidance=()`**：Change 1 永不触发 guided detection。
2. **强制 differential test（升级自可选）**：固定 synthetic frames + scripted/mock `PersonDetector` + 固定 homography + 固定 config，对比重构前后两条路径的输出——raw detections / frame detections / positions / render observations / render events / player trajectory / metric tracks / ROI counters，须逐项一致。覆盖核心状态机搬迁（tracker / smoother / selector / lock / identity / render epoch / diagnostics / overlay）。
3. **回归门**：现有单摄 tracking 相关测试套件全绿。
4. **可选**：real-video golden smoke（真实 fixture 视频产物冒烟，不维护全量 golden）。

**理由**：约 300 多行核心状态机搬迁，仅靠"现有测试全绿"不足以证明 `regression = 0`；synthetic differential 成本低、能真正兑现行为保护。真实视频 golden 成本高，保持可选。

### D5: `detect_regions` 显式 unsupported

`PersonDetector` 增加：

```python
class RegionDetectionUnsupported(RuntimeError): ...

def detect_regions(self, frame, regions, confidence_override=None) -> list[Detection]:
    raise RegionDetectionUnsupported("this detector does not implement ROI inference")
```

以及 `supports_region_detection = False`（P1 真正实现后置 True）。**不用 `[]` 静默表示不支持**——`[]` 的语义是"ROI 推理成功但这里没人"，将来 P1 接线失误会变成难以诊断的静默漏检。

`EmptyPersonDetector` 返回 `[]` 则正确：其语义本就是"永远没有检测"。

Change 1 主路径（`guidance=()`）永不调用 `detect_regions`，不影响行为保护。

**替代方案**：unsupported 返回 `[]`。否决——语义混淆，静默漏检难排查。

### D6: P1 就绪度

- `PersonDetector` 可注入共享：Cam1/Cam2 两个 session 可传同一实例；`PoseEstimator` 本 Change 由 pipeline 持有，不进入 session（与 proposal 表述对齐）。
- `guidance` 参数占位：`step(..., guidance=())` 已就位，P1 传入 `CrossViewGuidance` 列表。
- session 每次 tracking run 新建（与既有 `PrimaryPlayerSelector` 生命周期对齐 requirement 一致）。

## Risks / Trade-offs

- **[Risk] 重构引入行为漂移（最核心）** → 缓解：强制 synthetic differential test（D4.2）+ 回归套件全绿；逐字段迁移 config（D3）。
- **[Risk] `processed_frame_count` 语义漂移**（gate 前 vs gate 后）→ 缓解：留在 pipeline、保持 gate 前递增顺序（D1b）。
- **[Risk] 丢失 `tracker` / `footpoint_estimator` / `projector` DI** → 缓解：工厂保留注入（D3），加注入测试。
- **[Risk] `lock_diagnostics` 从 `player_trajectories.diagnostics` 合并中消失** → 缓解：session 累积并原样参与合并（D2）。
- **[Risk] `selection_training_samples` 被实现成累计列表** → 缓解：命名冻结为 `latest_selection_training_samples`（快照语义，D2）+ 差分/单元测试。
- **[Risk] identity epoch 顺序漂移** → 缓解：MUST 顺序冻结（D2b）+ differential test 守护。
- **[Risk] `detect_regions` 静默 `[]` 造成 P1 漏检难查** → 缓解：显式 `RegionDetectionUnsupported`（D5）。
- **[Risk] `ViewTrackingSessionConfig` 字段迁移漏字段** → 缓解：以 1753-1860 行推导块为逐字段核对清单；config 构造单测断言关键字段与 settings 一致。

## Migration Plan

- 单次提交。新增 `view_tracking_session.py`（config / factory / session / outputs），改造 `_run_tracking()` 为"解码/门控/计数/球/姿态/调试/组装 + 委托 session"。
- 不改变任何 artifact schema、API、存储路径、前端契约。
- 回滚 = revert 该提交（无数据迁移、无产物格式变化）。
- 验收：强制 differential test + 现有单摄/多视角相关测试全绿。

## Open Questions

无阻塞项。ROI 过滤位置（D1a）与差分测试强度（D4）已拍板。real-video golden smoke（D4.4）是否纳入 CI 由实施阶段视 fixture 成本决定，不阻塞 apply。
