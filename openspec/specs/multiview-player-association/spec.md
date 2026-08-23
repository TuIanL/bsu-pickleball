# multiview-player-association Specification

## Purpose
`GlobalPlayerAssociator`（joint_tracking_v2 专用）把双视角 local observations 分配到 roster global states：canonical 空间最大基数可行匹配、uncertainty-aware 几何门、两级 identity continuity（强绑定 + 弱历史绑定）、PendingReassociation 迟滞；灾难场景下 trusted historical-identity reanchor 决策（associator 只决策、JointRun 唯一执行 reseed）。
## Requirements
### Requirement: View Identity 与 Global Identity 分离

系统 MUST 区分 View Identity（`(view_id, view_player_id)`）与 Global Identity（`global_player_id`）。`cam_1 / Player_1` 与 `cam_2 / Player_1` MUST NOT 被默认视为同一真人；两者 MUST 通过显式的跨视角关联建立映射关系。

#### Scenario: 标签不直接等价

- **WHEN** 两路分别产生 `cam_1 / Player_1` 与 `cam_2 / Player_1`
- **THEN** 系统 SHALL 不将二者视为同一 global player
- **AND** 系统 SHALL 仅在关联判定成立后才赋予同一 `global_player_id`

#### Scenario: 关联映射

- **WHEN** 跨视角关联判定两个 view 观测属于同一真实球员
- **THEN** 系统 SHALL 将二者映射到同一 `global_player_id`
- **AND** 该映射 SHALL 可被后续 Fusion 层消费

### Requirement: 跨视角关联不使用 side 字段

跨视角身份关联 MUST NOT 使用现有单视角 artifact 的 `side` 字段作为身份依据。关联 SHOULD 使用 canonical court distance、global prediction（来自 `GlobalTrackFilter.predict`）、temporal continuity、previous association 与 physical court constraints。

#### Scenario: 禁用 side

- **WHEN** `CrossViewPlayerAssociator` 计算关联代价
- **THEN** 关联代价 SHALL 不包含 `side` 字段输入
- **AND** 该约束 SHALL 由自动化测试断言

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

### Requirement: 关联在 canonical 空间执行

跨视角关联 MUST 在 Canonical Physical Court Frame 空间执行，其代价基于 canonical 坐标距离与运动预测残差，而非 local 坐标。

关联代价 MUST 分离为两个层面：

- **几何可行性门**：`cross_view_distance <= max_feasibility_cost`。该门 MUST 仅使用 canonical 坐标距离，MUST NOT 包含预测项。
- **排序代价**：在几何可行的候选之间，使用 `cross_view_distance + prediction_bias * secondary_to_global_prediction_residual` 计算，MUST 先最大化可行匹配数量，再在相同数量下取排序代价最小。

prediction 项 MUST 为 **per-candidate**（使用 secondary observation 到该 global 预测位置的残差），MUST NOT 为同一 reference player 的常数，MUST NOT 影响几何可行性判定。

#### Scenario: canonical 距离代价

- **WHEN** 关联需要比较两路观测位置
- **THEN** 系统 SHALL 先归一化到 canonical 坐标
- **AND** 几何可行性门 SHALL 使用 canonical 坐标距离与 `max_feasibility_cost` 比较

#### Scenario: per-candidate prediction 排序

- **WHEN** 某 reference player 已关联到某 global player、该 global 存在预测位置，且存在多个 secondary candidate
- **THEN** 系统 SHALL 为每个 candidate 加入 `prediction_bias * distance(secondary_candidate, predicted_position)`（per-candidate）
- **AND** 该预测项 SHALL 影响候选之间的排序

#### Scenario: 几何可行性独立于预测

- **WHEN** 某 pair 的 `cross_view_distance <= max_feasibility_cost`，但预测残差较大
- **THEN** 该 pair SHALL 仍视为几何可行并可参与排序
- **AND** 系统 SHALL NOT 因预测项将几何合法的配对被整体剔除

### Requirement: 最大基数可行匹配（maximum-cardinality feasible matching）

跨视角二分图匹配 MUST 在可行匹配中优先最大化匹配数量（maximum-cardinality），再在相同数量下选择 ranking cost 最小的方案。匹配 MUST 支持 `reference_keys` 与 `secondary_keys` 数量不等的矩形输入（如 `2 ref / 1 sec`、`4 ref / 3 sec`、`1 ref / 2 sec`），MUST NOT 因索引方向错误抛出 `KeyError`。部分可行时 MUST 返回最大可行匹配（能配 1 对不返回 `[]`），未匹配元素 MUST 保持单视角。任一侧为空时 MUST 返回空列表。

