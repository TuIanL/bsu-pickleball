## 1. Pre-Association Candidate Layer

- [x] 1.1 新增 `backend/app/vision/multiview/pre_association.py`：`PreAssociationCandidate` dataclass（`matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`）+ `pre_associate()`（**只消费 ROI-filtered base + 成功 pre-tick guided**，一对一 min-cost 匹配 + gate + ambiguity rejection，对照 GlobalState(t-1) 预测）
- [x] 1.2 court projection 抽与 `PlayerProjector` 共用的纯函数（`image_to_court` + bounds 分类），pre-association 与正式 projector 共用，MUST NOT 复制一套（防前后不一致）
- [x] 1.3 只读性保证：pre-associate 只读 GlobalState(t-1) 预测，MUST NOT 修改状态 / mapping / tracker；投影失败 candidate 保留（projection_status 标记）
- [x] 1.4 `P1OnlineRecoveryConfig` 新增 `same_tick_recovery_enabled: bool = True`、`pre_association_gate_ft`（默认 3.0）、`ambiguity_margin`（默认 0.15）；`CrossViewGuidancePolicy` 同步（沿用 #2 配置真源模式）

## 2. PreparedViewFrame 事务型两阶段

- [x] 2.1 `view_tracking_session.py`：新增 `PreparedViewFrame` dataclass（frame_index / timestamp / raw_detections（仅诊断）/ roi_filtered_base / pre_tick_guided / merged_pre_tick / frame / committed=False）+ `prepare_frame()`（base → ROI filter → pre-tick guided → merge，**不 update tracker**）+ `complete_frame()`（same-tick guided merge → **tracker.update 恰好一次** → project → selector/lock/identity → formal observation，置 committed=True；**第二次 complete 抛异常**）
- [x] 2.2 `step()` 保持兼容旧调用（内部 prepare + complete 空 same-tick）；tracker.update-once 精确语义（successfully committed → exactly 1；任何 source frame → at most 1；unavailable/decode fail/degraded → 0）加测试断言

## 3. JointViewRuntime 窄接口

- [x] 3.1 `joint_view_runtime.py`：新增 `prepare(source_frame_index, timestamp_s, pre_tick_guidance, timing_context) -> PreparedViewFrame | None`（get_frame 解帧恰好一次，decode 失败返回 None）与 `complete(prepared, same_tick_guidance, timing_context) -> ViewFrameResult | None`（转发 complete_frame，committed 语义保持）；`step()` 保留兼容旧调用
- [x] 3.2 主循环 MUST NOT 越过 runtime 直接解帧；same-tick 阶段不重复解同一 source frame

## 4. Same-Tick Bidirectional Recovery（主循环重构）

- [x] 4.1 `multiview_joint_run.py` 主循环两阶段重构（冻结顺序）：prepare 阶段（每 view decode 一次 + base/ROI/pre-tick guided/merge，不 update）→ **current-tick barrier** → pre-association → same-tick opportunity selection → same-tick guided ROI（donor 当前 canonical evidence 投影）→ commit 阶段（每 view tracker.update ONCE → project → lock/identity → formal observation）→ process_tick
- [x] 4.2 same-tick guidance 复用 `CrossViewGuidance` + `guided_detection.py` pre-gate/merge；ROI 中心用 donor 当前 canonical position 投影（非仅旧 prediction），尺寸复用 `build_expected_player_region`；**donor 严格 base origin**（MUST NOT 用 pre-tick guided 作 same-tick donor）
- [x] 4.3 `RecoveryAttemptLedger`（attempted_pairs / roi_count_by_view / pre_tick_count / same_tick_count）：`pre-tick + same-tick ≤ max_regions_per_view_per_tick` 硬约束 + 同 `(global,target)` 去重
- [x] 4.4 `same_tick_recovery_enabled=false` 时回退实施前行为（A/B 与回归基线）

## 5. 诊断联动

- [x] 5.1 `player_display_diagnostics.py`：漏斗行新增 `pre_association_status`（candidate_found / projection_failed / ambiguous / not_assessed）与 `same_tick_guidance_status`（generated / not_generated_no_cross_candidate / not_needed_observed / geometry_unavailable），缺省兼容
- [x] 5.2 same-tick 单独计数：`same_tick_opportunity_count / same_tick_guidance_generated_count / same_tick_roi_invocation_count / same_tick_formal_observation_count / same_tick_recovery_success_count`（不混入 #2 guided_recovery_success_count）
- [x] 5.3 `src/types/report.ts`：`PlayerDisplayDiagnosticsRow` 新增两可选字段；诊断面板展示（可选）

## 6. 测试与验收

- [x] 6.1 后端单测：pre-association（一对一匹配 / ambiguity rejection / 只消费 ROI-filtered / 投影与 projector 一致 / 只读不写 mapping）
- [x] 6.2 后端单测：PreparedViewFrame（committed 防重复 / 第二次 complete 抛异常 / step 兼容 / update-once 精确语义：unavailable→0、committed→1）
- [x] 6.3 后端单测：same-tick 双向恢复（donor 有 base candidate target 无 → 补检成功；两路 projection 均失败 → 不强制；donor 严格 base；budget 共享不翻倍；同 pair 去重）
- [x] 6.4 后端回归测试：`GlobalPlayerAssociator.process_tick` 输出与门限不变（#2 基线保持）；`same_tick_recovery_enabled=false` 回退现状
- [x] 6.5 前端测试：诊断面板展示新字段；缺失按未评估显示
- [x] 6.6 真实素材验收（`mvr_35ac365aec96` / job-95132a7a53 @ 00:07）：**不预设 P1 必须被救回**——报告 `pre_association_status / same_tick_guidance_status / same_tick_*` 计数；验证"至少一路 candidate 可成功 canonical pre-associate + same-tick 机制正确触发"；若 P1 因两路 projection 均失败未救回，如实报告为 projection repair 问题（不视为本 Change 失败）；A/B 对比 `same_tick_recovery_enabled` on/off 的 `same_tick_recovery_success_count`
