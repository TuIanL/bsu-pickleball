## Context

joint_tracking_v2 的视频回放存在启动阶段的展示证据缺口：视频前 1~2 秒人物框与小地图同时为空，随后恢复。已验证根因是身份 bootstrap 的「权威身份确认窗口」被等价成了「展示空窗」，而非检测缺失或前端加载慢。

当前链路（代码实证）：
- `MultiViewJointExecutor` 构造双视角 session 时 `eligibility_policy="lock_only"`（`multiview_joint_executor.py:358`）。
- `PlayerLockManager` 两条进入 LOCKED 的路径：普通 `_try_lock_slot()`（676 行）会 append `event="player_locked"` diagnostic；但 bootstrap 实际调用的 `_assign_candidate_to_slot()`（238 行）在 `observed_frames >= lock_min_hits` 时**直接** `slot.state="locked"` + `locked_since_frame`（267 行），**不写** `player_locked` diagnostic。
- 因此 bootstrap 窗口内 `eligible_track_ids = locked_track_ids | reconnect_candidates = ∅`，不出 `JointObservation`，不出 fusion → `fused_player_overlay` 与 `result.tracks` 开头都空。

实测（job-131dcc0477 / mvr_fd98101a3951）：首条 `player_locked` = 1.0s（= bootstrap_min_frames），`fused_player_overlay` 首次非空帧与 `result.tracks` 首次采样均在 1.133s，互相吻合，确认空窗来自后端时间线。

**约束（来自既有 spec 红线）**：`multiview-fused-player-overlay` 规定「系统 SHALL NOT 为了"始终显示全部球员"而制造无证据的展示框」。回填 MUST 使用真实观测，绝不做位置插值或 backward-hold。

**约束（来自用户）**：身份算法（PlayerLock / association / GlobalState / fusion metrics / roster）与位置指标（heatmap / distance / speed）全部保持不动；回填数据 MUST NOT 被任何指标消费。

**已核实的事实边界**：
- `MultiObjectTracker` 用单调 `_next_track_id`（`multi_object_tracker.py:35,74-75`），删除旧 track 后新检测只拿更大的 id，**不复用**旧号码 → 不以「frame 断档」推断 id 复用。
- `snapshot().positions[*].court_position` 是**单视角 local court 坐标**；association 进入 global matching 前显式 `local_to_canonical(...)`（`association_global.py:246`）；直接当 canonical 会在 `rotate_180` 参考机位翻转。
- 后端 `EvidenceType` 是严格 `Literal[base_observed, guided_observed, refined_observed, cross_view_projected, predicted_only]`（`fused_overlay_types.py:30`）→ 仅写 `"bootstrap_backfill"` 会过不了 validator。
- `ViewTrackingSession.snapshot()` **已**暴露 `positions` / `tracks`，无需再改。

## Goals / Non-Goals

**Goals:**
- 在离线任务完成后，把 bootstrap 窗口内已真实存在的原始 track 观测，按其最终锁定的 Player_N 身份做 retrospective 填充，填补前 1~2 秒的展示空缺。
- 回填数据带显式 provenance（`evidence_type=bootstrap_backfill`、`display_only=true`、`metric_eligible=false`），与 authoritative 数据在结构上可区分。
- 人物框与小地图共用同一展示时间语义（overlay entity 自带 `canonical_court_position_ft`）。
- 首次 lock 映射可靠暴露；坐标正确转换；契约（后端 Literal / 前端类型 / 展示样式）一致更新。

**Non-Goals:**
- 不修改 bootstrap 时长、不修改 `lock_only`、不修改身份判定 / 关联 / fusion / roster。
- 不修改任何指标（heatmap / distance / speed / trajectory metrics）。
- 不向前端做「假数据」：绝不把首帧 P1 框 backward-hold 到 t=0，绝不插值。
- 不修改 `result.tracks`（authoritative）的语义或内容；不新增第三个 `display_player_trajectory` artifact。

## Decisions