#### Scenario: reference 多于 secondary

- **WHEN** 传入 `2 reference` 与 `1 secondary`（或 `4 ref / 3 sec`）
- **THEN** 系统 SHALL 正常运行，不抛出 `KeyError`
- **AND** 系统 SHALL 返回不超过 secondary 数量的匹配对
- **AND** 未匹配的 reference 元素 SHALL 保持单视角

#### Scenario: secondary 多于 reference

- **WHEN** 传入 `1 reference` 与 `2 secondary`
- **THEN** 系统 SHALL 正常运行，不抛出 `KeyError`
- **AND** 系统 SHALL 返回不超过 reference 数量的匹配对
- **AND** 未匹配的 secondary 元素 SHALL 保持单视角

#### Scenario: 部分可行（partial feasible）

- **WHEN** `2 reference` 与 `2 secondary` 中仅 `1` 对几何可行，其余对超过 `max_feasibility_cost`
- **THEN** 系统 SHALL 返回该 `1` 对可行匹配
- **AND** 系统 SHALL NOT 返回 `[]`（不得因其余对不可行而丢弃可行对）

#### Scenario: 空集合

- **WHEN** `reference_keys` 或 `secondary_keys` 为空
- **THEN** 系统 SHALL 返回空列表且不抛出异常

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

### Requirement: 单视角缺失不阻塞

当某 global player 在一路视角不可见时,另一路观测 SHALL 仍能分配到其 global state;缺失视角 SHALL 视为该 view binding 过期,而非阻止关联。

#### Scenario: 单视角缺失

- **WHEN** cam_1 的 P3 不可见、cam_2 可见
- **THEN** P3 的 cam_2 观测 SHALL 分配到其 global state
- **AND** cam_1 缺失 SHALL 视为该 view binding 过期,而非阻止关联

### Requirement: 关联不使 prediction 影响几何可行性

跨视角关联 SHALL 分离几何可行性门与排序代价:几何可行性仅由 canonical 距离判定,per-candidate prediction 残差只在可行候选之间排序(保留 Change 0 修复)。

#### Scenario: 几何门独立

- **WHEN** 某 pair 几何可行但预测残差较大
- **THEN** 该 pair SHALL 仍可参与排序
- **AND** SHALL NOT 因预测项被整体剔除

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

### Requirement: reference view binding 槽位唯一性

`GlobalPlayerAssociator` 对 reference view 的 `(view_id, view_player_id)` 映射 SHALL 保持唯一：同一 view 内同一个 `Player_N` 槽位 SHALL 至多绑定一个 global player。新 global 尝试占用已被其他 global 占用的槽位时，SHALL 走 reassociation（`PendingReassociation`，连续强证据帧数达到 `reassociation_frames` 才切换），MUST NOT 直接覆盖既有 mapping。

#### Scenario: 两个 global 抢同一 reference 槽位不覆盖

- **WHEN** gid_1 已绑定 cam_1 的 Player_1，gid_3 的观测试图关联到 cam_1 的 Player_1
- **THEN** 系统 SHALL 将该候选标记为 reassoc pending（记录 challenger 连续强证据帧数）
- **AND** 在 `reassociation_frames` 帧强证据前，mapping SHALL 保持 gid_1 → Player_1
- **AND** SHALL NOT 立即把 Player_1 重新绑定到 gid_3

#### Scenario: 强证据达标后切换

- **WHEN** challenger（gid_3）对 cam_1 Player_1 连续强证据 ≥ `reassociation_frames`
- **THEN** mapping SHALL 切换到 gid_3 → Player_1
- **AND** 原绑定（gid_1）SHALL 进入 reacquire 候选池（historical_reacquired 语义）

### Requirement: 槽位冲突可观测

系统 SHALL 记录 reference view 槽位冲突事件（如 `event: "reference_slot_conflict"` + `view_id` + `view_player_id` + `incumbent_global` + `challenger_global` + `epoch`），供身份冲突归因（display diagnostics 的 `roster_conflict` 字段数据来源）。该观测 SHALL 只读，MUST NOT 改变 association 算法与门限。

#### Scenario: 冲突事件记录

