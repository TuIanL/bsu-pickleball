## Context

Phase 0 诊断（mvr_35ac365aec96 @ 00:07）实证 P1 消失根因：两路都有真实检测框（conf 0.71/0.86）但都没形成 formal observation。已核实代码路径：`PlayerProjector.project()`（`player_projector.py:72-73`）在投影落 `outside_tracking_area && drop_outside_tracking` 时丢弃该 track 的 `PlayerFramePosition`，但 `frame_detections` 仍可从 eligible tracks 生成；`_result_to_observations`（`multiview_joint_run.py:967-1042`）要求 matching `PlayerFramePosition` 且 `court_position != None` 否则跳过。**因此"画面有框但 positions 无此 track"是真实可能，同 tick ROI YOLO 不天然修复投影/formal observation 失败。**

前三个 change 已交付：诊断可观测（#1）、pre-tick recovery 触发加速（#2，含 `is_target_recovery_eligible` / `GuidanceDecision.trigger_source` / available-miss ledger）、展示稳定（#3，含 `OverlayDisplayStateMachine` / `ViewPersonScaleProfile` / 共享 `build_expected_player_region`）。本 Change（B-Phase-2）能力定义为：**same-tick usable-candidate recovery**——当另一视角当前 tick 提供可靠、非循环的 base canonical candidate，而 target view 当前没有 usable candidate 时，利用该 fresh cross-view evidence 在 tracker commit 前做一次受控补检。

当前主循环（`multiview_joint_run.py`）：`age_bindings → predict → guidance snapshot（pre-tick）→ View A/B perception（runtime.step 内一次完成 detect→guided→tracker→lock→identity）→ tick barrier → process_tick → fusion`。`JointViewRuntime.step()` 自己 `get_frame()` 解帧后调 `tracking_session.step()`。

## Goals / Non-Goals

**Goals:**

- 让"本 tick A 路有可靠 base candidate、B 路缺失"在**同一 canonical tick 内**完成 B 路受控补检。
- 保持 **tracker.update-once**：successfully prepared and committed source frame → exactly 1；任何 source frame → at most 1（frame unavailable / decode fail / view degraded → 0）。
- pre-association 只提供候选归属先验（一对一匹配 + gate + ambiguity rejection），不产生 AssociationUpdate、不修改 `process_tick`。
- same-tick 恢复单独计数，与 #2 的 next-tick fast path 增益可区分。

**Non-Goals:**

- **不声称治疗 00:07 P1 根因**（两路投影/formal 断裂属 projection repair，非本 Change）。
- 不做 raw detector 训练/替换、不做 appearance ReID、不做 projection repair。
- 不修改 `GlobalPlayerAssociator` 算法/门限/晋升逻辑。
- 不修改 tracker/lock/identity 语义（只拆事务边界）。
- 不改变 fused overlay 展示层（#3 已交付）。
- 不改变 pre-tick guidance 语义（#2 保持）。

## Decisions

### D1: PreparedViewFrame 事务型两阶段（保护 update-once）

`ViewTrackingSession` 拆为：

```python
@dataclass
class PreparedViewFrame:
    frame_index: int
    timestamp: float
    raw_detections: list            # 仅诊断（不参与 pre-association）
    roi_filtered_base: list         # 参与 pre-association 的 base evidence
    pre_tick_guided: list           # 成功 pre-tick guided evidence（origin=guided_roi）
    merged_pre_tick: list           # base + pre-tick guided merge 结果
    frame: object
    committed: bool = False

def prepare_frame(self, frame, frame_index, timestamp, pre_tick_guidance) -> PreparedViewFrame
    # base YOLO → ROI filter → pre-tick guided ROI → merge；不碰 tracker

def complete_frame(self, prepared, same_tick_guidance) -> ViewFrameResult
    # 若 prepared.committed → 抛异常（防重复 update）
    # same-tick guided ROI → merge → tracker.update 恰好一次 → project → selector/lock/identity
    # committed=True

def step(self, frame, frame_index, timestamp, guidance=()) -> ViewFrameResult
    # 兼容旧调用：prepare_frame(pre_tick_guidance=guidance) + complete_frame(空 same_tick)
```

