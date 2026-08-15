# multiview-online-player-recovery Specification (Delta)

## Purpose

本 delta 强化 guided recovery 的身份约束：对 confirmed + cross_view_anchored 的 global player，guidance 明确的 `expected_global_player_id` 在 guided candidate（`detection_origin=guided_roi`）通过 target-view pre-gate 时成为强约束——优先恢复 expected global，不可行则 reject / unresolved，不得转投其他 global；同 tick base formal observation 优先于 guidance，stale guidance 不得覆盖 base evidence。

## Requirements

## MODIFIED Requirements

### Requirement: 在线恢复证据链

`joint_tracking_v2` SHALL 仅在 target view 从自身当前 source frame 的真实像素中重新获得 formal local player observation 后，声明一次 online recovery。该 observation SHALL 可追溯 donor view、guidance、target source frame、local player identity 与 identity epoch、source track、pre-gate residual 与 assigned global player。当 recovery 针对 `confirmed AND cross_view_anchored` 的 global player 时，assigned global SHALL 为 guidance 指定的 `expected_global_player_id`，除非几何不可行或 pre-gate 拒绝（此时记录 reject / unresolved，SHALL NOT 转投其他 global）。同 tick 的 base formal observation 正常走普通关联，stale guidance SHALL NOT 覆盖 base evidence（base 优先语义与 `base_recovered` 保持一致）。

#### Scenario: 双向 controlled dropout 恢复
- **WHEN** 已 anchored 的 global player 在 Cam1 变 weak、Cam2 保持可信 base observation，且 Cam1 当前 frame available
- **THEN** 系统 SHALL 使用 Cam2 donor guidance 在 Cam1 的真实像素中恢复 formal local player observation
- **AND** 恢复前、中、后的 global player identity SHALL 保持一致（即 guidance 指定的 expected global）

#### Scenario: 预测不构成恢复
- **WHEN** target ROI 未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 生成 target-view recovered observation
- **AND** SHALL NOT 将 prediction 或 guidance 计为 recovery

#### Scenario: guided 恢复不转投其他 global
- **WHEN** guidance 明确 `expected_global_player_id=G3`，Cam1 在 ROI 内通过 pre-gate 重新检测到球员，但该候选与 G2 的几何代价更低
- **THEN** 系统 SHALL 仍优先绑定回 G3
- **AND** SHALL NOT 因排序代价转投 G2

#### Scenario: guidance 目标不可行则拒绝
- **WHEN** guided candidate 与 G3 的几何距离超出该状态门限，或 pre-gate 拒绝
- **THEN** 系统 SHALL 将该候选记为 reject / unresolved
- **AND** SHALL NOT 将其分配给其他 roster global

#### Scenario: base 证据优先于 stale guidance
- **WHEN** 同 tick 的 base formal observation 已可靠看到目标球员，而 guidance 期望另一 global（陈旧）
- **THEN** base observation SHALL 走普通关联，guidance 强约束不覆盖
- **AND** 恢复 episode 按 base_recovered 记录，不计为 guided success
