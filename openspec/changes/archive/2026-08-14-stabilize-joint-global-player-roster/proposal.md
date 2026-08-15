## Why

双摄 joint_tracking_v2 真实任务（job-f473d041a6）产出 47 个 `global_player_N`（fused 样本 7858 个、47 个不同 global id），而场上只有 4 名球员。本地 P1-P4 锁定（`eligibility_policy="lock_only"`）已正确生效，`_result_to_observations` 也只放行带正式 local identity 的观测——问题集中在 Global 层：`GlobalPlayerAssociator` 对 unmatched 观测无条件调用 `GlobalPlayerRegistry.new_global_id()`，registry 无人数上限、无候选池、无状态机，把一次次局部失配（3ft 硬门、epoch reset、同步偏差）解释成"新的人出现"。同时 joint compose 不产出与单摄同契约的 structured visualization data，前端被迫降级展示旧 PNG 热力图（`global_player_47 球员位置热力图`）。

## What Changes

- **新增 Global Roster（全局比赛球员名单）概念**：`GlobalPlayerRegistry` 首次知晓本场比赛人数（`expected_player_count`，来自 `match_context`），以固定 roster 替代开放式 `players` dict；`new_global_id()` 不再公开为普通 unmatched 可用路径，改为 `allocate_roster_slot()`，roster 满后返回 None。
- **新增 Global Roster Candidate 候选池（含自身归属规则）**：unmatched formal observation 先进入 `GlobalRosterCandidate`（候选 id 前缀 `candidate_`，**禁止使用 `global_player_N`**）。下一 tick 观测归属 candidate 的判定按优先级：同 `(view_id, view_player_id, epoch)` 强 key 复用 → 跨 epoch 弱 prior → canonical geometry → 才新建；同 tick 同 candidate 每 view 至多一个 observation。连续稳定证据达标（双视角一致 ≥2 tick，或单视角 formal identity 稳定 ≥5 tick；参数后定）晋升；瞬时异常只能产生 transient candidate 并过期。
- **三级生命周期与 roster 确认（slot 占满 ≠ roster 可信）**：`candidate → provisional roster occupant → roster confirmed`。`ROSTER_ACTIVE` 仅在全部 slot 有 occupant **且每个 occupant 额外稳定 K tick 或至少一次可靠 cross-view anchoring** 后进入；进入后系统从"发现谁在场上"切换为"寻找这四个人现在在哪里"，后续 unmatched 只能 unresolved / recovery / reject，**禁止再创建 G5**。
- **roster 重建边界与 identity_reset 严格分离**：只有 `new_match`、显式 `roster_reset`、明确确认的 participant-change / substitution 事件才重建 roster；**普通 local identity epoch reset、局/盘切换、换边 SHALL NOT 触发 roster 重建**。
- **两级 identity continuity**（修改现有 spec 的"epoch reset 不继承 prior"）：强绑定 `(view_id, Player_N, epoch) → global` 在 epoch reset 后失效的规则保留；新增弱历史绑定 `(view_id, Player_N) → global`，epoch reset 后观测可经 geometry / donor / prediction 重新证明回原 global，但不无脑继承、也不无脑新建。
- **关联 gate 升级为 uncertainty-aware**：固定 `3.0 ft` 硬门改为 `gate = min(max_reacquire_gate_ft, base_gate_ft + uncertainty_scale × prediction_uncertainty_ft)`，不同状态（稳定连续 / 历史 local 重连 / 跨 epoch reacquire / 换人尝试）使用不同门宽；参数须用真实双摄 trace 的 residual 分布标定，不预拍。
- **PendingReassociation 多帧强证据迟滞**：一帧"强证据"须同时满足 challenger geometry 可行、cost 优于 incumbent 超过 `switch_margin`（默认 0.15，可调）、challenger global 连续一致；连续 `reassociation_frames`（默认 5）帧才切换，challenger 变化则计数清零；替代现有 `local_identity_switch_penalty` cost penalty，避免网前交叉跑位单帧换色。
- **Guided recovery 强身份约束（guided 观测专用，base 优先）**：confirmed + cross_view_anchored + guidance 明确 `expected_global_player_id=G3` + guided candidate（`detection_origin=guided_roi`）通过 target-view pre-gate 时，优先只恢复 G3；G3 几何不可行 / pre-gate 拒绝则 reject / unresolved，不转投 G2。该强约束不作用于 base formal observation——同 tick base 证据正常走普通关联，stale guidance 不覆盖 base evidence。
- **Confirmed roster 不参与普通 GC，但"存在"与"关联资格"分离**：candidate / 未 confirmed 的 tentative 可过期淘汰；roster 内 confirmed 出画只降级 weak → lost 等待 recovery，不删除；当 `uncertainty > threshold` 或 `last_seen_age > threshold` 时该玩家退出普通紧门匹配（不吸附观测），仅经 historical continuity / guided recovery / strong reacquire 回归。
- **新增 `global-player-roster.v1` 产物（诊断 / 映射 contract）与 Global→canonical Player 映射（reference view display anchor）**：内部保留 `global_player_N` 讨论；canonical `Player_N` 由 reference view 的 formal local identity 决定（稳定绑定 `cam_1/Player_3` 则公开为 `Player_3`；仅有 non-reference evidence 时暂缓分配；整场 reference 缺失用 deterministic fallback）。用户可见 trajectory / metrics / structured visualization / report 一律 `Player_1..4 / P1..P4`，MUST NOT 出现 `global_player_`；joint 路径生成与单摄同契约的 `structured/data.json`（22×10 网格、P1-P4），复用 `PositionVisualizationDataBuilder`。
- **球员计数语义**：区分 `expected_player_count` / `roster_occupied_count` / `confirmed_player_count` / `observed_player_count`，报告按实际确认 / 观测人数如实呈现，MUST NOT 为避免 47 类计数而硬写赛制人数。
- **F1 offline refinement 冻结 roster 映射**：F1 可补 observation、改善 fused position，但 SHALL NOT 修改 `global → Player_N` 映射、SHALL NOT 分配新 slot；roster snapshot 与 F0 snapshot 一起冻结。

