# strengthen-multiview-cooperative-player-perception Specification

## Purpose
same-tick usable-candidate recovery：PreparedViewFrame 事务型两阶段 + pre-association（一对一匹配 + gate + ambiguity rejection，只读）→ same-tick guided ROI（donor 当前 base canonical evidence）→ merge → tracker.update once。解决"本 tick A 路有可靠 candidate、B 路缺失"的互补，不声称治疗投影/formal observation 下游问题。

## Requirements

### Requirement: Same-Tick Usable-Candidate Recovery（能力定义收窄）

系统 SHALL 提供 same-tick usable-candidate recovery：当某 global 在 donor view 当前 tick 存在可靠、可 canonical 化的 **base** pre-association candidate，而 target view 当前 tick **没有 usable candidate** 时，利用该 fresh cross-view evidence 在 tracker commit 前对 target view 做一次受控补检。target view 的失败状态 SHALL 至少区分 `candidate_absent / projection_failed / ambiguous / usable_candidate_present`。本能力 SHALL NOT 声称治疗投影/formal observation 失败：若两路 raw box 都有但两路 projection 都失败，系统 SHALL NOT 强制补检（属 projection repair 问题）。

#### Scenario: donor 有 usable candidate、target 缺失 → 补检

- **WHEN** 某 global 在 Cam2 当前 tick 有 strong base candidate（可 canonical pre-associate），Cam1 当前 tick `candidate_absent` 或 `projection_failed`
- **THEN** 系统 SHALL 对 Cam1 生成 same-tick guidance 并做受控补检
- **AND** 补检形成的 formal observation 走现有关联

#### Scenario: 两路 projection 都失败不强制

- **WHEN** 两路 raw box 都有但两路 court projection 都失败
- **THEN** 系统 SHALL NOT 强制 same-tick 补检
- **AND** 该情况 SHALL 记为 projection repair 问题（不视为本能力失败）

### Requirement: PreparedViewFrame 事务型两阶段

系统 SHALL 以事务型两阶段执行每 view 的 perception：`prepare_frame`（base YOLO → ROI filter → pre-tick guided ROI → merge，**不调用 tracker.update**，产出 `PreparedViewFrame` 含 `committed=False`）与 `complete_frame`（same-tick guided merge → **tracker.update 恰好一次** → project → selector/lock/identity → formal observation，置 `committed=True`）。**第二次 complete 同一 prepared 帧 SHALL 抛异常**（防重复 update）。原 `step()` SHALL 保持兼容旧调用（内部 prepare + complete 空 same-tick）。

#### Scenario: prepare 不 update tracker

- **WHEN** 调用方执行 `prepare_frame(frame, ...)`
- **THEN** 系统 SHALL 完成 base/ROI/pre-tick guided/merge
- **AND** SHALL NOT 调用 tracker.update

#### Scenario: complete 后 committed

- **WHEN** 调用方执行 `complete_frame(prepared, same_tick_guidance)`
- **THEN** 系统 SHALL merge → tracker.update 一次 → 后续链路
- **AND** `prepared.committed` SHALL 置 True

#### Scenario: 重复 complete 抛异常

- **WHEN** 调用方对同一 prepared 帧第二次调用 `complete_frame`
- **THEN** 系统 SHALL 抛出异常
- **AND** SHALL NOT 再次 update tracker

### Requirement: tracker.update-once 精确语义

系统 SHALL 保证：**successfully prepared and committed source frame → 每 view 恰好 1 次 tracker.update；任何 source frame → 至多 1 次**。frame unavailable / decode fail / view degraded 时 SHALL 为 0（不满足"恰好 1"）。

#### Scenario: 正常帧恰好一次

- **WHEN** 某 view 的 source frame 成功 prepared 且 committed
- **THEN** 该帧该 view 的 tracker.update 次数 SHALL 恰为 1

#### Scenario: 不可用帧为 0

- **WHEN** 某 view 的 frame unavailable / decode fail / view degraded
- **THEN** tracker.update 次数 SHALL 为 0
- **AND** 该情况 SHALL 不计入"恰好 1"要求

### Requirement: pre-association 只消费 ROI-filtered evidence + 一对一匹配

pre-association SHALL 只消费 `PreparedViewFrame.roi_filtered_base` 与成功的 `pre_tick_guided`（保留 origin provenance），MUST NOT 使用 ROI filter 之前的全部 raw YOLO detections（球场外人员不得成为强 candidate）。court projection SHALL 复用与 `PlayerProjector` 共用的纯函数（`image_to_court` + bounds 分类），MUST NOT 复制一套。匹配 SHALL 为每 view 一对一（min-cost）+ gate + ambiguity rejection：`residual ≤ pre_association_gate` 且 second-best margin 足够 → strong candidate；否则 `ambiguous`。`PreAssociationCandidate` SHALL 含 `matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`。