- **WHEN** 第二个 global 尝试占用已绑定的 reference 槽位
- **THEN** 系统 SHALL 记录 `reference_slot_conflict` 事件（含双方 gid 与槽位）
- **AND** 该事件 SHALL 可在 job 观测产物中检索

#### Scenario: 观测不改变关联结果

- **WHEN** 发生槽位冲突且触发 reassoc pending
- **THEN** 冲突事件 SHALL 仅记录观测信息
- **AND** 关联算法、门限、晋升逻辑 SHALL 与实施前一致

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

### Requirement: tentative bootstrap view uniqueness

同一个 tentative global 在同一 tick SHALL 至多接受每个 view 一份 observation；bootstrap grouping SHALL 不把同一 camera 的两个不同 formal local players 合并为同一 global。

#### Scenario: 同 view 近距离双人
- **WHEN** Cam1 的两个 formal local players 的 canonical 距离小于 bootstrap gate
- **THEN** 系统 SHALL 为其保留不同 tentative global candidates

### Requirement: pre-association 一对一匹配 + ambiguity rejection（只读）

系统 SHALL 提供只读 pre-association 候选归属先验，SHALL 采用每 view 一对一匹配（min-cost）+ gate + ambiguity rejection：`residual ≤ pre_association_gate_ft` 且 second-best margin 足够（> `ambiguity_margin`）→ strong candidate；否则 `ambiguous`。`PreAssociationCandidate` SHALL 含 `matched_global_id / residual_ft / match_status / ambiguity_margin / projection_status / intrinsic_quality / origin`。pre-association SHALL 只读 `GlobalState(t-1)` 预测（与 guidance 同源），MUST NOT 产生 AssociationUpdate、MUST NOT 写 mapping。`GlobalPlayerAssociator.process_tick` 的算法、门限、候选晋升逻辑 SHALL 保持不变。

#### Scenario: 一对一匹配 + ambiguity rejection

- **WHEN** 某 candidate 与两个 global 预测的 residual 均 ≤ gate 且 margin 不足
- **THEN** 该 candidate SHALL 标记 `ambiguous`
- **AND** SHALL NOT 作为 same-tick donor（防双打 NVZ 密集时 P1/P2 互换）

#### Scenario: 归属先验不写 mapping

- **WHEN** pre-association 判定某 raw candidate 大概率属于 P1
- **THEN** 该判定 SHALL 只作为 same-tick ROI 决策的输入
- **AND** SHALL NOT 修改 mapping / 产生 AssociationUpdate / 影响 process_tick 内部状态

#### Scenario: 正式关联仍走 process_tick

- **WHEN** same-tick 补检形成新的 formal observation
- **THEN** 该 observation SHALL 由现有 `GlobalPlayerAssociator.process_tick` 正式关联
- **AND** 关联算法与门限 SHALL 与实施前一致

### Requirement: 可信历史 identity reanchor（决策与执行分离）

当普通匹配、continuity、weak historical binding 均因 geometry hard gate 拒绝（如被污染的 prediction 距恢复观测过远），且同时满足以下**全部**条件时，associator MUST 产生 reanchor 关联决策（`AssociationUpdate(..., reanchor=True)`）：

1. 观测 `(view_id, view_player_id)` 存在弱历史绑定（`historical_bindings`）指向原 global G；
2. G 当前处于 risk 状态（`last_state_risk_tick` 在 `reanchor_risk_window_ticks` 内，reason ∈ {innovation_rejected, conflict_no_measurement}，见 `multiview-global-player-state`）；
3. local identity 当前稳定（同 `view_player_id` 连续出现，无 epoch 抖动）；
4. 观测连续 N 帧（N=3，可配置）在自身运动连续邻域内（帧间位移 < 阈值，默认 3ft）；
5. 无歧义竞争：该观测对 G 的 residual 显著小于对次优 global 的 residual（margin），或次优 global 不在候选/已被绑定其它观测。

**associator 产生 reanchor 决策时 MUST NOT 直接调用 `absorb_measurement`/`reseed` 更新 GlobalState**（state update owner 唯一：由 `MultiViewJointRun` 在 fusion 后执行）。JointRun 对 reanchor update MUST 执行 `registry.reseed(...)`（position=观测位置、velocity=0、covariance=初始值、timestamp=当前），而非普通 `absorb_measurement`。