## Capabilities

### New Capabilities
- `multiview-global-player-roster`: 全局比赛球员名单（fixed roster、candidate pool 与自身归属规则、三级生命周期 candidate→occupant→confirmed、BOOTSTRAPPING→ROSTER_ACTIVE 状态机、roster 重建边界与 identity_reset 分离、confirmed roster 不 GC 但 stale 退出普通关联、球员计数语义、F1 冻结、`global-player-roster.v1` 诊断产物与 reference-view display anchor 映射）

### Modified Capabilities
- `multiview-player-association`: `GlobalPlayerAssociator` 的 unmatched 处理从"立即 new_global_id"改为"进 candidate pool / unresolved"；固定 3ft 几何门改为 uncertainty-aware gate；增加 `PendingReassociation` 多帧强证据迟滞（switch_margin + 连续一致）；增加历史 local-slot 弱绑定（修改"identity epoch reset 不继承 prior"，且明确 epoch reset 不触发 roster 重建）；guided `expected_global_player_id` 从 ranking penalty 升级为强约束（仅约束 guided_roi 观测，base 优先）；stale roster 玩家退出普通关联。
- `multiview-global-player-state`: `GlobalPlayerRegistry` 增加 `expected_player_count` 与 `allocate_roster_slot()`（替代公开 `new_global_id()`）、三级生命周期状态机、候选池生命周期、存在与关联资格分离（stale 退出普通匹配）、confirmed roster 玩家不因长时间缺失被 GC。
- `multiview-online-player-recovery`: guidance 对 confirmed + cross_view_anchored 的目标玩家，在 guided candidate 通过 pre-gate 时要求优先恢复 `expected_global_player_id`，不可行时 reject / unresolved，不得转投其他 global；同 tick base formal observation 优先于 stale guidance。
- `multiview-analysis-result-composer`: joint compose 产出 `global-player-roster.v1`（诊断 contract）与 Global→canonical Player 映射（reference view display anchor）；公开轨迹身份一律 `Player_1..4 / P1..P4`；joint 路径生成与单摄同契约的 structured visualization data（而非仅旧 PNG heatmap）；球员计数按明确语义区分；F1 不改变 roster 映射。

## Impact

- `backend/app/vision/multiview/global_state.py`：`GlobalPlayerRegistry` roster 化（expected_player_count / allocate_roster_slot / 三级状态机 / 候选池 / stale 关联资格 / GC 策略）。
- `backend/app/vision/multiview/association_global.py`：`GlobalPlayerAssociator.process_tick` unmatched 分流、candidate 归属、uncertainty-aware gate、两级 continuity、PendingReassociation 强证据、guided 强约束 + base 优先。
- `backend/app/vision/multiview/offline_refinement.py`：F1 冻结 roster 映射（消费冻结的 roster snapshot）。
- `backend/app/vision/multiview/guidance.py` / `multiview_joint_run.py`：如涉及 candidate / roster 状态读取与 guidance 强约束的接线。
- `backend/app/services/multiview_result_composer.py`：`compose_joint_result` 增加 roster.v1 产物、Global→Player 映射（reference anchor）、structured data 生成（复用 `PositionVisualizationDataBuilder`）、球员计数语义。
- `backend/app/services/multiview_joint_executor.py`：创建 registry / associator 时传入 `match_ctx.expected_player_count`。
- `backend/app/vision/pickleball_game_analysis/visualization_data_builder.py`：joint 路径复用其生成 structured data（接受 roster 映射后的 `Player_N` 标签）。
- 前端：预期无改动（structured-heatmap 契约已支持 `Player_1..4`，joint 生成同契约数据后自动走 SVG）。
- 测试：`backend/tests/` 新增 roster 硬断言（整场 `registry.players ≤ expected_player_count`；roster 确认前不 ACTIVE；roster 关闭后不创建 G5；epoch reset 重回同一 global 且不重建 roster；N-1 帧不切换 / N 帧强证据才切换；guided 恢复不转投且 base 优先；用户可见产物无 `global_player_`；`heatmaps.players[].id` 仅 `Player_1..4`；F1 不改映射）；用 job-f473d041a6 同源素材重跑验收 47 条轨迹消失、报告如实报告确认人数。