#### Scenario: 一对一匹配 + ambiguity rejection

- **WHEN** 某 candidate 与两个 global 预测的 residual 均 ≤ gate 且 margin 不足
- **THEN** 该 candidate SHALL 标记 `ambiguous`
- **AND** SHALL NOT 作为 same-tick donor（防 P1/P2 互换）

#### Scenario: 只消费 ROI-filtered

- **WHEN** 某 raw detection 在 ROI filter 之外（球场外）
- **THEN** pre-association SHALL NOT 将其视为 candidate
- **AND** 仅 `roi_filtered_base` 与成功 `pre_tick_guided` 参与

#### Scenario: 投影与 projector 一致

- **WHEN** pre-association 判定某 candidate 投影有效
- **THEN** 正式 `PlayerProjector` 对该 candidate 的投影判定 SHALL 一致（同一纯函数）
- **AND** 不得出现"pre-association 有效、projector 判 outside_tracking_area → drop"的不一致

### Requirement: same-tick guidance 使用当前 donor canonical evidence

same-tick guidance 的 ROI 中心 SHALL 使用 donor 当前 tick 的 canonical evidence：donor 当前 base candidate 成功 pre-associate 到某 global 且与该 global 的 pre-tick prediction 一致性通过 → 把 **current canonical position** 投影到 target view 形成 ROI。**MUST NOT 复制 donor 的 pixel bbox 到 target**。same-tick donor SHALL 严格限定为当前 source frame 的 **base** evidence（origin=base），MUST NOT 使用 pre-tick guided 作为 same-tick donor 再指导另一路（防 guided→guided 自我强化）。

#### Scenario: donor 当前位置投影 ROI

- **WHEN** Cam2 当前 base candidate pre-associate 到 G1 成功且与预测一致
- **THEN** same-tick ROI 中心 SHALL 为 Cam2 当前 canonical position 投影到 Cam1 的结果
- **AND** SHALL NOT 使用 Cam2 的 pixel bbox

#### Scenario: donor 严格 base

- **WHEN** 某 view 仅有 pre-tick guided evidence（origin=guided_roi）作为唯一 donor
- **THEN** 系统 SHALL NOT 将其作为 same-tick donor
- **AND** same-tick 补检 SHALL NOT 触发（防自我强化）

### Requirement: 共享 ROI budget

系统 SHALL 在每个 canonical tick 维护 `RecoveryAttemptLedger`（`attempted_pairs / roi_count_by_view / pre_tick_count / same_tick_count`），硬约束：`pre_tick_count[view] + same_tick_count[view] ≤ max_regions_per_view_per_tick`；同一 `(global, target)` 一 tick 默认最多真正跑一次 ROI。

#### Scenario: 共享预算不翻倍

- **WHEN** 某 view 本 tick pre-tick guidance 已用 3 个 ROI、`max_regions_per_view_per_tick=4`
- **THEN** same-tick guidance SHALL 最多再分配 1 个 ROI（合计 ≤ 4）
- **AND** MUST NOT 各自独立按 4 计算（翻倍成 8）

#### Scenario: 同 pair 去重

- **WHEN** 某 `(global, target)` 本 tick 已有 pre-tick ROI 尝试
- **THEN** same-tick 阶段 SHALL NOT 对该 pair 再次跑 ROI
- **AND** 记入 `attempted_pairs`

### Requirement: 不改变 association 算法

pre-association SHALL 只提供候选归属先验（供 same-tick ROI 决策），MUST NOT 改变 `GlobalPlayerAssociator.process_tick` 的算法、门限、候选晋升逻辑。正式关联仍由现有 `process_tick` 在 commit 后完成。回归测试 SHALL 断言 `process_tick` 输出与门限行为不变。

#### Scenario: association 语义不变

- **WHEN** same-tick 补检形成新的 formal observation
- **THEN** 该 observation SHALL 走现有 `process_tick` 普通关联
- **AND** `GlobalPlayerAssociator` 的匹配/门限/晋升逻辑 SHALL 与实施前一致

### Requirement: 配置与回退

系统 SHALL 提供 `same_tick_recovery_enabled` 配置开关（默认 True）与 `pre_association_gate_ft` / `ambiguity_margin` 参数。关闭时 SHALL 回退到实施前行为（base perception → pre-tick guidance → association，无 same-tick 互救）。

#### Scenario: 开关关闭回退现状

- **WHEN** `same_tick_recovery_enabled=false`
- **THEN** 系统 SHALL 不执行 pre-association 驱动的 same-tick 互救
- **AND** 行为与实施前一致（A/B 与回归基线）
