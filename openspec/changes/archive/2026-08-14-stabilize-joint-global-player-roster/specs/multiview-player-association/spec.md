# multiview-player-association Specification (Delta)

## Purpose

本 delta 修改 `GlobalPlayerAssociator` 的行为：unmatched 观测不再立即创建 `global_player_N`，改为进入 candidate pool / unresolved；固定 3ft 几何门升级为 uncertainty-aware gate；增加 `PendingReassociation` 多帧强证据迟滞（含 switch_margin）；增加历史 local-slot 弱绑定；guided `expected_global_player_id` 升级为强约束（仅约束 guided_roi 观测，base 优先）；stale roster 玩家退出普通关联。P0 `CrossViewPlayerAssociator` 语义保持不变。

## Requirements

## MODIFIED Requirements

### Requirement: 关联迟滞

跨视角关联 SHALL 存在 association hysteresis：已建立 `A ↔ X` 关联后，即使下一帧出现略优的候选匹配，系统 SHALL NOT 立即换人；仅当连续多帧产生强证据时才 reassociate。系统 SHALL 通过 `PendingReassociation` 状态跟踪"候选换人"证据，**一帧计为强证据 SHALL 同时满足**：① challenger geometry 可行（相应状态门限内）；② challenger cost 比 incumbent 好超过 `switch_margin`（默认配置 0.15，可调）；③ challenger 指向的 global 连续一致。连续达到 `reassociation_frames`（默认 5，可配置）帧强证据才正式切换，否则保持原绑定；challenger 每帧变化或证据中断则计数清零；切换 SHALL 在 diagnostics 中记录。

#### Scenario: 保持既有关联

- **WHEN** 已有 `A ↔ X` 关联且下一帧出现略优候选
- **THEN** 系统 SHALL 保持 `A ↔ X`
- **AND** 系统 SHALL NOT 因单帧略优即切换

#### Scenario: 强证据 reassociate

- **WHEN** 连续多帧产生强证据表明另一匹配更可信
- **THEN** 系统 SHALL 允许 reassociate
- **AND** 系统 SHALL 在 diagnostics 中记录该身份切换

#### Scenario: 微弱优势不累积换人

- **WHEN** challenger 每帧只比 incumbent 好 0.01（低于 `switch_margin`）
- **THEN** 该帧 SHALL NOT 计为强证据
- **AND** 计数 SHALL 不累积，绑定保持不变

#### Scenario: challenger 变化则清零

- **WHEN** 连续帧中 challenger 指向的 global 不一致（每帧不同 challenger）
- **THEN** 强证据计数 SHALL 清零
- **AND** 绑定 SHALL 保持不变

#### Scenario: 交叉跑位不单帧换色

- **WHEN** 网前两名球员交叉跑位，单帧另一 candidate 距离更近
- **THEN** 系统 SHALL NOT 单帧切换
- **AND** 仅当连续 `reassociation_frames` 帧该 candidate 持续为强证据才切换

### Requirement: GlobalPlayerAssociator(新类)

系统 SHALL 提供 `GlobalPlayerAssociator`(**新类,不修改 P0 `CrossViewPlayerAssociator`**),以 `GlobalState.predict(t)` 为中心,将各视角观测分配到 global states:

```text
GlobalState.predict(t)
    ├── assign Cam1 observations → global states
    ├── assign Cam2 observations → global states
    ├── unmatched observations → candidate pool（roster 未满时，按候选归属规则累积）
    ├── unmatched observations → unresolved（roster 已满时）
    └── fusion/update GlobalState(t)
```

该关联器 SHALL 复用 Change 0 的 `min_cost_matching()` 作为共享 primitive(含 rectangular 匹配与 per-candidate prediction 修复)。P0 `CrossViewPlayerAssociator`(reference-centric)SHALL 语义不变,仅在 `late_fusion_v1` 使用。

#### Scenario: 观测分配到全局

