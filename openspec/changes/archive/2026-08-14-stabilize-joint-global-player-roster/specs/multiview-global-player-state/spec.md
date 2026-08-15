# multiview-global-player-state Specification (Delta)

## Purpose

本 delta 为 `GlobalPlayerRegistry` 增加 roster 语义：知晓 `expected_player_count`、以 `allocate_roster_slot()` 替代公开的 `new_global_id()`、维护三级生命周期状态机（candidate → provisional occupant → confirmed）、candidate 生命周期、confirmed roster 不 GC、"存在与关联资格分离"（stale 玩家退出普通匹配）。

## Requirements

## ADDED Requirements

### Requirement: Registry roster 化

`GlobalPlayerRegistry` SHALL 在创建时接收 `expected_player_count`。registry SHALL 通过 `allocate_roster_slot()` 分配正式 global 身份，roster 满后返回 None；公开的 `new_global_id()` SHALL 不再作为普通 unmatched 观测的可用路径（仅在 roster reset / 重建等明确事件中由内部使用）。`predict_all()` SHALL 仅返回 roster 内且具备普通关联资格的 global 的预测；候选池（`candidate_N`）SHALL NOT 参与预测与关联匹配。

#### Scenario: 双打 roster 上限 4

- **WHEN** `expected_player_count=4` 且已分配 4 个 slot
- **THEN** 再次 `allocate_roster_slot()` SHALL 返回 None
- **AND** 候选池候选 SHALL 不进入 `predict_all()`

#### Scenario: 单打 roster 上限 2

- **WHEN** `expected_player_count=2`
- **THEN** roster 最多 2 个正式 global
- **AND** 多余观测 SHALL 停留在候选池或 unresolved

### Requirement: 三级生命周期状态机与确认

registry SHALL 维护 `candidate → provisional roster occupant → roster confirmed` 生命周期：candidate 晋升后成为 provisional occupant（占 slot），仅当全部 slot 均有 occupant 且每个 occupant 额外稳定 K 个 canonical tick 或至少一次可靠 cross-view anchoring 后，roster 才进入 `ROSTER_ACTIVE`。**slot 占满 SHALL NOT 使 roster 可信**；确认窗口内错误 occupant SHALL 可被推翻。

#### Scenario: 候选晋升为 occupant

- **WHEN** candidate 满足晋升规则
- **THEN** 其 SHALL 成为 provisional roster occupant（占 slot，参与融合与指标）
- **AND** registry SHALL 仍处于 BOOTSTRAPPING（未确认）

#### Scenario: 确认后进入 ACTIVE

- **WHEN** 全部 slot 占用且每 occupant 满足稳定 K tick 或 cross-view anchoring
- **THEN** registry SHALL 进入 `ROSTER_ACTIVE`
- **AND** 此后不创建新 global

#### Scenario: 占满未确认仍可推翻

- **WHEN** 4 个 occupant 均未满足确认条件
- **THEN** registry SHALL 保持 BOOTSTRAPPING
- **AND** 错误 occupant SHALL 可被弱绑定 / geometry 证据替换

### Requirement: 存在与普通关联资格分离

`GlobalPlayerState` 的"存在于 registry"与"有资格参与普通 association"SHALL 分离：当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家 SHALL 标记为 stale，退出普通紧门匹配（其预测不作为普通候选吸附观测），仅允许经 historical local continuity、guided recovery、strong reacquire 路径回归；恢复成功后重新获得普通资格。candidate 与从未 confirmed 的 tentative SHALL 可过期淘汰；已进入 roster 的 confirmed global 出画 SHALL 仅降级 weak → lost，等待 recovery，SHALL NOT 删除。仅 roster reset 才销毁。

#### Scenario: 候选过期

- **WHEN** candidate 长时间未达晋升条件
- **THEN** registry SHALL 将其过期清理
- **AND** 清理 SHALL 不影响 roster 内 global

#### Scenario: roster 内 P3 出画不删

- **WHEN** roster 内 Global P3 出画（binding 降级 lost）
- **THEN** GlobalPlayerState P3 SHALL 继续存在于 registry
- **AND** 恢复时 SHALL 复用原 global，不得创建新 global

#### Scenario: stale 不吸附

- **WHEN** Global P3 失踪超阈值
- **THEN** P3 的预测 SHALL 退出普通关联
- **AND** 其他观测 SHALL NOT 因 P3 的 stale 预测被误吸附

#### Scenario: 明确换场才重建

- **WHEN** 系统识别到 new_match / roster_reset / participant-change
- **THEN** registry SHALL 销毁现有 roster 并重新进入 `BOOTSTRAPPING`
- **AND** 普通遮挡 / epoch reset / 局盘切换 / 换边 SHALL 不触发重建
