## 1. 执行模式 + 持久化输入

- [x] 1.1 冻结字段名 `multiviewExecutionMode`(late_fusion_v1 | joint_tracking_v2),缺省 `late_fusion_v1`;历史 job 零迁移
- [x] 1.2 持久化 `jointViewInputs: [JointViewInput { cameraSlot, captureTrackId, cameraId, videoId, calibrationId, courtOrientation }]` 进 `AnalysisJobSummary`,Parent `sourceJobs = []`;保留 `cameraId`(sync 可能以真实 camera id 为 key,不依赖 `_resolve_secondary_sync_key()` 猜测)
- [x] 1.3 `executionMode` 进入 `inputSignature`/`configSignature`(防止同一 take 的 late/joint 被幂等去重当成同一任务,A/B baseline)
- [x] 1.4 新增 `jointRunId`(不复用 `fusionRunId`);`AnalysisJobSummary { fusionRunId?(late only), jointRunId?(joint only) }`;Parent 被 claim → 先持久化 `jointRunId` → 再开视频/模型
- [x] 1.5 `resolve_executor` 按 `analysisKind=multiview` + `executionMode` 选择执行体;`is_runnable()` 按模式判定(joint = queued AND orchestrationStatus == joint_ready)

## 2. CanonicalAnalysisClock(source-frame 单调不重复)

- [x] 2.1 新增 `app/vision/multiview/analysis_clock.py`:`SynchronizedFrameBundle { take_timestamp_ms, views, frame_status, mapping_diagnostics }`;`FrameSample { source_frame_index, source_timestamp_ms, mapped_take_timestamp_ms, selection_error_ms, frame }`
- [x] 2.2 实现 clock:reference analysis-frame tick(与检测无关),复用 `map_reference_time` / `build_frame_map`,超容差 → `unavailable`
- [x] 2.3 实现 **source-frame 单调不重复**:记录 `last_consumed_source_frame_index[view]`;tick 映射到已消费 secondary frame → `frame_status = no_new_frame`,**不调用 session.step**
- [x] 2.4 单测:两个 canonical tick 映射同一 Cam2 frame → Cam2 `session.step()` 只调用一次;tick 与检测无关;单视角缺源帧 → `unavailable`

## 3. GlobalMotionEstimator(不修改 P0)

- [x] 3.1 新增 `app/vision/multiview/global_state.py`:`GlobalPlayerState`(位置/速度/uncertainty/lifecycle/**cross_view_anchored**/view_bindings)
- [x] 3.2 新增 `GlobalMotionEstimator`(**不修改 P0 `GlobalTrackFilter`**),冻结 **4-state constant-velocity Kalman `[x,y,vx,vy]` + covariance**:`predict(t) → (position, covariance)`;吸收真实测量更新并收紧 covariance;`predicted` 不回灌
- [x] 3.3 实现 `cross_view_anchored`:历史 ≥N 次稳定双视角 canonical 一致 → true;单摄稳定仅使 lifecycle=confirmed
- [x] 3.4 单测:predict 未来位置 + covariance 增长、吸收测量收紧、confirmed 但未 anchored 不产生强 guidance

## 4. GlobalPlayerAssociator(不修改 P0)

- [x] 4.1 新增 `GlobalPlayerAssociator`(**不修改 P0 `CrossViewPlayerAssociator`**):`GlobalState.predict(t) → assign Cam1 → assign Cam2 → unmatched → tentative`;复用 Change 0 `min_cost_matching()` 共享 primitive
- [x] 4.2 单视角缺失不阻塞(P3 cam_1 不可见 / cam_2 可见仍关联到 global)
- [x] 4.3 单测:global-centric 分配、单视角缺失、几何门独立于预测;确认 `late_fusion_v1` 走 P0 associator

## 5. CrossViewGuidancePolicy(confirmed + anchored 门控)

- [x] 5.1 新增 `app/vision/multiview/guidance.py`:`CrossViewGuidance { global_player_id, target_view, predicted_canonical_position, uncertainty_ft, predicted_local_position, expected_image_position, roi, confidence, expires_at }`
- [x] 5.2 新增 `CrossViewGuidancePolicy`,冻结触发语义:`min_global_confidence / max_uncertainty_ft / missing_after_ticks / guidance_cooldown_ticks / max_regions_per_view_per_tick`;`ViewBinding { visibility: observed/weak/missing/lost, last_seen, quality }`
- [x] 5.3 强 guidance 仅对 `confirmed AND cross_view_anchored`;仅 weak/missing/lost 触发 high-recall ROI;observed 不重复补跑;cooldown + 每 view 每 tick region 上限
- [x] 5.4 实现 ROI 投影:`canonical → canonical_to_local()` → `H^-1` → image(covariance 决定 ROI 尺寸)
- [x] 5.5 单测:ROI 投影链、expires_at、policy 触发/冷却、guidance 不创造 measurement

