## Why

双摄 joint 模式下，视频叠加层出现"某球员消失 / 实线框 / 虚线框 / 脚点"切换时，页面只告诉用户"P1 丢失"，无法区分到底是哪一层断了。Phase 0 单点诊断（mvr_35ac365aec96 @ 00:07）已实证：P1 在两路都有真实检测框（cam_1 conf 0.71、cam_2 conf 0.857），但**两路都没有形成 formal observation** —— 断点在 `detection → court_position 投影 → formal observation → association` 链路，不在检测器、也不在 overlay。没有逐 stage 的显示诊断，后续任何感知层改动（fast recovery、pre-association）都只能靠肉眼猜，无法定位失败漏斗，也无法验证修复是否真正命中断点。

## What Changes

- **新增 `player-display-diagnostics` 能力**：joint run 每个 canonical tick 对 `roster confirmed player × available view` 落盘一份**紧凑**的逐 stage 显示漏斗（`player-display-diagnostics.v1`），回答"这个球员此刻为什么这样显示 / 为什么不显示"。
- **v1 漏斗边界 = post-tracker/post-lock eligible detection**：`frame_detections` 是 `PlayerLockManager` 得到 `eligible_track_ids` 之后才构建的检测框（非 raw YOLO）。v1 能准确回答 `eligible detection → position → court projection → formal JointObservation → global association` 各层，但**不回答** raw detector / ROI filter / tracker / lock rejection 归因（不属于本 Change）。
- **分层断裂状态**：对每个候选拆 `eligible_detection_present / position_present / court_position_present / projection_status / projection_confidence / formal_observation_emitted`，前两项必须独立（`frame_detection` 有而 `frame_position` 无 vs `court_position=None` 根因不同）。
- **数据源复用运行时已暴露的信息**：`ViewFrameResult` 已携带 `frame_detections`、`local_identity_by_track`、`observation_origin_by_track`、`pre_gate_residual_by_track`、`guided_reject_reason_counts` 等（`view_tracking_session.py:132-157`）。**不修改** ViewTrackingSession 检测/身份/关联算法，**不新增**检测阶段。
- **read-only decision observability**：`AssociationUpdate` 当前无 reason 字段、`GlobalPlayerAssociator.diagnostics` 仅为全局 counter，因此本 Change 增加只读 `AssociationDecision`（如 `associator.last_tick_decisions`，含 `result/reason`），不改变 `process_tick()` 算法结果与门限；`GuidanceGenerator.generate()` 当前遇条件不满足即 `return None`，本 Change 增加 side-effect-free `GuidanceDecision`（status + reason：target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable 等），为 `add-next-tick-fast-player-recovery` 打基础。
- **身份归因约束**：漏斗中 eligible detection 阶段只表达 `eligible_detections_in_expected_gate`（post-lock 候选落在 expected region 门内），MUST NOT 描述为 "raw YOLO hit P1"——该字段不表示检测器原始输出。
- **expected region 因果性**：expected region SHALL 只使用 **pre-tick global prediction**（该帧处理前系统预期 P1 在哪），MUST NOT 用 same-tick fused position（避免 hindsight bias）。`expected_region_status = available | prediction_unavailable | uncertainty_too_high | target_geometry_unavailable`，非 `available` 时 `eligible_detections_in_expected_gate` 为 `null`（表示"连可靠 expected region 都没有"），MUST NOT 写 `0`（`0` 表示"知道该看哪里但无候选"）。
- **expected region 几何复用 guidance 规则**：抽纯函数 `build_expected_player_region(predicted_position, uncertainty, target_geometry, policy)`，guidance 与 diagnostics 共用同一 ROI 计算（`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`），MUST NOT 各写一套固定 ±gate_px。
- **不依赖 debug trace**：`debugTraceEnabled=false` 时该 compact diagnostic 仍 MUST 生成；不得因缺少 `joint_debug_trace` 而跳过（避免"业务 truth 依赖 debug artifact"问题回归）。
- **诊断失败隔离（硬不变量）**：显示诊断构建失败 MUST NOT 导致核心 joint 分析失败；core result 保持成功，`player_display_diagnostics_status=failed` + 结构化 reason。
- **新增查询 API**：`GET /analysis/jobs/{job_id}/multiview/players/Player_1/display-diagnostics?timestamp_ms=7000&window_ms=500`，按窗口查询单球员单视角证据链；**正式 artifact 直接存 canonical `Player_N`**（run 内部暂存 global id，roster mapping 稳定后 canonicalize 再写正式产物），API 直接 filter `player_id == "Player_1"`，无需（也不做）在 API 层反查 global id。
- **前端展示**：双摄协同分析页（`/analysis/{jobId}/multiview`）新增 per-player 显示诊断展开面板，默认折叠；MVP 不做 GT A/B、不做交互式时间线。
- **体积控制**：compact funnel 每 tick 每 `(player, view)` 一行精简 JSON（1815 ticks × 4 players × 2 views ≈ 1.5 万行级别），MUST NOT 膨胀为 debug trace 规模（127MB 量级）；MVP 不做窗口采样，全量但紧凑。
- **scope 边界（明确不做）**：不修改 guidance 触发语义、不修改 association decision semantics、不做 same-tick recovery、不新增 ViewTrackingSession 检测插桩、不做 raw detector/ROI/lock rejection 归因；这些属于后续 `add-next-tick-fast-player-recovery` 与 `strengthen-multiview-cooperative-player-perception`。

