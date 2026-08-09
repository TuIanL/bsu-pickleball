## Why

P0（`late_fusion_v1`）是"两个 child 各跑完整单摄分析,Parent 等 child 全完成才第一次同时知道两摄发生了什么"——事后报告修复。P1 让 `GlobalPlayerState` 在视频分析过程中就存在:Camera1 开始不可靠时,Camera2 已通过全局状态帮它继续看住球员。本 Change 引入 `joint_tracking_v2`,同时把 P0 完整保留为 `late_fusion_v1`(兼容 + A/B baseline)。

**核心原则:Additive P1。** P0 的核心算法类(`GlobalTrackFilter` / `CrossViewPlayerAssociator` / `CanonicalTimelineBuilder` / `MultiViewFusionRun`)在 late_fusion_v1 下语义完全不变;P1 能力全部由新类承载(`GlobalMotionEstimator` / `GlobalPlayerRegistry` / `GlobalPlayerAssociator` / `CanonicalAnalysisClock` / `MultiViewJointRun`),只在 joint_tracking_v2 生效。

## What Changes

- **执行模式 `multiviewExecutionMode`**:`late_fusion_v1 | joint_tracking_v2`,缺省 `late_fusion_v1`。`executionMode` 进入 `inputSignature`/`configSignature`,防止同一 take 的两种模式被幂等去重当成同一任务(A/B baseline)。同一 CaptureTake 可建两个 Parent 对比。
- **持久化 joint 输入**:新增 `jointViewInputs: [JointViewInput { cameraSlot, captureTrackId, cameraId, videoId, calibrationId, courtOrientation }]`,Parent `sourceJobs = []`。必须进 `AnalysisJobSummary` 持久化(重启可重建 JointRun);保留 `cameraId`(sync 可能以真实 camera id 为 mapping key,避免 `_resolve_secondary_sync_key()` 猜测)。
- **CanonicalAnalysisClock**(新):reference 视频 analysis-frame clock,与检测无关。`FrameSample { source_frame_index, source_timestamp_ms, mapped_take_timestamp_ms, selection_error_ms, frame }`;**source-frame 严格单调、不重复消费**——tick 映射到已消费的 Cam2 frame 时 `views.cam_2 = None` / `frame_status = no_new_frame`,不再次 step。
- **GlobalMotionEstimator**(新,不修改 P0 `GlobalTrackFilter`):冻结 **4-state constant-velocity Kalman `[x,y,vx,vy]` + covariance**,`predict(t) → (position, covariance)`,ROI 由 covariance 推导。
- **GlobalPlayerAssociator**(新,不修改 P0 associator):`GlobalState.predict(t) → assign Cam1 obs → assign Cam2 obs → unmatched → tentative`;复用 Change 0 `min_cost_matching()` 作为共享 primitive。
- **CrossViewGuidancePolicy**(新):冻结触发语义 `min_global_confidence / max_uncertainty_ft / missing_after_ticks / guidance_cooldown_ticks / max_regions_per_view_per_tick`;`ViewBinding { visibility: observed/weak/missing/lost, ... }`,仅 weak/missing/lost 触发 high-recall ROI。
- **Guided re-detection 顺序修正**:`guided candidate PRE-GATE(bbox sanity → footpoint → projection → canonical/motion residual) → accepted → 与 base merge → tracker.update ONCE`。**residual pre-gate 在 tracker 之前**,pre-gate 拒绝的 guided candidate 绝不碰 tracker。
- **lifecycle 与 cross-view 资格分离**:`GlobalPlayerState { lifecycle: confirmed, cross_view_anchored }`。强 guidance 要求 `confirmed AND cross_view_anchored`(历史上 ≥N 次稳定双视角一致);单摄错误锁定不能去另一摄自证。
- **`JointViewRuntime` + `ReferenceRichAnalysisContext`**:`MultiViewJointRun → JointViewRuntime(cam1, full) + JointViewRuntime(cam2, perception)`;cam_1 full 的 pose/ball/debug/serve 消费**同一次 reference frame decode** 的 `ViewFrameResult`,不二次调用 `AnalysisPipeline.run()`。
- **orchestrationStatus 冻结**:late_fusion `waiting_sources/fallback_ready/fusion_ready/fusing/composing/completed`;joint `joint_ready/joint_tracking/composing/completed`。`is_runnable()`:joint = `queued AND orchestrationStatus == joint_ready`。
- **`jointRunId` + 长任务语义**:`fusionRunId`(late only)/ `jointRunId`(joint only);Parent 被 claim → 先持久化 `jointRunId` → 再开视频/模型;原子 finalize;每 tick cancellation;Cam2 永久解码失败 → `joint_degraded` 继续 Cam1,Cam1 失败 → failed。
- **Artifact v1/v2 独立**:late → `writer_v1 → fused_player_trajectory.v1`(永远保留);joint → `writer_v2 → fused_player_trajectory.v2`;公共 `load_fused_trajectory()` version-aware,Composer 消费 normalized model。`observation_origin` 与 `fusion_status` 正交。
- **复用 P0 位置融合数学**:joint observations → Global association → 既有 `ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion` → Global motion update,不重写融合。