## 6. Guided re-detection(pre-gate 在 tracker 之前)

- [x] 6.1 `PersonDetector` 实现 `detect_regions` ROI 推理(`supports_region_detection=True`,lower-threshold)
- [x] 6.2 实现 **candidate PRE-GATE**:`bbox/image sanity → candidate footpoint → Homography projection → canonical residual → motion residual`;candidate 无需 track id(从 `Detection.bbox → 临时 footpoint → image_to_court` 计算)
- [x] 6.3 只保留 accepted guided candidates → 与 base detections merge/dedup → **`tracker.update ONCE`**;**pre-gate 拒绝的 guided detection 绝不碰 tracker**
- [x] 6.4 单测:same-source-frame 不二次 update、合并去重、**pre-gate 拒绝不触碰 tracker**、accepted guided → `metric_eligible=true` / `predicted → false`

## 7. MultiViewJointRun + JointViewRuntime + 长任务语义

- [x] 7.1 新增 `JointViewRuntime { view_input, capture, fps, frame_size, homography, roi_artifact, court_view_scorer, court_view_state, tracking_session, scope, counters }`;`MultiViewJointRun → JointViewRuntime(cam1, full) + (cam2, perception)`;`MultiViewFusionRun` 仅属 late_fusion_v1
- [x] 7.2 实现 per-tick 流程:`GlobalState(t-1) → predict → guidance snapshot → View A/B(base+pre-gated guided, tracker.update ONCE) → tick barrier → GlobalPlayerAssociator → fusion → GlobalState(t)`;两路同用 pre-tick snapshot;V1 串行共享模型
- [x] 7.3 **复用 P0 位置融合数学**:`ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion`,不重写
- [x] 7.4 长任务:每 tick cancellation;进度 = canonical clock processed/total;两个 capture finally release;**atomic finalize**(避免半个 v2 被误认完成);重启复用 `jointRunId` 清理 temp 从头重跑(无 checkpoint)
- [x] 7.5 失败语义:Cam2 永久解码失败 → 该时刻起 view unavailable → 继续 Cam1 → diagnostics=`joint_degraded`;Cam1/reference 失败 → failed
- [x] 7.6 集成测试:双摄 joint 端到端(2 摄 4 球员、单摄缺失、guided 重检恢复)

## 8. ReferenceRichAnalysisContext(full scope 富分析)

- [x] 8.1 定义 `perception` scope(cam_2):person detection / tracking / duplicate suppression / footpoint / court projection / local PlayerLock+identity / guided re-detection / joint observation emission;不含 ball/serve/action/metrics/report/overlay
- [x] 8.2 新增 `ReferenceRichAnalysisContext`:cam_1 `JointViewRuntime` 的 `ViewFrameResult` → pose / ball / debug / serve helpers,**消费同一次 reference frame decode**,不二次调用 `AnalysisPipeline.run()`
- [x] 8.3 单测:full scope 富分析产物正确、cam_2 不重复跑富分析链

## 9. Artifact v1/v2 独立

- [x] 9.1 新增 sibling `JointViewObservation`(bbox / frame size / image footpoint / detection_origin / guidance_id?),不污染 P0 `ViewObservation`
- [x] 9.2 独立 writer:late → `writer_v1 → fused_player_trajectory.v1`(P0 writer 永远保留);joint → `writer_v2 → fused_player_trajectory.v2`(`observation_origin` 与 `fusion_status` 正交)
- [x] 9.3 公共 `load_fused_trajectory()` version-aware:`v1 → normalize_v1` / `v2 → normalize_v2`;Composer 消费 normalized model(不依赖"v1 reader 读 v2 未知字段"假设)
- [x] 9.4 Composer joint 路径:从 Parent-owned JointRun 获取,overlay 标签来自 `GlobalPlayer_<id>`;`late_fusion_v1` child inheritance 不变

## 10. 专项测试与回归

- [x] 10.1 **same-secondary-frame-not-processed-twice**:两个 canonical tick 映射同一 Cam2 frame → step 只调用一次(invariant 8)
- [x] 10.2 **guided-reject-does-not-touch-tracker**:pre-gate 拒绝的 guided candidate 不创建/改写 track 状态(invariant 9)
- [x] 10.3 **joint-restart-idempotency**:失败重试复用 `jointRunId`,清理 temp,原子 finalize
- [x] 10.4 **execution-mode-dedup/A-B**:同一 take 的 late/joint inputSignature 不同,不被去重丢弃
- [x] 10.5 运行 `late_fusion_v1` 既有多视角测试套件全绿(回归);确认 P0 `GlobalTrackFilter` / `CrossViewPlayerAssociator` 未被修改
- [x] 10.6 确认六条(现九条)硬不变量落实(design D11),不扩展 ball/pose/serve 到双摄协同