### D1：display-only 隔离（架构级红线）
回填产物**只**从 reference view session 的 `snapshot().positions` 旁路产出，写入独立的 `bootstrap_display_backfill.v1`（或并入 `fused_player_overlay.json` 的 `bootstrap_backfill` 段）。指标层与 fusion 层代码路径不引用该产物。隔离靠架构保证，而非约定。

### D2：数据源与范围收窄
video 画面是 reference view，bootstrap backfill 的 bbox / court 最可信来源应**显式限定为 `reference_view_id`**，而不是随便哪个 view。范围从「整场 × 双摄 × 全 track」缩小为「reference view × bootstrap 窗口 × 最终锁定的 2/4 个 track」。
- 功能链路直接吃内存 snapshot，仅持久化 `bootstrap_display_backfill.v1`；
- 如需排障可额外落 debug-only 的 `bootstrap_preidentity_observations.v1`（pre-lock raw observations），而非整场 `view_session_raw_tracks` 全量落盘。

### D3：首次 lock 映射显式化（修复 P0 接线错误）
**不使用** `lock_diagnostics.player_locked` 反推——bootstrap 首次锁定走 `_assign_candidate_to_slot()`，不写该 diagnostic，反推会漏掉最重要的映射。
改为在 `PlayerLockManager` 增加纯观测接口：

```text
InitialLockAssignment(player_id, track_id, locked_frame_index)
_initial_lock_assignments: dict[str, InitialLockAssignment]
```

任何 slot **第一次**从非 locked 进入 `locked` 时记录一次，**永远不覆盖**（后续 reconnect / tentative 切换不影响）。`snapshot()` 显式带出。
**不改变**：谁被锁、何时锁、锁定阈值、bootstrap 行为——只是把现有内部事实可靠地暴露。

### D4：retrospective identity assignment，非插值
仅取「该 Player_N 最终锁定的 exact `track_id`」在 `frame_index < locked_frame_index` 区间内的**真实**观测（bbox + local court_position），原样赋值（非插值），随后经 D6 转 canonical。pre-lock 期间若该 track 无观测 → 该帧不填（自然为空，不做假数据）。

### D5：track temporal / spatial continuity guard（防「错人假历史」，修正 P0 前提）
当前 tracker **不复用** id，但同一 track 可能被 IOU 贪心错误接给另一个人，或发生异常空间跳变 / 严重碎片化。护栏目标不是「帧连续」，而是「identity 连续 + 空间合理」：
- 只取 exact `track_id` 的 pre-lock 真实观测；
- **允许自然观测间隙**（detector miss、frame_stride>1 的 0,2,4,6... 序列都正常）；
- 对相邻真实观测：若 `Δt` 合理 **且** `displacement / Δt ≤ display_backfill_max_speed` **且**与 lock 起点空间连续 → 接受；
- 否则（异常跳变）从异常处**截断**历史，丢弃该段；
- **宁可少填、绝不填错**。

### D6：canonical 坐标转换（修正 P0 坐标风险）
`snapshot().positions[*].court_position` 是单视角 local court ft。必须经与 association 相同的转换：

```text
position.court_position (local court ft)
        │ local_to_canonical(orientation=reference_orientation)
        ▼
canonical_court_position_ft = [x, y] | null
```

转换放在 `BootstrapDisplayBackfillBuilder`，**不让前端猜**。建议字段命名 `canonical_court_position_ft: [x, y] | null`，并可在 artifact 层带 `court_frame_version="canonical_court_frame.v1"`、`court_unit="ft"` 强化契约。

### D7：与既有「五种 evidence + hidden outcome」协同
`fused_overlay_builder` 当前有 **五种** `EvidenceType`（`base_observed / guided_observed / refined_observed / cross_view_projected / predicted_only`）+ 「不渲染」outcome。`bootstrap_backfill` 作为**最低优先的最后兜底分支**：仅当五级证据全缺、且 `frame < 该 player 的 locked_frame_index`、且存在 D4/D5 给出的真实观测时启用；不得覆盖任何更高级别证据，也不得产生「不渲染」之外的额外 outcome。