- **WHEN** 某 tick 两路分别产生观测
- **THEN** 系统 SHALL 用 pre-tick GlobalState 预测,将各视角观测分配到对应 global player
- **AND** 未匹配观测 SHALL 进入 candidate pool（roster 未满时），不得立即获得 `global_player_N`

#### Scenario: P0 associator 语义不变

- **WHEN** `executionMode=late_fusion_v1`
- **THEN** `CrossViewPlayerAssociator` SHALL 按 P0 reference-centric 语义工作
- **AND** `GlobalPlayerAssociator` SHALL 仅作用于 joint_tracking_v2 路径

#### Scenario: roster 满后未匹配进 unresolved

- **WHEN** registry 处于 `ROSTER_ACTIVE` 且观测无法匹配 P1-P4
- **THEN** 该观测 SHALL 记为 unresolved / recovery / noise
- **AND** SHALL NOT 创建新 global player

### Requirement: geometry-gated identity continuity prior

`GlobalPlayerAssociator` SHALL 先以 canonical distance 应用 hard feasibility gate，随后才以 stable local identity key `(view_id, view_player_id, local_identity_epoch)` continuity 和 guided `expected_global_player_id` 作为 ranking penalty/prior。历史 mapping 的 fallback SHALL 遵守同一 hard gate，identity prior SHALL NOT 强制分配不可行 global。

系统 SHALL 维护两级 continuity：

- **强绑定（exact epoch）**：`(view_id, view_player_id, local_identity_epoch) → global`。epoch 变化时该强绑定 SHALL 失效（与现有 spec 一致）。
- **弱历史绑定（historical local-slot）**：`(view_id, view_player_id) → global`。epoch reset 后该弱绑定 SHALL 仍保留，作为"很可能仍是过去该视角的 P3"的先验；观测必须重新通过 geometry / donor view / prediction 证明后才能复用原 global，证据不足时进入 unresolved（roster 满）或候选池（roster 未满），SHALL NOT 自动继承、也 SHALL NOT 创建新 global。

**identity epoch reset 是局部跟踪生命周期事件**，只影响该 view 的强绑定，SHALL NOT 触发 global roster 重建（重建仅由 new_match / roster_reset / participant-change 触发）。

#### Scenario: 历史 mapping 超出几何门
- **WHEN** 一个 local player 的历史 global mapping 与当前 canonical observation 距离超过 association gate
- **THEN** 系统 SHALL NOT 直接复用该 mapping
- **AND** diagnostics SHALL 记录 geometry-infeasible continuity rejection

#### Scenario: identity epoch reset 不继承强 prior
- **WHEN** `Player_3` 从 identity epoch 0 reset 到 epoch 1
- **THEN** epoch 1 observation SHALL NOT 继承 epoch 0 的强 continuity prior
- **AND** 系统 SHALL 依据弱历史绑定 `(view_id, Player_3)` 尝试重新证明回原 global

#### Scenario: epoch reset 后重新证明成功
- **WHEN** epoch reset 后的观测在几何 / donor / prediction 证据下与弱历史绑定指向的 global 一致
- **THEN** 系统 SHALL 将其重新绑定到原 global（epoch 更新为当前值）
- **AND** SHALL NOT 创建新 global

#### Scenario: 证据不足不新建
- **WHEN** epoch reset 后的观测无法通过几何 / donor / prediction 证明属于任何 roster 内 global
- **THEN** 系统 SHALL 将其记为 unresolved（roster 满时）或候选（roster 未满时）
- **AND** SHALL NOT 仅因 epoch 变化创建新 `global_player_N`

#### Scenario: epoch reset 不重建 roster

- **WHEN** 局部 identity epoch reset 发生
- **THEN** registry SHALL 保持现有 roster
- **AND** 该事件 SHALL NOT 触发 roster 销毁或重建

## ADDED Requirements

### Requirement: uncertainty-aware association gate

