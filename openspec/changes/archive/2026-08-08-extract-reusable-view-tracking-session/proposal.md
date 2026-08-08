## Why

`AnalysisPipeline._run_tracking()` 是一个约 1500 行的单体函数，逐帧 tracking 计算（检测 → ROI 过滤 → 多目标跟踪 → 脚点 → 投影 → 平滑 → 主球员选择 → 锁定 → 身份 → 渲染观测）全部内嵌在同一个 while 循环里。当前 P0 `joint_tracking_v2` 演进要求每个摄像头各跑一路逐帧 tracking，若不先抽出可复用组件，`single_view_tracking.py` 与 `multiview_tracking.py` 会各自复制一套、后续修脚点/PlayerLock/Selector 时两边漂移。这是多视角架构演进（P1）之前的第一个纯架构 Change：**抽出 `ViewTrackingSession`，行为完全不变（行为保护）**。

## What Changes

- 新增 `ViewTrackingSession` 可复用组件，接口 `session.step(frame, *, frame_index, timestamp, guidance=()) -> ViewFrameResult`。它封装单视角逐帧 tracking 的全部计算链：detect（注入的 PersonDetector）→ detection ROI 过滤 → `MultiObjectTracker.update` → `DuplicateTrackSuppressor` → `FootpointEstimator` → `PlayerProjector.project` → `CourtPositionSmoother` → `PrimaryPlayerSelector` → `PlayerLockManager` → `PlayerIdentityManager` → 渲染观测/事件生成。
- `AnalysisPipeline._run_tracking()` 中的逐帧循环改为委托 `session.step()`，其余保留在 pipeline：视频解码/抽帧/时间裁剪、court-view 门控、detection ROI artifact 计算、calibration diagnostics、debug writers、球检测、姿态估计、生命周期事件组装、进度日志、产物组装。
- Session 持有 per-view tracking 状态组件（tracker / suppressor / smoother / selector / lock / identity / footpoint / projector）；`PersonDetector` 由外部注入、允许未来两个 ViewTrackingSession 共享同一实例；`PoseEstimator` 本 Change 继续由 `AnalysisPipeline` 持有，不进入 Session（避免文档内部矛盾）。
- `PersonDetector` / `EmptyPersonDetector` 新增可选 ROI detector 契约 `detect_regions(frame, regions, confidence_override=None)`（为 P1 guided ROI detection 铺路）；未实现 ROI 推理的 `PersonDetector` 显式抛 `RegionDetectionUnsupported`（不用 `[]` 静默表示不支持），`EmptyPersonDetector` 返回 `[]`；默认 `guidance=[]` 时永不调用，单摄行为不变。
- **行为保护（核心验收标准）**：默认 `guidance=[]` 时，单摄分析输出与重构前完全一致（regression = 0），由**强制 synthetic differential test**（固定 synthetic frames + mock detector + 固定 homography + 固定 config，逐项对比两路径产物）+ 现有单摄测试套件共同守护。
- **明确不做**：mode-scoped eligibility 收紧（属 Change 2 `add-bidirectional-multiview-player-tracking`）；`min_cost_matching` / prediction cost（已在 `fix-multiview-association-costing` 完成）；任何 artifact 版本变化。

## Capabilities

### New Capabilities
- `view-tracking-session`: 可复用的单视角逐帧 tracking session —— `step()` 接口、持有 per-view 跟踪状态、重量模型注入共享、默认 guidance 下行为保护、`ViewFrameResult` 契约。

### Modified Capabilities
- `player-tracking-engine`: `PersonDetector` 契约增加可选 `detect_regions(frame, regions, confidence_override=None)` 方法（默认不可用、不改变现有 detect / detect_frame 行为）。

## Impact

- **代码**：
  - 新增 `backend/app/vision/player_tracking_engine/view_tracking_session.py`（`ViewTrackingSessionConfig` / `ViewFrameResult` / `ViewTrackingSession` / `build_view_tracking_session` 工厂 / 窄接口输出）
  - `backend/app/services/analysis_pipeline.py`（`_run_tracking()` 逐帧循环委托 session；`processed_frame_count` 与 court-view gate 顺序保持；`tracker` / `footpoint_estimator` / `projector` 注入经工厂保留）
  - `backend/app/vision/player_tracking_engine/person_detector.py`（`detect_regions` 可选契约 + `RegionDetectionUnsupported`，含 `EmptyPersonDetector`）
- **测试**：强制 synthetic differential test（重构前后两路径逐项对比）+ 现有单摄 tracking 测试全绿（行为保护）；新增 session 单元测试（step 逐帧、默认 guidance、DI 注入保留、detect_regions unsupported 显式抛错）。
- **不涉及**：P0 已归档文档、`GlobalTrackFilter` / `CrossViewPlayerAssociator` / fusion / orchestration / artifact schema / Executor / Composer。
