# multiview-global-player-roster Specification

## Purpose

定义全局比赛球员名单（Global Roster）：一场比赛固定人数（单打 2 / 双打 4）的 global player 集合，由 candidate pool 经"晋升→确认"两级流程建立，进入 ROSTER_ACTIVE 后不再创建新 global；覆盖 candidate 自身归属规则、生命周期状态机、roster 重建边界、confirmed roster 不 GC、统计语义、F1 冻结与 `global-player-roster.v1` 产物及 Global→canonical Player 映射。

## Requirements

## ADDED Requirements

### Requirement: Registry 知晓本场比赛人数

`GlobalPlayerRegistry` SHALL 在创建时接收 `expected_player_count`（来自 `match_context`：singles=2、doubles=4）。registry SHALL 只允许 roster 内的 global player 占用正式身份；roster 满后 `allocate_roster_slot()` SHALL 返回 None。

#### Scenario: 双打固定 4 人

- **WHEN** `match_format=doubles` 创建 registry
- **THEN** `expected_player_count` SHALL 为 4
- **AND** `allocate_roster_slot()` 在已分配 4 个后 SHALL 返回 None

#### Scenario: 单打固定 2 人

- **WHEN** `match_format=singles` 创建 registry
- **THEN** `expected_player_count` SHALL 为 2
- **AND** roster 满后普通 unmatched 观测 SHALL NOT 获得新 global id

### Requirement: GlobalRosterCandidate 候选池与自身归属规则

系统 SHALL 提供 `GlobalRosterCandidate` 候选池：unmatched formal observation 在未达到晋升条件前 SHALL 进入候选池，候选 id 前缀 SHALL 为 `candidate_`，MUST NOT 使用 `global_player_N`。candidate SHALL 记录 first/last tick、hit_count、dual_view_hit_count、canonical 位置与 local bindings。**下一 tick 的 unmatched observation 归属 candidate 的判定 SHALL 按以下优先级**：①同 `(view_id, view_player_id, local_identity_epoch)` 复用同 candidate（强 key）；②跨 epoch 的 `(view_id, view_player_id)` 仅作弱 prior（复用同 candidate 但证据权重低）；③否则按 canonical geometry（落在 candidate 预测位置邻域内）；④全部不满足才新建 candidate。同 tick 一个 candidate 每个 view SHALL 至多接受一个 observation，同一 view 的两个不同 formal local players SHALL NOT 合并为同一 candidate（继承 `tentative bootstrap view uniqueness` 语义）。

#### Scenario: 瞬时观测不立即成为 global

- **WHEN** 某 tick 出现一个未匹配的 formal observation
- **THEN** 系统 SHALL 创建 `candidate_N` 而非 `global_player_N`
- **AND** 该 candidate SHALL 不占用 roster slot、不参与 `predict_all()` 作为关联预测源

#### Scenario: 同 local 身份累积到同一候选

- **WHEN** 后续 tick 出现与既有 candidate 同 `(view_id, view_player_id, epoch)` 的观测
- **THEN** 系统 SHALL 复用该 candidate 累积证据
- **AND** SHALL NOT 新建重复候选

#### Scenario: epoch 变化仅弱 prior 复用

- **WHEN** 观测的 `local_identity_epoch` 相对既有 candidate 已变化，但 `(view_id, view_player_id)` 相同
- **THEN** 系统 SHALL 以弱 prior 尝试复用同 candidate（证据权重低）
- **AND** 若 canonical geometry 也不支持，SHALL 新建候选而非强行合并

#### Scenario: 同 view 双人不合并

- **WHEN** 同一 view 的两个 formal local players 的 canonical 距离小于候选门限
- **THEN** 系统 SHALL 为其保留不同 candidate
- **AND** 同一 tick 同 candidate 每 view 至多接受一个 observation

#### Scenario: 晋升占用 roster slot

- **WHEN** candidate 连续稳定证据达标（双视角一致 ≥2 有效 tick，或单视角 formal identity 稳定 ≥5 tick；参数可调）
- **THEN** 系统 SHALL 将其晋升为 provisional roster occupant（占用空闲 slot）
- **AND** 晋升后其观测才参与融合与指标