## Capabilities

### New Capabilities
- `multiview-execution-mode`: `multiviewExecutionMode` 字段、缺省、`inputSignature` 去重、A/B baseline。
- `multiview-synchronized-analysis-clock`: CanonicalAnalysisClock、`SynchronizedFrameBundle`、`FrameSample`、source-frame 单调不重复。
- `multiview-global-player-state`: `GlobalPlayerState`、`GlobalMotionEstimator`(4-state Kalman)、lifecycle 与 `cross_view_anchored` 分离。
- `cross-view-player-guidance`: `CrossViewGuidance`、`CrossViewGuidancePolicy`、`ViewBinding`、confirmed+anchored 门控。
- `guided-player-redetection`: guided candidate PRE-GATE(在 tracker 前)、merge、`detection_origin`。

### Modified Capabilities
- `analysis-job-executor-dispatch`: `MultiViewAnalysisExecutor` 按 executionMode 分发;joint 长任务语义(cancellation / progress / failure / atomic finalize)。
- `multiview-analysis-orchestration`: 冻结 late/joint 两套 orchestrationStatus 与 `is_runnable()`;joint 不创建 child。
- `multiview-analysis-result-composer`: v1/v2 独立 writer + 公共 version-aware reader;joint overlay 标签来自 GlobalPlayer。
- `multiview-analysis-input-contract`: `jointViewInputs` + `cameraId` 持久化;`executionMode` 进 inputSignature。
- `multiview-player-association`: 新增 `GlobalPlayerAssociator`(不修改 P0 associator),复用 `min_cost_matching()` 共享 primitive。
- `multiview-fusion-run`: `MultiViewJointRun` + `jointRunId` + 失败语义;`MultiViewFusionRun` 仅属 late_fusion_v1。

## Impact

- **代码**:
  - 新增 `app/vision/multiview/analysis_clock.py` / `global_state.py`(含 `GlobalMotionEstimator`)/ `guidance.py`(含 policy)/ `guided_detection.py`(含 pre-gate)/ `association_global.py`(`GlobalPlayerAssociator`)
  - 新增 `app/services/multiview_joint_executor.py`、`joint_view_runtime.py`、`reference_rich_analysis.py`
  - 改造 `analysis_executor_dispatch.py` / `multiview_coordinator.py` / `multiview_result_composer.py` / `fusion_run.py`(mode 感知 + joint run + jointRunId)
  - `view_tracking_session.py` 复用为双摄 ViewRun 载体(guidance 钩子已在 Change 1)
  - 新 `fused_player_trajectory.v2` writer + `load_fused_trajectory()` reader + `JointViewObservation`
- **数据**:`executionMode` / `jointViewInputs` / `jointRunId` 落 Parent job;历史任务缺省 late_fusion_v1,零迁移。
- **不涉及**:已归档 P0 文档;Change 0/1 产物(P0 核心算法类不被修改)。
- **测试**:clock source-frame 不重复 / guided pre-gate 不碰 tracker / joint restart 幂等 / execution-mode A/B 去重;late_fusion 既有套件全绿。
