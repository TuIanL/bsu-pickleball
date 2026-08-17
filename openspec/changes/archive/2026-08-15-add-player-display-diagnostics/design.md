## Context

joint 模式下视频叠加层出现"球员消失 / 框型切换"时，前端只显示"P1 丢失"这类粗粒度信息。Phase 0 单点诊断（mvr_35ac365aec96 @ 00:07，tick 210）已实证：P1 在两路都有 eligible detection（cam_1 `Player_1` track3 conf 0.71、cam_2 `Player_1` track1 conf 0.857），但两路 formal observation 均缺失 → `fused` 无 P1 → overlay 不渲染。断点在 `eligible detection → position → court projection → formal observation → association`，而非检测器或 overlay。

现有可复用的事实源（已核实）：

- `ViewFrameResult`（`view_tracking_session.py:132-157`）已携带：`frame_detections`（**post-lock eligible detections**，非 raw YOLO）、`frame_positions`、`local_identity_by_track`、`observation_origin_by_track`、`guidance_id_by_track`、`donor_view_by_track`、`expected_global_by_track`、`pre_gate_residual_by_track`、`guided_candidate_count`、`guided_pre_gate_accepted_count`、`guided_detection_invoked`、`guided_reject_reason_counts`。
- `frame_detections` 构建边界（`view_tracking_session.py:407-429`）：`PlayerLockManager.update()` 产出 `eligible_track_ids` → `_tracks_to_frame_detections()` 才构建。**因此 v1 漏斗起点是 post-tracker/post-lock eligible detection；raw YOLO / ROI filter / tracker / lock rejection 归因不在本 Change 能力内。**
- `_result_to_observations`（`multiview_joint_run.py:967-1042`）的进入条件链：formal detection 有 player_id → `positions_by_track` 找得到同 track → `pos.court_position is not None` → player_id 存在 → 生成 JointObservation；任一步失败直接 `continue`。
- `AssociationUpdate`（`association_global.py:72-80`）只有 `global_id / view_id / observation / confidence / tentative`，**无 reason**；`GlobalPlayerAssociator.diagnostics` 是全局累计 counter，非 per-observation 决策记录。
- `GuidanceGenerator.generate()`（`guidance.py:67-120`）遇条件不满足直接 `return None`，无 side-effect-free explanation；ROI 半径为 `base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`。
- `global-player-roster.v1`：`player_id (Player_N) ↔ global_player_id` 映射。
- `fused_player_overlay.v1`：展示层最终 evidence_type / bbox_source（前端已消费）。

## Goals / Non-Goals

**Goals:**

- joint run 每 tick 对 `roster confirmed player × available view` 落盘紧凑显示漏斗，定位"为何这样显示/为何不显示"的逐 stage 断点，粒度到 `eligible_detection / position / court_position / formal_observation / association`。
- 复用 `ViewFrameResult` + 只读 association/guidance decision observability，不修改感知算法、不新增检测阶段。
- 提供 `Player_N × 时间窗口` 的只读查询 API 与前端展开面板。
- `debugTraceEnabled=false` 时仍可生成（不依赖 debug trace）。
- 显示诊断构建失败不得影响核心 joint 分析结果。

**Non-Goals:**

- 不修改 guidance 触发语义、不修改 association decision semantics、不做 same-tick recovery（后续 change）。
- 不新增 ViewTrackingSession 检测插桩（如逐帧 raw YOLO 全量落盘）。
- **不做 raw detector / ROI filter / tracker / lock rejection 归因**（v1 起点是 eligible detection，向更早 stage 归因属后续 change）。
- 不做 GT A/B、交互式时间线、参数修改控件。
- 不把 debug trace 作为本产物的数据源或前置条件。

## Decisions

### D1: 漏斗记录点在 `process_tick` 之后（association 完成后）