#### Scenario: 候选过期

- **WHEN** candidate 未达晋升条件且长时间无新证据
- **THEN** 系统 SHALL 将其标记 expired 并清理
- **AND** 清理 SHALL NOT 影响既有 roster

### Requirement: 三级生命周期与 roster 确认（slot 占满 ≠ roster 可信）

系统 SHALL 以三级生命周期推进：`candidate → provisional roster occupant → roster confirmed`。`ROSTER_ACTIVE` 仅在 **全部 slot 均有 occupant 且每个 occupant 额外稳定 K 个 canonical tick（默认配置）或至少发生过一次可靠 cross-view anchoring** 后进入；仅"slot 占满"SHALL NOT 使 roster 可信。进入后系统 SHALL 从"发现谁在场上"切换为"维护这 N 个已知球员"：后续 unmatched observation SHALL 进入 unresolved / recovery / reject 路径，SHALL NOT 创建新 global。

#### Scenario: 占满但未确认不激活

- **WHEN** 4 个 slot 均有 provisional occupant，但各 occupant 未满足稳定 K tick 且无 cross-view anchoring
- **THEN** registry SHALL 仍处于 `BOOTSTRAPPING`
- **AND** 错误 occupant SHALL 仍可被弱绑定 / geometry 证据推翻

#### Scenario: 确认后进入维护模式

- **WHEN** 全部 slot 占用且每 occupant 稳定 K tick 或至少一次可靠 cross-view anchoring
- **THEN** registry SHALL 进入 `ROSTER_ACTIVE`
- **AND** 此后 unmatched 观测 SHALL NOT 创建新 global

#### Scenario: roster 关闭后禁止新建

- **WHEN** registry 处于 `ROSTER_ACTIVE` 且出现无法匹配到 P1-P4 的观测
- **THEN** 系统 SHALL 将其记为 unresolved / recovery candidate / noise
- **AND** SHALL NOT 创建 `global_player_5` 及以上

### Requirement: roster 重建边界（与 identity_reset 严格分离）

只有 `new_match`、显式 `roster_reset`、明确确认的 participant-change / substitution 事件才允许销毁并重建 roster。**普通 local identity epoch reset、局/盘切换、换边 SHALL NOT 触发 roster 重建**；局部 epoch reset 只影响该 view 的强绑定（见 multiview-player-association 的两级 continuity），roster 内玩家身份保持。

#### Scenario: 换场/换人才重建

- **WHEN** 系统检测到明确的 new_match / roster_reset / participant-change 事件
- **THEN** 现有 roster SHALL 被销毁并进入新的 BOOTSTRAPPING
- **AND** 其余任何情况 SHALL 保持 roster 不变

#### Scenario: epoch reset 不重建 roster

- **WHEN** 某 view 的 local player 发生 identity epoch reset（遮挡 / track loss 触发）
- **THEN** registry SHALL 保持现有 roster
- **AND** 该 local 身份 SHALL 经弱历史绑定 + 证据重新回原 global，而非触发 roster 重建

### Requirement: confirmed roster 不参与普通 GC，但存在与关联资格分离

candidate 与从未 confirmed 的 tentative SHALL 可过期淘汰；已进入 roster 的 confirmed global 出画 SHALL 只降级 weak → lost 并等待 recovery，SHALL NOT 被删除。仅 roster reset 才销毁。同时，`GlobalPlayerState` 的"存在于 registry"与"有资格参与普通 association"SHALL 分离：当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家 SHALL 退出普通紧门匹配，仅允许经 historical local continuity / guided recovery / strong reacquire 路径回归。

#### Scenario: P3 出画不删

- **WHEN** roster 内 Global P3 长时间不可见
- **THEN** GlobalPlayerState P3 SHALL 继续存在（lifecycle=lost）
- **AND** P3 重新出现时 SHALL 恢复为原 global，而非创建新 global

#### Scenario: stale 玩家不参与普通匹配

