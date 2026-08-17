## Why

Phase 0 诊断（mvr_35ac365aec96 @ 00:07）实证：P1 在两路都有真实检测框（conf 0.71/0.86），但两路都没形成 formal observation——断点在 `detection → court_position 投影 → formal observation → association` 链路。已核实：`PlayerProjector.project()`（`player_projector.py:72-73`）在投影落 `outside_tracking_area && drop_outside_tracking` 时直接丢弃该 track 的 `PlayerFramePosition`，但 `frame_detections` 仍可生成，于是"画面有框但 positions 无此 track"确实可能发生；`_result_to_observations` 又要求 matching `PlayerFramePosition` 且 `court_position != None` 否则跳过。

**因此必须承认：同 tick 再跑一次 ROI YOLO 不天然修复"检测已存在但投影/formal observation 失败"。** 前三个 change 已交付诊断（#1）、pre-tick recovery 触发加速（#2）、展示稳定（#3），但均无法让"本 tick A 路有可靠 candidate、B 路缺失"在**同一 canonical tick 内**互补——当前 guidance 是 pre-tick snapshot（`multiview_joint_run.py:268-318` 在 `runtime.step()` 之前生成）。本 Change（B-Phase-2）的目标是：**same-tick usable-candidate recovery**——当另一视角当前 tick 提供可靠、非循环的 base canonical candidate，而 target view 当前没有 usable candidate 时，利用该 fresh cross-view evidence 在 tracker commit 前做一次受控补检。

## What Changes

- **能力定义收窄（核心修正）**：本 Change 的目标是 **same-tick usable-candidate recovery**，不是"治愈 00:07 P1 根因"。触发条件：某 global 在 donor view 当前 tick 存在可靠、可 canonical 化的 pre-association candidate，而 target view 当前 tick **没有 usable candidate**（区分 `candidate_absent / projection_failed / ambiguous / usable_candidate_present`）。若两路 raw box 都有但两路 projection 都失败，本 Change 可能仍救不了——那是 projection repair 问题，不是本 Change 的实现失败。00:07 保留做真实验收，但验收**不预设 P1 必须被救回**，只要求证明"至少一路 candidate 能成功 canonical pre-associate"且 same-tick 机制正确触发。
- **PreparedViewFrame 事务型两阶段**（保护 tracker.update-once 的工程措施）：`ViewTrackingSession` 拆为 `prepare_frame(frame, frame_index, timestamp, pre_tick_guidance)`（base YOLO → ROI filter → pre-tick guided ROI → merge，**不碰 tracker**，产出 `PreparedViewFrame` 含 `committed=False`）与 `complete_frame(prepared, same_tick_guidance)`（same-tick guided merge → **tracker.update 恰好一次** → project → selector/lock/identity → formal observation，置 `committed=True`）。**第二次 complete 同一 prepared 帧直接抛异常**。原 `step(frame, ..., guidance=...)` 内部调 prepare + complete，单摄/旧调用行为不变。
- **主循环两阶段重构（冻结顺序，消除 D2/D3 矛盾）**：

```text
GlobalState(t-1)
↓
生成既有 pre-tick guidance（#2 语义不变）
↓
每 view：decode frame ONCE → base YOLO → ROI filter → pre-tick guided ROI → merge
    （不 tracker.update）
════════ current-tick barrier ════════
两路当前 detection evidence
↓
pre-association（只读 GlobalState(t-1) 预测 + 本 tick 两路 ROI-filtered evidence）
↓
same-tick opportunity selection
↓
same-tick guided ROI（donor 当前 canonical evidence 投影）
↓
merge
════════ commit ════════
每 view：tracker.update ONCE → project → selector/lock/identity → formal JointObservation
↓
GlobalPlayerAssociator.process_tick（算法不变）
↓
fusion
```