在 `multiview_joint_run.py` 的 `updates = self.associator.process_tick(...)`（L400）之后记录：此时 `view_results`（per-view ViewFrameResult）与 `associator.last_tick_decisions`（只读决策记录）都在内存中，单次遍历即可同时获得 detection/position 信息与关联结果，无需二次遍历 tick 或重放视频。

**备选**：在 perception 后立即记录（L397 之后）→ 缺 association 结果，无法回答"检测到了但没关联上"；在 fused overlay 阶段反推 → 过度耦合 overlay 产物且丢失 detection/position 层信息。**选择 process_tick 后**。

### D2: v1 漏斗起点 = eligible detection；候选字段命名对齐真实边界

`frame_detections` 是 post-tracker/post-lock 的 eligible detection，因此字段命名为 **`eligible_detections_in_expected_gate`**（不是 `base_candidates_in_gate`，后者暗示 raw 候选）。spec 中 MUST 明确：v1 funnel starts at the post-tracker/post-lock eligible detection boundary；raw detector / ROI / lock rejection attribution 不属于本 Change。对该字段的解读是"系统本来会搜索 P1 的 expected region 里有没有 eligible detection"，而非"YOLO 是否看到了人"。

### D3: 分层断裂状态（不合并）

对每个 `(player, view)` 记录独立的断裂层字段，MUST NOT 合并成单个 `projection_ok`：

```text
eligible_detection_present      # frame_detections 有该 track
position_present                # frame_positions 有该 track
court_position_present          # pos.court_position 非 None
projection_status               # 原始 projection status 值
projection_confidence           # pos.projection_confidence
formal_observation_emitted      # 是否生成 JointObservation
```

`eligible_detection_present=true, position_present=false` 与 `eligible_detection_present=true, position_present=true, court_position_present=false` 是两种根因，MUST 分别可区分。本次 P1 案例正是靠这组字段定位到"检测框在、但 formal observation 断"。

### D4: association reason 来自只读 `AssociationDecision`，不假设 `AssociationUpdate` 带 reason

`AssociationUpdate` 当前无 reason。本 Change 在 `GlobalPlayerAssociator` 增加只读 `last_tick_decisions: list[AssociationDecision]`：

```text
AssociationDecision(view_id, observation_key, result, global_id=None, reason=...)
```

`reason` 覆盖 associator 内部已有的分支（`continuity_rejected_geometry` / `historical_reacquired` / `guided_expected_rejected` / `reassoc_pending` / `unresolved_no_slot` / `candidate_admitted` 等，目前仅累计进 `self.diagnostics` counter）。**不改变 `process_tick()` 算法结果与任何门限**，仅把已有决策点额外记录一份。这属于 read-only observability，不是修改 association 语义。

### D5: guidance 侧 side-effect-free `GuidanceDecision`

`GuidanceGenerator.generate()` 当前遇条件不满足即 `return None`。本 Change 增加 `last_decisions: list[GuidanceDecision]`，每条含：

```text
status = generated | not_eligible
reason = target_not_missing | donor_unavailable | donor_low_quality |
         prediction_uncertain | cooldown | geometry_unavailable | not_confirmed_anchored
```

不改变 generate() 的返回与触发语义。**必要性**：这是给 #2 `add-next-tick-fast-player-recovery` 打基础——如果连"为什么没触发 guidance"都看不到，到了 #2 会缺一块证据。若实现上暂不动 guidance 文件，前端 v1 只能显示 `guidance_generated / guided_detection_invoked / guided_candidates / guided_pre_gate_accepted`，不声称显示完整 `guidance_skip_reason`；**推荐前一种（加 GuidanceDecision）**。

### D6: expected region 只用 pre-tick prediction，因果无偏

expected region SHALL 只使用 **pre-tick global prediction**（该帧真正处理前系统预期 P1 在哪），MUST NOT 用 same-tick fused position（hindsight bias；且本次 P1 案例 formal observation 缺失时 fused 也缺失，fused 不能作为 fallback）。contract 使用：

```text
expected_region_status = available | prediction_unavailable | uncertainty_too_high | target_geometry_unavailable
```

