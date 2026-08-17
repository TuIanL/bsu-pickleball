## MODIFIED Requirements

### Requirement: 触发语义扩展（pre-tick + same-tick + 共享 budget）

目标视角的 guidance 触发资格 SHALL 由共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)` 判定（#2 已交付）：`visibility in {"weak","missing","lost"}` 或（`fast_recovery_enabled` 且 `consecutive_available_misses >= 1`）时允许 **pre-tick guidance**。本 Change 扩展：当 `same_tick_recovery_enabled=true` 且**本 tick pre-association 发现另一路当前帧有 strong base candidate、本路无 usable candidate** 时，SHALL 允许生成 **same-tick guidance**（在 commit 前，不依赖 binding age）。same-tick guidance SHALL 复用 `CrossViewGuidance` 契约与 `guided_detection.py` 的 pre-gate/merge，MUST NOT 新增第二套检测路径；ROI 中心 SHALL 使用 donor 当前 canonical evidence（非仅旧 prediction），尺寸复用 `build_expected_player_region`；**donor 严格限定为当前 source frame 的 base evidence**（origin=base）。pre-tick 与 same-tick SHALL 共享 `RecoveryAttemptLedger` 预算：`pre_tick_count[view] + same_tick_count[view] ≤ max_regions_per_view_per_tick`，同一 `(global, target)` 一 tick 至多一次 ROI。

#### Scenario: same-tick guidance 触发

- **WHEN** `same_tick_recovery_enabled=true`，P1 本 tick 在 Cam1 有 strong base pre-association candidate、Cam2 无 usable candidate
- **THEN** 系统 SHALL 对 Cam2 生成 same-tick guidance（即使 pre-tick predicate 不满足）
- **AND** ROI 中心 SHALL 为 Cam1 当前 canonical position 投影

#### Scenario: donor 严格 base

- **WHEN** 某 view 仅有 pre-tick guided evidence（origin=guided_roi）作为唯一 donor
- **THEN** 系统 SHALL NOT 将其作为 same-tick donor
- **AND** same-tick 补检 SHALL NOT 触发（防 guided→guided 自我强化）

#### Scenario: 共享 budget 不翻倍

- **WHEN** 某 view 本 tick pre-tick guidance 已用 3 个 ROI、`max_regions_per_view_per_tick=4`
- **THEN** same-tick guidance SHALL 最多再分配 1 个 ROI（合计 ≤ 4）
- **AND** MUST NOT 各自独立按 4 计算

#### Scenario: 同 pair 去重

- **WHEN** 某 `(global, target)` 本 tick 已有 pre-tick ROI 尝试
- **THEN** same-tick 阶段 SHALL NOT 对该 pair 再次跑 ROI
- **AND** 记入 `RecoveryAttemptLedger.attempted_pairs`
