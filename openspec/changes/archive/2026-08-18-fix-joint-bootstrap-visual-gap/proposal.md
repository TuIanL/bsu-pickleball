## Why

joint_tracking_v2 模式下，视频回放的**前 1~2 秒既没有人物框、也没有小地图轨迹，随后恢复正常**。这并非 YOLO 漏检，也不是前端 artifact 异步加载，而是身份 bootstrap 的「权威身份确认窗口」被错误等价成了「展示空窗」：

- `PlayerLock` 在 `frame_index < bootstrap_min_frames`（30fps 下 ≈30 帧 = 1.0s）期间只收集 tracklet、不允许 `_try_early_lock()`；
- 该窗口内 `eligible_track_ids` 恒为空 → 不出 `player_id` → 不出 `JointObservation` → 不 fusion → `fused_player_overlay`（人物框数据源）与 `result.tracks`（小地图数据源）开头均无数据；
- 前端人物框（吃 `fusedPlayerOverlay`）与小地图（吃 `result.tracks`）因此同空同恢复。

实测（job-131dcc0477 / mvr_fd98101a3951）已坐实：首条 `player_locked` 在 1.0s（= bootstrap_min_frames），`fused_player_overlay` 首次非空前与 `result.tracks` 首次采样均在 1.133s，三者互相吻合。这是启动阶段真实的展示证据缺口，不影响任何指标或身份算法。

**目标**：把「Authoritative Identity（权威身份）」与「Display Evidence（展示证据）」解耦——离线任务在身份锁定后，安全地用最终 P1~P4 身份对 bootstrap 期间已真实存在的 track 做 retrospective 回填，仅用于展示，**绝不污染**指标 / fusion / 全局 roster。

## What Changes

- 新增**离线展示回填**链路：joint 任务完成后，依据「首次 lock 映射」（slot 第一次进入 locked 时记录的 `(player_id, track_id, locked_frame_index)`，仅记一次、永不覆盖）取每个 Player_N 最终锁定的 `track_id`，从 reference view 原始 tracking 轨道中筛出该 track 在 `locked_frame_index` 之前的**真实**观测（bbox + local court_position），经 `local_to_canonical(reference_orientation)` 转为 canonical 坐标后，标注 `evidence_type=bootstrap_backfill`、`display_only=true`、`metric_eligible=false`，注入融合叠加层与小地图。
- **坐标系转换**：回填的 canonical 坐标必须由 `local_to_canonical(orientation=reference_orientation)` 显式转换，不能把单视角 local `court_position` 直接当 canonical（否则 `rotate_180` 参考机位下小地图会翻转）。
- **展示权威统一**：joint 模式的 display authority 拍板为 `fusedPlayerOverlay` —— 人物框与 `CourtMinimap` 都从 overlay 的 player entity（含 `canonical_court_position_ft`）派生展示轨迹；单摄仍走 `pipelineTracks`。joint 模式下若 fused overlay 可用则用 overlay-derived display tracks，仅旧任务/不可用时 fallback 到 `result.tracks`。**不新增第三个 `display_player_trajectory` artifact**。
- `PlayerLockManager` 新增**纯观测接口** `initial_lock_assignments`（任何 slot 第一次进入 locked 时记录一次，永不覆盖），经 `snapshot()` 透出；**不改变**谁被锁、何时锁、锁定阈值、bootstrap 行为。
- `ViewTrackingSession.snapshot()` **已**暴露 `positions` / `tracks`（无需再改）；joint finalize 阶段改为消费 reference view 的 session snapshot 做回填。
- **不改**：`PlayerLock` bootstrap 逻辑、`lock_only` eligibility、`association` / `GlobalState` / fusion metrics、P1~P4 最终身份判定、heatmap / distance / speed 等位置指标。回填数据 MUST NOT 被任何指标消费。

## Capabilities

### New Capabilities
- `multiview-bootstrap-display-backfill`: 离线阶段对 bootstrap 窗口内真实存在的原始 track 观测，按其最终锁定的 Player_N 身份做 retrospective 展示回填，纯 display-only，附显式 provenance 契约（`evidence_type=bootstrap_backfill`、`display_only=true`、`metric_eligible=false`）。

### Modified Capabilities
- `view-tracking-session`: **新增** `initial_lock_assignments` 透出（首次 lock 映射），并随 `snapshot()` 暴露；原始 `positions` 已由 snapshot 暴露，回填直接复用。
- `multiview-fused-player-overlay`: 既有「五种 evidence + hidden outcome」决策链增加最低优先的 `bootstrap_backfill` 分支（仅当五级证据全缺、且 `frame < 该 player 的 locked_frame_index`、且存在回填真实观测时启用）；overlay player entity 新增 `canonical_court_position_ft`，使人物框与小地图同源同 tick。

## Impact

- **后端**：`PlayerLockManager`（新增 `initial_lock_assignments` + snapshot 透出）、`fused_overlay_types.py`（EvidenceType 增加 `bootstrap_backfill` + validator + `FusedPlayerOverlayPlayer` 增加 `canonical_court_position_ft`）、`overlay_display_state.py`（展示状态映射增加 `bootstrap_backfill`）、`fused_overlay_builder`（新增 bootstrap 分支）、新增 `BootstrapDisplayBackfillBuilder`、`joint_view_runtime`（finalize 阶段触发回填）。
- **前端**：`report.ts`（`FusedPlayerEvidenceType` + `FusedPlayerOverlayEntity` 增加 `canonical_court_position_ft`）、`VideoAnalysisCard.tsx`（`FUSED_EVIDENCE_STYLE` 增加 `bootstrap_backfill`）、`CourtMinimap`（改吃 overlay-derived 展示轨迹）、`videoOverlayPlayback.test.ts`（新增 playback regression）。
- **产物**：新增 `bootstrap_display_backfill.v1`（功能产物）；可选 debug-only 落盘 `bootstrap_preidentity_observations.v1`。
- **依赖 / 风险**：回填数据源依赖「track temporal / spatial continuity guard」（防 tracker identity switch / 异常空间跳变），而非「frame 连续无断档」（tracker 不复用 id，允许自然漏检间隙）。
- **不破坏**：identity manager、global association、metrics、roster 的 authoritative 路径保持不变；`result.tracks` 语义不变。