reanchor MUST NOT 通过整体放宽 `max_reacquire_gate_ft` 实现（普通/continuity/historical 三条路径的 gate 语义保持不变）；reanchor 决策 MUST 记录 `reanchor_pending / reanchor_succeeded / reanchor_rejected_ambiguous` 诊断事件与归因明细。

#### Scenario: 污染后正确观测恢复原 global

- **WHEN** `cam_1/Player_2` 曾稳定绑定 `global_player_4`；G 预测被污染偏离 14ft 且处于 risk 状态；恢复后观测连续 3 帧在 [19,-4] 邻域；无其他 global 与之竞争
- **THEN** associator SHALL 产生 `reanchor=True` 决策
- **AND** JointRun SHALL 以观测位置 reseed 其 estimator（velocity=0），清除污染位置与速度
- **AND** SHALL 记录 `reanchor_succeeded`

#### Scenario: 歧义时不 reanchor

- **WHEN** 恢复观测对两个 global 的 residual 都接近（如双打中相邻 P1/P2 站位模糊）
- **THEN** 系统 SHALL NOT 产生 reanchor 决策
- **AND** SHALL 记录 `reanchor_rejected_ambiguous`
- **AND** SHALL 按现有 unresolved 路径处理（roster 满时不新建）

#### Scenario: 无风险标记不 reanchor

- **WHEN** global 不在 risk 状态（无 innovation rejection / conflict 未选中记录，或已清除）
- **THEN** 系统 SHALL NOT 进入 reanchor 路径
- **AND** 仅按普通 association gate 评估

### Requirement: reanchor 不破坏既有 gate 语义

reanchor 路径 MUST 独立于 `_pair_gate_ft` 的普通匹配/continuity/historical 分支实现，MUST NOT 改变以下既有行为：稳定连续匹配用 `base_gate_ft` 紧门；历史 local 重连 / 跨 epoch reacquire 随 uncertainty 扩展至 `max_reacquire_gate_ft`；换人尝试用更严格门与 `PendingReassociation` 迟滞。`multiview-player-association` 既有 requirement（geometry-gated identity continuity prior / uncertainty-aware association gate）的语义 SHALL 保持不变。

#### Scenario: 普通 reacquire 语义不变

- **WHEN** 未被污染的 global 因短暂缺观测后恢复
- **THEN** 系统 SHALL 仍按 `uncertainty-aware association gate` 评估（gate 随 uncertainty 扩展）
- **AND** SHALL NOT 因 reanchor 路径存在而改变该评估

### Requirement: Local slot 与 global 的全视图双射
`GlobalPlayerAssociator` SHALL 保证同一 tick 内每个 `(view_id, view_player_id, epoch)` 至多绑定一个 global，且每个 global 在同一 view 至多接受一个 local slot。duplicate、cross-side 或 ambiguity margin 不足的 challenger SHALL NOT 覆盖 incumbent。

#### Scenario: P2 尺度投影候选落在 P1 bbox
- **WHEN** P2 projected candidate 的 target bbox memory owner 为 P1 或其 local slot 已绑定另一 global
- **THEN** association SHALL 拒绝该候选或保持为 unresolved display evidence
- **AND** SHALL NOT 将 P2 global 绑定到 P1 local slot

### Requirement: 投影 provenance 不授予身份
`cross_view_projected` evidence SHALL 只用于展示/恢复候选排序，不得单独创建 local identity、global binding 或 canonical trajectory sample。其 provenance MUST 含 donor global、target slot、geometry residual、bbox memory owner 与 age。

#### Scenario: donor P2 有效但 target 无 detection
- **WHEN** donor view 确认 P2 而 target view 无真实/ROI detection
- **THEN** target view MAY 展示 P2 projected footpoint
- **AND** MUST NOT 因该投影修改 P1/P2 的 association mapping

### Requirement: 跨摄 appearance 只使用已校正软先验
Global association MAY 在 geometry/side/slot hard gate 后使用跨摄 appearance 排序，但 MUST 要求 donor/target descriptor 合格且 camera color profile confidence 达标。未经校正、non-discriminative 或低质量 appearance SHALL 权重归零；projected bbox 不得生成 descriptor。

#### Scenario: 跨摄颜色相似但 profile 不可靠
- **WHEN** cam_1/cam_2 的 candidate 颜色相似但 camera profile confidence 不达标
- **THEN** association SHALL 忽略跨摄 appearance cost
- **AND** SHALL 按 geometry、prediction、continuity 与一对一约束裁决