仅 `available` 时计算 `eligible_detections_in_expected_gate`；否则该字段为 **`null`**（表示"连可靠 expected region 都没有"），MUST NOT 写 `0`（`0` 表示"知道该看哪里但无候选"，诊断意义不同）。

### D7: expected region 几何复用 guidance 规则（共享纯函数）

抽纯函数 `build_expected_player_region(predicted_position, uncertainty, target_geometry, policy)`，guidance 与 diagnostics **共用同一套 ROI 计算**（`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，cap `max_roi_margin_px`），MUST NOT 各写一套固定 ±gate_px——否则可能出现"diagnostics 说有候选 in gate、但 guidance 实际 ROI 根本不覆盖该候选"的误导。

### D8: 产物结构 flat 数组 + 时间窗口查询；身份直接存 canonical

`player-display-diagnostics.v1` 为 flat 数组：每个元素一个 `(canonical_tick, player_id, view_id)` 行，`player_id` **直接存 canonical `Player_N`**（run 内部暂存 global id，roster mapping 稳定后 canonicalize 再写正式产物）。API 直接 `filter rows where player_id == "Player_1"`，**不需要在 API 层反查 global id**。flat 结构便于前端直接渲染，也便于按 player 聚合。

**备选**：嵌套 `ticks → players → views` → 查询需深层过滤；正式 artifact 存 global id → 属于 internal diagnostic artifact，应只通过 API 暴露 canonicalized response，不应再给 `AnalysisArtifacts` 公开直链 URL。**选择 artifact 直接存 Player_N + API 直 filter**。

### D9: 诊断失败隔离（硬不变量）

显示诊断构建失败 MUST NOT 导致核心 joint 分析失败：core result 保持成功，`player_display_diagnostics_status=failed` + 结构化 reason。除非以后专门跑 diagnostic acceptance mode，否则显示诊断不是业务结果成功的硬依赖。

## Risks / Trade-offs

- [产物体积增长] → flat 行紧凑化（每行 < 300 字节，1815 ticks × 4 players × 2 views ≈ 1.5 万行 ≈ 4MB 量级），远小于 debug trace（127MB）；MVP 全量落盘，不做采样。
- [身份归因误导] → D2 强制 eligible detection 阶段只报 `eligible_detections_in_expected_gate`，不得描述为 raw YOLO hit；spec 以 scenario 约束。
- [association/guidance observability 侵入] → 严格只读：不改算法结果、不改门限、不改变返回；以 `last_tick_decisions` / `last_decisions` 附加记录实现，测试断言核心输出不变。
- [roster 中途变化] → 产物行以该 tick 当时的 roster 快照为准；正式产物用最终稳定映射 canonicalize。
- [前端默认展开造成性能/噪音] → 面板默认折叠，仅展开单球员单时刻（API 窗口模式），不做整场拉取。
- [诊断 bug 拖垮核心分析] → D9 硬不变量：diagnostics 失败不影响 core result，状态置 failed + reason。

## Migration Plan

- 后端新增模块与 route，AnalysisArtifacts 可选扩展字段；旧任务无该产物时 API 返回结构化 `unavailable` + reason，前端显示不适用状态。
- 无破坏性变更；`multiview-joint-observability` 页面新增入口，其余区域不动。
- `AssociationUpdate` / `GuidanceGenerator.generate()` 的返回与门限不变（只读 observability 附加），既有测试应全量保持通过。

## Open Questions

- `build_expected_player_region` 的默认 `base_roi_margin_px`（40px）与 cap `max_roi_margin_px`（160px）沿用 guidance 现有配置值；是否需要在 diagnostics 侧暴露配置覆盖入口？→ 建议 V1 只读复用，不提供覆盖。
- `available_miss_streak`（B-Phase-1 字段）是否一并纳入产物？→ 本 change 只记录 `binding_visibility`，miss streak 随 B-Phase-1 添加（避免本 change 提前引入感知语义改动）。