- **JointViewRuntime 也要改（Tasks 必须列入）**：`JointViewRuntime` 拥有 `prepare(...)` / `complete(...)` 窄接口（内部 `get_frame()` 解帧恰好一次 + 转发 tracking session），主循环不越过 runtime 直接解帧、阶段 2 不重复解同一 source frame。
- **pre-association 只消费 ROI-filtered base + 成功 pre-tick guided**（非全部 raw YOLO）：球场外工作人员/背景人物不得成为强 candidate；`PreparedViewFrame` 同时保存 raw detections 仅用于诊断。court projection 抽与 `PlayerProjector` **共用**的纯函数（`image_to_court` + bounds 分类），MUST NOT 复制一套，防"pre-association 说投影有效、正式 projector 说 outside_tracking_area → drop"的前后不一致。
- **pre-association 匹配拍板**：每 view 一对一匹配（min-cost）+ gate + ambiguity rejection：`residual ≤ pre_association_gate` 且 second-best margin 足够 → strong candidate；否则 `ambiguous`。`PreAssociationCandidate` 字段落定：`matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`。
- **same-tick guidance 用当前 donor canonical evidence**（不只沿用旧 prediction）：Cam2 当前 base candidate 成功 pre-associate 到 G1 且与 G1 pre-tick prediction 一致性通过 → 把**当前 canonical position** 投影到 Cam1 形成 same-tick ROI。**绝不复制 donor 的 pixel bbox 到 target**。same-tick donor 严格限定为当前 source frame 的 **base** evidence（MUST NOT 用 pre-tick guided 作为 same-tick donor 再指导另一路，防 guided→guided 自我强化）。
- **共享 ROI budget / RecoveryAttemptLedger**：每个 canonical tick 建 `RecoveryAttemptLedger`（`attempted_pairs / roi_count_by_view / pre_tick_count / same_tick_count`），硬约束 `pre-tick + same-tick ≤ max_regions_per_view_per_tick`，同一 `(global, target)` 默认一 tick 最多真正跑一次 ROI。
- **不改变 association 算法**：pre-association 只提供候选归属先验，不产生 AssociationUpdate、不写 mapping；正式关联仍由 `process_tick` 完成（回归测试锁定）。
- **诊断联动**：漏斗行新增 `pre_association_status / same_tick_guidance_status`；same-tick 单独计数（`same_tick_opportunity_count / same_tick_guidance_generated_count / same_tick_roi_invocation_count / same_tick_formal_observation_count / same_tick_recovery_success_count`），不与 #2 的 guided success 混同（证明增益来源）。
- **scope 边界（明确不做）**：不做 raw detector 训练/替换、不做 appearance ReID、不做 projection repair（两路投影都失败属于另一问题）、不修改 `GlobalPlayerAssociator` 算法/门限、不修改 tracker/lock/identity 语义、不改变 fused overlay 展示层。

## Capabilities

### New Capabilities

- `strengthen-multiview-cooperative-player-perception`: same-tick usable-candidate recovery——PreparedViewFrame 事务型两阶段 + pre-association（一对一匹配 + gate + ambiguity rejection，只读）→ same-tick guided ROI（donor 当前 base canonical evidence）→ merge → tracker.update once。解决"本 tick A 路有可靠 candidate、B 路缺失"的互补，不声称治疗投影/formal observation 下游问题。

### Modified Capabilities

- `view-tracking-session`: `prepare_frame` / `complete_frame` 事务型两阶段（committed 防重复 update），`step()` 兼容旧调用；pre-association 只消费 ROI-filtered evidence。
- `joint-view-runtime`: `prepare()` / `complete()` 窄接口（解帧一次 + 转发），主循环不越过 runtime。
- `cross-view-player-guidance`: same-tick guidance 扩展（donor 当前 base canonical evidence 投影 ROI，donor 严格 base origin），与 pre-tick 共享 ROI budget。
- `multiview-player-association`: pre-association 一对一匹配 + ambiguity rejection（只读归属先验），`process_tick` 算法不变。
- `multiview-online-player-recovery`: same-tick 恢复单独计数（不混入 #2 guided success）。
- `player-display-diagnostics`: 漏斗行新增 `pre_association_status / same_tick_guidance_status`。

## Impact

- **后端**：`backend/app/vision/multiview/pre_association.py`（新）、`backend/app/vision/player_tracking_engine/view_tracking_session.py`（prepare/complete 事务拆步）、`backend/app/vision/multiview/joint_view_runtime.py`（prepare/complete 窄接口）、`backend/app/vision/multiview/multiview_joint_run.py`（主循环两阶段 + RecoveryAttemptLedger）、`backend/app/vision/multiview/guidance.py`（same-tick guidance + budget 共享）、`backend/app/vision/player_tracking_engine/player_projector.py`（抽共享 projection 纯函数）、`backend/app/vision/multiview/player_display_diagnostics.py`（新字段）、`backend/app/vision/multiview/recovery_config.py`（`same_tick_recovery_enabled`）。
- **契约**：`player-display-diagnostics.v1` 行结构新增两字段（向后兼容）。
- **测试**：pre-association（一对一匹配 / ambiguity rejection / 只消费 ROI-filtered / projection 与 projector 一致）；PreparedViewFrame（committed 防重复 / 第二次 complete 抛异常 / step 兼容）；same-tick 双向恢复（A 有 B 无 → B 补检 / 两路均无 → 不制造 / update-once 断言 / donor 严格 base / budget 共享）；回归（process_tick 不变 / `same_tick_recovery_enabled=false` 回退）；真实素材验收（00:07 证明至少一路 candidate 可 canonical pre-associate + same-tick 机制正确触发，不预设 P1 被救回）。
- **OpenSpec**：新增 capability `strengthen-multiview-cooperative-player-perception`；MODIFIED `view-tracking-session`、`joint-view-runtime`、`cross-view-player-guidance`、`multiview-player-association`、`multiview-online-player-recovery`、`player-display-diagnostics`。