`GlobalPlayerAssociator` SHALL 以 uncertainty-aware gate 替代固定单值几何门：`gate_ft = min(max_reacquire_gate_ft, base_gate_ft + uncertainty_scale × prediction_uncertainty_ft)`。不同关联状态 SHALL 使用不同门宽：稳定连续匹配用 `base_gate_ft`（约 3ft）；历史 local 重连 / 跨 epoch reacquire 允许随 Kalman uncertainty 扩展至上限 `max_reacquire_gate_ft`；尝试把已有 global 换成另一个 global 时 SHALL 使用更严格门。具体参数 SHALL 用真实双摄 trace 的 residual 分布标定，MUST NOT 未经数据预拍为唯一标准。

#### Scenario: 稳定匹配用紧门

- **WHEN** 观测与预测位置接近且状态稳定
- **THEN** 关联门 SHALL 接近 `base_gate_ft`
- **AND** 明显异常候选 SHALL 被拒绝

#### Scenario: 重连允许适度放宽

- **WHEN** 历史 local player 重连或跨 epoch reacquire 且 Kalman uncertainty 较大
- **THEN** 关联门 SHALL 随 uncertainty 扩展至 `min(max_reacquire_gate_ft, base + scale×uncertainty)`
- **AND** 仍受 `max_reacquire_gate_ft` 上限约束

#### Scenario: 换人尝试用更严门

- **WHEN** 某个 candidate 试图取代已绑定 global 的另一 global
- **THEN** 系统 SHALL 使用比普通关联更严格的门与 `PendingReassociation` 迟滞
- **AND** 单帧更近 SHALL NOT 触发替换

### Requirement: stale roster 玩家不参与普通关联

当 roster 内玩家 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，其预测 SHALL 退出普通紧门匹配（不作为普通候选吸附观测），仅允许通过 historical local continuity、guided recovery、strong reacquire 路径回归。

#### Scenario: stale 预测不吸附

- **WHEN** Global P3 失踪超阈值
- **THEN** P3 的预测 SHALL NOT 参与普通观测关联
- **AND** 其他玩家的观测 SHALL NOT 因 P3 的 stale 预测被误吸附

#### Scenario: 强恢复路径仍可用

- **WHEN** 目标观测带有明确 historical / guidance / reacquire 证据指向 P3
- **THEN** 系统 SHALL 仍允许经该强路径将观测回归 P3
- **AND** 恢复成功后 P3 SHALL 重新获得普通关联资格

### Requirement: guided expected-global 强约束（guided 观测专用，base 优先）

对 `confirmed AND cross_view_anchored` 的 global player，当 guidance 明确携带 `expected_global_player_id=G3` 且 guided candidate（`detection_origin=guided_roi`）通过 target-view pre-gate（真实像素证据）时，`GlobalPlayerAssociator` SHALL 优先将该 candidate 恢复为 G3：仅当 G3 几何不可行或 pre-gate 拒绝时才 reject / unresolved，SHALL NOT 因排序代价略低将其转投其他 global（如 G2）。该强约束 SHALL 仅约束 `detection_origin=guided_roi` 的观测；同 tick 的 base formal observation 正常走普通关联，stale guidance SHALL NOT 覆盖 base evidence。

#### Scenario: guidance 命中恢复原 global

- **WHEN** Cam2 提供 donor guidance 期望 G3，Cam1 在 ROI 内通过 pre-gate 重新检测到该球员
- **THEN** 系统 SHALL 将 Cam1 该观测绑定回 G3
- **AND** SHALL NOT 将其关联为 G2

#### Scenario: guidance 不可行则拒绝

- **WHEN** guided candidate 与 G3 的几何距离超过该状态门限或 pre-gate 拒绝
- **THEN** 系统 SHALL 记录 reject / unresolved
- **AND** SHALL NOT 转投其他 global

#### Scenario: base 证据优先于 guidance

- **WHEN** 同 tick 既有 base formal observation 可靠看到该球员，又有 stale guidance 指向其他 global
- **THEN** base observation SHALL 走普通关联
- **AND** guided 强约束 SHALL 不覆盖 base evidence