### D8：EvidenceType 契约更新（修正 P0 接线遗漏）
后端 `fused_overlay_types.py`：
- `EvidenceType` Literal 增加 `bootstrap_backfill`；
- `FusedPlayerOverlayPlayer` 增加 `canonical_court_position_ft`；
- 相应 validator / `overlay_display_state.py` 的展示状态映射都要增加 `bootstrap_backfill`（建议映射为 `REAL_BOX`，因其有真实 bbox）。

前端：
- `report.ts`：`FusedPlayerEvidenceType` 增加 `bootstrap_backfill`；`FusedPlayerOverlayEntity` 增加 `canonical_court_position_ft`；
- `VideoAnalysisCard.tsx`：`FUSED_EVIDENCE_STYLE` 增加 `bootstrap_backfill`；
- `videoOverlayPlayback.test.ts`：新增 bootstrap_backfill playback regression。

### D9：零影响验收（hard invariant）
同一输入跑 A=backfill OFF 与 B=backfill ON，要求以下结构化 JSON **完全一致**（直接 hash）：
```
fused_player_trajectory      identical
global roster                identical
result.tracks                identical
metrics                      identical
```
仅允许发生变化：`bootstrap_display_backfill` / `fused_player_overlay` / 前端 `CourtMinimap` display。这是对「display-only 真的只是 display-only」的最强保证。

## Risks / Trade-offs

- **[Risk] initial_lock_assignments 仍可能为空**（如 bootstrap 全程无人锁定）→ Mitigation：回填函数对缺失映射的 player 自然跳过，不报错、不造假。
- **[Risk] local→canonical 用错 orientation** → Mitigation：始终用 `reference_orientation`（joint 已知），且该 orientation 与 association 同输入；单测覆盖 `rotate_180`。
- **[Risk] 异常空间跳变误接受** → Mitigation：D5 的速度/连续性护栏；阈值 `display_backfill_max_speed` 取保守值（如 2× 正常球员最大速度）。
- **[Risk] 回填错误导致展示异常** → Mitigation：纯展示产物 + `ENABLE_BOOTSTRAP_DISPLAY_BACKFILL` 开关（默认开），一键禁用即可回滚，无数据迁移。
- **[Trade-off]** 不修 identity 算法意味着 bootstrap 时长仍固定 1~3s，回填只覆盖「已检测但未显示」的窗口，不缩短锁定本身。

## Migration Plan

1. 后端：`PlayerLockManager` 新增 `_initial_lock_assignments` + snapshot 透出；`fused_overlay_types.py` 扩展 EvidenceType / player entity；`BootstrapDisplayBackfillBuilder` 实现 D3~D6；`joint_view_runtime` finalize 阶段触发回填。
2. 落盘：`bootstrap_display_backfill.v1` 随 job artifact 写出；可选 `bootstrap_preidentity_observations.v1`（debug-only）。
3. 前端：`report.ts` / `VideoAnalysisCard.tsx` / `CourtMinimap` 接入新 evidence 与 `canonical_court_position_ft`；`VideoAnalysisCard` 维持 fused overlay 优先。
4. 默认开启开关，回滚 = 关闭开关 + 删除回填 artifact，无数据迁移。

## Open Questions

- **验收素材**：job-131dcc0477 有 1.5s pre-roll，0~1.0s 零观测无法区分「隐藏检测」与「真无人」。该 job 的正确 acceptance 是「有真实 pre-lock observation 的 tick → 必出现 bootstrap_backfill；无真实 observation 的 tick → 必仍为空；禁止为达到 0 秒有人而制造框」。真正验证「t=0 即四人显示」需另取「无 pre-roll 且 t=0 有人」的 clip（见 tasks 5.3）。
- **initial_lock_assignments 是否需事件时间戳**：当前落地 `(player_id, track_id, locked_frame_index)` 足够；如需墙钟时间可由 frame_index 推导，列为可选增强。
- **`display_backfill_max_speed` 阈值**：取保守常数（如 2× 正常最大速度），实施时由实现者校验。