## Capabilities

### New Capabilities

- `player-display-diagnostics`: joint 模式逐球员逐 stage 显示漏斗的产物契约与查询——消费 `ViewFrameResult` + read-only association/guidance decisions + roster + frame status + pre-tick prediction，构建 `player-display-diagnostics.v1` 紧凑产物（artifact 直接存 canonical `Player_N`），并提供按 `Player_N × 时间窗口` 的只读查询 API 与前端展开面板。

### Modified Capabilities

- `multiview-joint-observability`: 双摄协同分析页新增 per-player 显示诊断入口与面板（引用新产物），并明确 `debugTraceEnabled=false` 时显示诊断仍可用、Debug 区域独立标记 unavailable；恢复漏斗与显示漏斗在页面语义上分离展示。
- `cross-view-player-guidance`: 新增 side-effect-free `GuidanceDecision` observability（generate 遇条件不满足时记录 status + reason），不改触发语义与门限；`build_expected_player_region` 抽为共享纯函数。

## Impact

- **后端**：`backend/app/vision/multiview/multiview_joint_run.py`（per-tick 漏斗记录：复用 `view_results` 中 `frame_detections` / `frame_positions` / `local_identity_by_track` / `guided_*`，association 后读取 `associator.last_tick_decisions`）、新增 `player_display_diagnostics.py`（漏斗构建 + contract schema + validator）、`backend/app/vision/multiview/association_global.py`（只读 `last_tick_decisions` observability，不改算法）、`backend/app/vision/multiview/guidance.py`（side-effect-free `GuidanceDecision` + 抽取 `build_expected_player_region`）、`backend/app/api/routes_analysis.py`（新增 `display-diagnostics` route）、`backend/app/services/storage_service.py`（产物路径 accessor）、`backend/app/schemas/pipeline.py`（AnalysisArtifacts 可选扩展字段）。
- **前端**：`src/pages/VisionPage.tsx` 或双摄协同分析页组件（新增 per-player 诊断面板，默认折叠）、`src/services/analysisClient.ts`（新增 API 封装）、`src/types/report.ts`（产物类型）。
- **契约**：新增 `player-display-diagnostics.v1` artifact contract（artifact 直接存 canonical `Player_N`）；`cross-view-player-guidance` 以 MODIFIED delta 表达 `GuidanceDecision` observability 与共享 region 纯函数。
- **OpenSpec**：新增 capability `player-display-diagnostics`；`multiview-joint-observability` 以 MODIFIED delta 表达页面新入口与可用性语义。