- **WHEN** Global P3 失踪超过阈值（uncertainty / last_seen_age 超限）
- **THEN** P3 SHALL 退出普通紧门匹配，不吸附其他玩家观测
- **AND** 仅经 historical continuity / guided recovery / strong reacquire 路径回归

### Requirement: 球员计数语义

系统 SHALL 区分 `expected_player_count`（赛制人数）、`roster_occupied_count`（已占 slot 数）、`confirmed_player_count`（已确认 roster 玩家数）与 `observed_player_count`（实际有观测的玩家数）。报告 / 产物 SHALL 按明确语义选用，MUST NOT 为避免"47 条"而硬写为 `expected_player_count`。

#### Scenario: 遮挡致只确认 3 人

- **WHEN** 双打任务因遮挡最终只确认 3 名 roster 玩家
- **THEN** 摘要 SHALL 如实报告已确认/已观测人数（如 3）
- **AND** 不得为凑数报告"检测到 4 条球员轨迹"

### Requirement: global-player-roster.v1 产物、display anchor 与公开映射

joint compose SHALL 产出 `global-player-roster.v1` 产物（诊断 / 映射 contract，非用户展示 identity），包含 `schema_version`、`expected_player_count`、`roster_occupied_count`、`confirmed_player_count`、`status`（`bootstrap` / `confirmed`）与每个 roster 玩家的 `global_player_id` / canonical `player_id` / `label` / 各 view binding。公开轨迹身份、overlay、report 与 `/visualization-data` SHALL 一律使用 canonical `Player_N / Pn`，用户可见产物 MUST NOT 出现 `global_player_`；roster.v1 与内部 diagnostics 可保留 internal global id。

**Global → canonical `Player_N` 映射规则（display anchor）**：以 reference view 的 formal local identity 为 canonical display anchor——某 global 稳定绑定 reference view 的 `Player_N` 则公开身份为该 `Player_N`；global 暂时只有 non-reference view evidence 时 canonical player id SHALL 暂缓分配，待 reference binding 出现后确定；整场 reference 缺失时使用明确的 deterministic fallback（如 slot 顺序）并在产物中标注。

#### Scenario: 公开链路只出现 P1-P4

- **WHEN** joint 分析完成且 roster confirmed
- **THEN** roster.v1 SHALL 提供 `global_player_id ↔ Player_N ↔ Pn` 完整映射
- **AND** 用户可见轨迹 / 热力图 / report SHALL 仅含 `Player_1..4 / P1..P4`
- **AND** 用户可见产物 SHALL NOT 包含 `global_player_` 字符串

#### Scenario: 诊断产物保留 internal id

- **WHEN** 检查 `global-player-roster.v1` 或内部 diagnostics
- **THEN** 其中 SHALL 可包含 internal `global_player_N`
- **AND** 该产物 SHALL 标记为诊断 / 映射 contract，不进入用户展示链路

#### Scenario: reference view 决定显示身份

- **WHEN** 某 global 稳定绑定 `cam_1 / Player_3`（reference view）
- **THEN** 其公开身份 SHALL 为 `Player_3`
- **AND** 不同重跑中同一物理球员的公开身份 SHALL 保持一致（由 reference binding 而非 slot 顺序决定）

#### Scenario: 缺 reference binding 暂缓分配

- **WHEN** 某 global 仅有 cam_2 evidence、reference view 未绑定
- **THEN** 其 canonical player id SHALL 暂缓分配（不写入公开轨迹）
- **AND** reference binding 出现后 SHALL 以该 binding 确定公开身份

### Requirement: F1 offline refinement 冻结 roster 映射

F1 offline refinement SHALL NOT 改变 roster 身份映射：不得修改 `global → Player_N` 的对应关系，SHALL NOT 在 F1 阶段分配新 roster slot。roster snapshot SHALL 与 F0 snapshot 一起冻结，F1 仅可补充 observation、改善 fused position。

#### Scenario: F1 不改身份

- **WHEN** F1 运行于已确认 roster 之上
- **THEN** F1 输出 SHALL 保持 F0 的 global→canonical 映射
- **AND** SHALL NOT 新增或重分配 roster slot