**第二次 complete 同一 prepared 帧直接抛异常**——这是本次重构保护 update-once 最重要的工程措施。

### D2: JointViewRuntime 窄接口（Tasks 必须列入）

`JointViewRuntime` 拥有：

```python
def prepare(self, source_frame_index, timestamp_s, pre_tick_guidance, timing_context) -> PreparedViewFrame | None
    # get_frame() 解帧恰好一次（复用现有 get_frame，含 CAP_PROP_POS_FRAMES 修复）；decode 失败返回 None

def complete(self, prepared, same_tick_guidance, timing_context) -> ViewFrameResult | None
    # 转发 tracking_session.complete_frame
```

主循环 MUST NOT 越过 runtime 直接解帧；阶段 2 不重复解同一 source frame。`step()` 保留兼容旧调用。

### D3: 主循环两阶段重构（冻结顺序）

```text
GlobalState(t-1)
↓
生成既有 pre-tick guidance（#2 语义不变）
↓
每 view：runtime.prepare（decode 一次 → base YOLO → ROI filter → pre-tick guided → merge）
    （不 tracker.update）
════════ current-tick barrier ════════
两路 PreparedViewFrame 的 ROI-filtered evidence
↓
pre-association（对照 GlobalState(t-1) 预测 + 两路 evidence）
↓
same-tick opportunity selection
↓
same-tick guided ROI（donor 当前 canonical evidence 投影到 target）
↓
每 view：runtime.complete（merge → tracker.update ONCE → project → lock/identity → formal obs）
↓
GlobalPlayerAssociator.process_tick（算法不变）
↓
fusion
```

**pre-tick guidance 在 prepare 阶段消费**（#2 不废），same-tick 只在 pre-tick 未覆盖的缺失场景补充。barrier 保证两路 evidence 都准备好才做 same-tick 决策，避免一路先 update 造成时序错乱。

### D4: pre-association（只消费 ROI-filtered evidence + 一对一匹配）

- **输入**：`PreparedViewFrame.roi_filtered_base` + 成功的 `pre_tick_guided`（保留 origin provenance）；raw detections 仅诊断。MUST NOT 用 ROI filter 前的 raw（球场外人员不得成为强 candidate）。
- **投影**：court projection 抽与 `PlayerProjector` 共用的纯函数（`image_to_court` + bounds 分类），MUST NOT 复制一套——防"pre-association 说投影有效、正式 projector 说 outside_tracking_area → drop"的前后不一致。
- **匹配拍板（V1 冻结）**：每 view 一对一匹配（min-cost）+ gate + ambiguity rejection：

```python
candidate canonical points × GlobalState(t-1) predictions
→ min-cost one-to-one（复用 min_cost_matching）
且 residual ≤ pre_association_gate
且 second-best margin 足够（> ambiguity_margin）
→ strong candidate
否则 → ambiguous
```

- **字段落定**：`PreAssociationCandidate` 含 `matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`。正式 associator 完全不动。

### D5: same-tick guidance 用当前 donor canonical evidence

same-tick guidance 的 ROI 中心 SHALL 使用 **donor 当前 tick 的 canonical evidence**（非仅旧 prediction）：

```text
Cam2 current base candidate → pre-associate 到 G1 成功
→ candidate canonical position 与 G1 pre-tick prediction 一致性通过
→ 把 current canonical position 投影到 Cam1 → Cam1 same-tick ROI
```

**绝不复制 donor 的 pixel bbox 到 target**。ROI 尺寸复用 `build_expected_player_region`（#1 共享）。**donor 严格限定为当前 source frame 的 base evidence**（origin=base），MUST NOT 用 pre-tick guided 作为 same-tick donor 再指导另一路（防 guided→guided 自我强化，与 #2 的 donor origin 约束一致）。

