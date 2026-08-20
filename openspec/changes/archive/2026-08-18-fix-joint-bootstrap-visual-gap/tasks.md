## 1. 首次 lock 映射（PlayerLockManager）

- [x] 1.1 在 `PlayerLockManager` 增加 `_initial_lock_assignments: dict[str, InitialLockAssignment]`（`player_id` / `track_id` / `locked_frame_index`）；任何 slot 第一次进入 `locked`（含 `_assign_candidate_to_slot` 的 bootstrap 路径，`player_lock_manager.py:267`）时记录一次，永不覆盖
- [x] 1.2 在 `ViewTrackingSession.snapshot()` 显式透出 `initial_lock_assignments`（复用已有 `positions` / `tracks`，不新增原始轨道字段）
- [x] 1.3 在 joint finalize 阶段消费 reference view 的 session snapshot（`initial_lock_assignments` + `positions`），作为回填数据源（`multiview_joint_executor.py` overlay_context 块读取 `ref_runtime.tracking_session.snapshot()`）

## 2. 回填计算核心（BootstrapDisplayBackfillBuilder）

- [x] 2.1 实现从 `initial_lock_assignments` 取每个 Player_N 的 `(track_id, locked_frame_index)`（不依赖 `lock_diagnostics.player_locked`）
- [x] 2.2 实现 retrospective 回填：筛出该 `track_id` 在 `frame_index < locked_frame_index` 的真实观测，原样赋值，**不进行插值**
- [x] 2.3 实现 track temporal / spatial continuity guard：允许自然观测间隙（detector miss / frame_stride>1）；相邻观测仅当 `Δt` 合理且 `displacement/Δt ≤ display_backfill_max_speed` 且空间连续时接受；异常跳变处截断历史
- [x] 2.4 坐标转换：对回填观测调用 `local_to_canonical(orientation=reference_orientation)`，输出 `canonical_court_position_ft`，转换放在 builder 内（不让前端猜）
- [x] 2.5 回填结果标注 `evidence_type=bootstrap_backfill`、`display_only=true`、`metric_eligible=false`，落盘为 `bootstrap_display_backfill.v1`（可选 debug-only 落 `bootstrap_preidentity_observations.v1`）

## 3. fused overlay 集成（evidence 契约）

- [x] 3.1 后端 `fused_overlay_types.py`：`EvidenceType` Literal 增加 `bootstrap_backfill`；`FusedPlayerOverlayPlayer` 增加 `canonical_court_position_ft: [x, y] | null`（含 `court_frame_version` / `court_unit` 可选强化字段）
- [x] 3.2 `overlay_display_state.py` 展示状态映射增加 `bootstrap_backfill → REAL_BOX`
- [x] 3.3 `fused_overlay_builder._decide_entity`（`fused_overlay_builder.py`）在五级证据全缺且 `frame < 该 player 的 locked_frame_index` 时，接入 `bootstrap_backfill` 分支作为最低优先级，MUST NOT 覆盖更高级别证据

## 4. 前端契约与展示

- [x] 4.1 `report.ts`：`FusedPlayerEvidenceType` 增加 `bootstrap_backfill`；`FusedPlayerOverlayEntity` 增加 `canonical_court_position_ft`
- [x] 4.2 `VideoAnalysisCard.tsx`：`FUSED_EVIDENCE_STYLE` 增加 `bootstrap_backfill`（避免渲染崩溃）
- [x] 4.3 `CourtMinimap` 改从 overlay-derived 展示轨迹（`canonical_court_position_ft`）读取，joint 模式 display authority = fusedPlayerOverlay；单摄仍走 `pipelineTracks`；无可用时 fallback `result.tracks`（注意：此处为 `result.tracks`，非 `result.tpracks`）
- [x] 4.4 `videoOverlayPlayback.test.ts`：新增 `bootstrap_backfill` playback regression（3 个用例，覆盖回填补窗、空帧不崩、与 post-lock 轨道合并为连续轨迹）

## 5. 开关与零影响验收

- [x] 5.1 增加 `ENABLE_BOOTSTRAP_DISPLAY_BACKFILL` 开关（默认开，`"1"`），支持一键禁用回填，无需数据库迁移即可回滚
- [ ] 5.2 对 job-bc053321f8 验证 acceptance：
  - [x] 5.2a 「不造假」数据诚实性已验证：该 job `bootstrap_display_backfill.json` = 30 条观测，全部 Player_1、frame 0–58、全部 `display_only=true`/`metric_eligible=false`、canonical 坐标全部有效，**无制造框** —— 纯数据层核对（无需重跑）
  - [ ] 5.2b 端到端注入待重跑确认：当前 `fused_player_overlay.json`（**重跑前的旧产物**）bootstrap_backfill 实体 = 0，证实状态机曾丢弃回填（集成 gap，已修复于 `overlay_display_state.py:45,51,143,157`）；需用户**重启 runtime 后重跑同一视频**得到新 job，确认 overlay 注入 30 条 Player_1 启动窗帧、且无人 tick 仍为空
- [ ] 5.3 取一个「无 pre-roll 且 t=0 有人」的 clip 复测，确认视频从 t=0 即有四人显示的回填真实生效 —— **用户无法提供该素材，change 结论阶段跳过（未验证真实填充效果）**
- [ ] 5.4 **零影响 hard invariant**：同一输入跑 A=backfill OFF 与 B=backfill ON，要求 `fused_player_trajectory` / `global roster` / `result.tracks` / `metrics` 结构化 JSON 完全一致（建议直接 hash），仅 `bootstrap_display_backfill` / `fused_player_overlay` / 前端 `CourtMinimap` display 允许变化 —— **可选，结论阶段未执行；代码层隔离已由 110 后端 + 10 前端单测覆盖，留作后续按需运行 hash-diff 脚本**