### D6: 共享 ROI budget / RecoveryAttemptLedger

每个 canonical tick 建 `RecoveryAttemptLedger`：

```python
attempted_pairs: set[(global_id, target_view)]
roi_count_by_view: dict[view_id, int]
pre_tick_count: dict[view_id, int]
same_tick_count: dict[view_id, int]
```

硬约束：
- `pre_tick_count[view] + same_tick_count[view] ≤ max_regions_per_view_per_tick`（共享预算，避免事实上翻倍成 8）；
- 同一 `(global, target)` 一 tick 默认最多真正跑一次 ROI（attempted_pairs 去重）。

### D7: 不改变 association 算法

`process_tick` 输入仍是 `all_obs`（formal JointObservation 列表）。pre-association 只影响哪些 raw evidence 通过 guided 补检成为 formal observation，不改变 `process_tick` 内部匹配/门限/晋升。回归测试断言 `process_tick` 输出与门限不变（#2 基线保持）。

### D8: 诊断联动 + same-tick 单独计数

- 漏斗行新增 `pre_association_status`（`candidate_found / projection_failed / ambiguous / not_assessed`）与 `same_tick_guidance_status`（`generated / not_generated_no_cross_candidate / not_needed_observed / geometry_unavailable`）。
- same-tick 单独计数：`same_tick_opportunity_count / same_tick_guidance_generated_count / same_tick_roi_invocation_count / same_tick_formal_observation_count / same_tick_recovery_success_count`——MUST NOT 混入 #2 的 `guided_recovery_success_count`（证明增益来源）。

### D9: 配置与回退

`P1OnlineRecoveryConfig` 新增 `same_tick_recovery_enabled: bool = True`（同步进 policy，沿用 #2 配置真源模式）；`pre_association_gate_ft`（复用 `association_gate_ft` 语义，默认 3.0）；`ambiguity_margin`（默认 0.15，与 #0 association 的 switch_margin 对齐）。关闭时回退实施前行为。

## Risks / Trade-offs

- [同 tick 时序复杂 → update-once 被破坏] → D1 PreparedViewFrame.committed 防重复 + complete 抛异常；测试断言"successfully prepared and committed → exactly 1，任何 source frame → at most 1（unavailable/decode fail → 0）"。
- [pre-association 误判 → 错误 ROI] → 一对一匹配 + gate + ambiguity rejection；guided candidate 仍需 pre-gate（residual 门）通过才进 merge；误判最多浪费一次 ROI，不污染正式关联。
- [两路投影都失败时 same-tick 无效] → 能力定义明确收窄，不预设救回；验收只要求"至少一路 candidate 可 canonical pre-associate + 机制正确触发"。
- [guided→guided 自我强化] → D5 donor 严格 base origin；同 tick 内 guided 不得作为 donor。
- [ROI budget 翻倍] → D6 RecoveryAttemptLedger 共享预算硬约束。
- [回归风险高（动主循环）] → 大 change 独立实施；`same_tick_recovery_enabled=false` 回退现状。

## Migration Plan

- 后端新模块 `pre_association.py`；`ViewTrackingSession` 拆 prepare/complete（step 兼容）；`JointViewRuntime` 加 prepare/complete 窄接口；`multiview_joint_run.py` 主循环两阶段重构。
- `same_tick_recovery_enabled` 默认 True；关闭时行为回退现状。
- 契约向后兼容（漏斗行新字段缺省）。

## Open Questions

- same-tick guidance 的 ROI 尺寸：`build_expected_player_region`（共享）基于 donor canonical position + uncertainty → 投影 target；candidate bbox 仅作锚点。V1 沿用，真实素材验证后如需扩展再定。
- `RecoveryAttemptLedger` 与 #2 的 `_recovery_episode_by_target` 是否合并？→ V1 独立 ledger（attempt 预算）与 episode（归属）分离，职责清晰。
