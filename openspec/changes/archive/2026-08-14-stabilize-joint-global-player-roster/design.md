# stabilize-joint-global-player-roster — Design

## Context

双摄 `joint_tracking_v2` 真实任务（job-f473d041a6，executionMode=joint_tracking_v2，cam_1 identity / cam_2 rotate_180）产出 47 个 `global_player_N`：fused 样本 7858 个、47 个不同 global id，报告摘要"检测到 47 条球员轨迹"。场上只有 4 名球员。

代码核验结论（2026-08-14）：
- **本地身份层已正确**：`multiview_joint_executor.py` 已设 `eligibility_policy="lock_only"`；`_result_to_observations` 只放行带 `player_id` 的 formal detection（`view_player_id` / `local_identity_epoch` / `track_id` 一并送入）；`age_bindings` 每 tick 调用；guidance 双向生成、各 view 用独立 orientation / inverse homography。
- **病根集中在 Global 层**：`GlobalPlayerAssociator.process_tick`（association_global.py）对 unmatched 观测无条件 `registry.new_global_id()`；`GlobalPlayerRegistry`（global_state.py）`players` 只增不减、`new_global_id()` 无上限、`predict_all()` 返回所有有 Kalman 状态的 global（含 stale）；continuity key `(view_id, view_player_id, epoch)` 在 epoch reset 时被强制清除；关联门固定 `3.0 ft`；guidance 的 `expected_global_player_id` 仅作 `0.5` cost penalty。
- **产物层缺口**：`compose_joint_result` 把 `global_player_id` 直接作为 `ProjectedTrackPoint.track_id`，且不产出 `structured/data.json`（前端 `/visualization-data` 404 → 降级旧 PNG 热力图，出现"global_player_47 球员位置热力图"）。

本 design 在首次提案后经评审收紧（2026-08-14）：补充 candidate 自身关联规则、roster 两级确认、identity_reset 与 roster_reset 语义拆分、stale prediction 的 association eligibility、reassociation 强证据定义、guided 的 base 优先级、canonical display anchor、F1 冻结 roster 映射。

## Goals / Non-Goals

**Goals:**
- 把 Global 层从"不断发现新 global track"升级为"先建立本场比赛固定 roster（单打 2 / 双打 4），之后只维护这 N 个已知球员"。
- 消除 `global_player_47` 类产物：roster 建立后 unmatched 观测只能 unresolved / recovery / reject，禁止创建 G5。
- 修复关联质量：uncertainty-aware gate、两级 continuity（epoch reset 后能重回原 global）、PendingReassociation 多帧强证据迟滞、guided recovery 强身份约束（且 base 证据优先）。
- 公开链路契约对齐单摄：`Player_1..4 / P1..P4`（由 reference view binding 决定 canonical anchor）；joint 路径生成与单摄同契约的 `structured/data.json`。
- F1 offline refinement 不得改变 roster 身份映射。

**Non-Goals:**
- 不重做本地 P1-P4 锁定（`PlayerLockManager` / `ViewTrackingSession` 已正确，仅保持现状）。
- 不修改 P0 `CrossViewPlayerAssociator`（association.py，reference-centric，late_fusion_v1 专用）。
- 不动前端组件（structured-heatmap 契约已支持 `Player_1..4`；joint 生成同契约数据后前端自动切换）。
- 不引入 appearance / ReID 模型（第一版纯几何 + 时序 + 身份连续性）。
- 不在本 change 调优最终参数（2/5 tick、gate 的 base/max、switch_margin、K tick 确认窗口）——参数由真实 trace 标定，本 change 只搭结构与默认值。

## Decisions

### D1: Registry 首次知晓比赛人数，`new_global_id()` 收归内部

`GlobalPlayerRegistry(expected_player_count=N)`；公开分配接口改为 `allocate_roster_slot() -> str | None`（满后 None）。`new_global_id()` 保留为内部私有路径，仅在 roster reset / 重建时使用，普通 unmatched 观测不可达。

- **Rationale**：`expected_player_count` 在 executor 已可拿到（`build_match_context`），现在创建 registry 时被丢弃。固定人数是匹克球固定场地场景的核心业务先验，"4 人硬上限"是最后一道安全网而非完整算法（须与 candidate pool + 两级确认配合，避免 bootstrap 错误被永久冻结）。
- **Alternatives**：仅 `if len(players) >= 4: 不再 new` —— 被否，会把 bootstrap 早期错误永久冻结。

### D2: GlobalRosterCandidate 候选池 + candidate 自身关联规则

unmatched formal observation → `candidate_N`（禁止 `global_player_N` 命名），记录 first/last tick、hit_count、dual_view_hit_count、canonical 位置、local bindings。**candidate 的归属判定必须锁死**，否则会出现几百个 `candidate_N`：

candidate matching 优先级（下一 tick 的 unmatched observation 判定属于 `candidate_3` 还是新建 `candidate_4`）：
1. 同 `(view_id, view_player_id, local_identity_epoch)` → 复用同 candidate（强 key）；
2. 跨 epoch 的 `(view_id, view_player_id)` → 仅作弱 prior（复用同 candidate 但证据权重低）；
3. 否则用 canonical geometry（`candidate_3` 预测位置邻域内）；
4. 全部不满足 → 新建 candidate。

约束：同 tick 一个 candidate 每个 view 至多接受一个 observation（继承现有 `tentative bootstrap view uniqueness` 语义——同一 view 的两个不同 formal local players 不得合并为同一 candidate）。

晋升规则（保守默认，参数可调）：
- 双视角连续一致 ≥2 有效 tick，或
- 单视角 formal local identity 稳定 ≥5 有效 tick。

晋升仅使 candidate 成为 **provisional roster occupant**（占 slot），不直接使 roster 可信（见 D3）。未晋升即过期。candidate 不参与 `predict_all()`（不成为关联预测源）。

- **Rationale**：瞬时投影异常 / 同步抖动最多产生 transient candidate 并过期，不会制造 `global_player_35`。candidate 归属规则保证证据能累积到正确的候选上，而不是扩散成大量孤儿 candidate。
- **Alternatives**：unmatched 直接 unresolved —— 会在 bootstrap 阶段因缺少候选积累而无法建立 roster，故 bootstrap 阶段需要候选池，ACTIVE 后候选池退居次要。

### D3: 三级生命周期：`candidate → roster occupant → roster confirmed`（两级确认）

**slot 占满 ≠ roster 可信**。状态机：

```text
BOOTSTRAPPING
   ├─ candidate_N（unmatched 观测的暂存）
   │    └─ 晋升（D2 规则）→ provisional roster occupant（占 slot）
   │         └─ 满足确认条件 → roster confirmed → ROSTER_ACTIVE
   └─ ROSTER_ACTIVE：只维护已知球员
```

`ROSTER_ACTIVE` 进入条件（两级确认，**不是"roster 满了"**）：
1. 所有 slot 均已有 occupant；**且**
2. 每个 occupant 额外稳定 K 个 canonical tick（默认配置，如 30 tick）**或** 至少发生过一次可靠 cross-view anchoring。

**roster 重建边界（与 identity_reset 严格分离）**：只有 `new_match`、显式 `roster_reset`、明确确认的 participant-change / substitution 事件才销毁并重建 roster。**普通 local identity epoch reset、局/盘切换、换边 SHALL NOT 触发 roster 重建**（与 D4 的弱历史绑定语义一致）。

- **Rationale**：前 0.5 秒投影误差晋升 4 个错误 candidate 时，"满 4 人就 ACTIVE"会把错误永久冻结；两级确认让错误 occupant 有机会在确认窗口内被推翻（弱历史绑定 + geometry）。
- **Alternatives**：单级"满即 ACTIVE" —— 被否，见上。

### D4: 两级 continuity（修改现有"epoch reset 不继承 prior"）

- 强绑定 `(view_id, Player_N, epoch) → global`：epoch reset 失效（保持现状）。
- 弱历史绑定 `(view_id, Player_N) → global`：epoch reset 后仍保留，作为先验；观测须重新通过 geometry / donor / prediction 证明回原 global；证据不足 → unresolved，不得自动继承、不得新建。

**语义拆分**：`PlayerIdentityManager` 的 identity epoch reset 是**局部跟踪生命周期事件**，只影响该 view 的强绑定，SHALL NOT 影响 global roster 的存在性（roster 重建仅由 D3 的边界事件触发）。Epoch reset 后的同 local 身份通过弱绑定 + 证据重新回到原 global（D4 场景），这正是"roster 不失忆"的实现。

- **Rationale**：场上固定四人 + 本地 epoch reset 多为遮挡/track loss。每次 reset 都彻底遗忘 global 身份必然制造 ID churn。弱绑定是"很可能是过去那个 P3，但必须重新证明"，比"完全陌生的人"准确得多。
- **Alternatives**：epoch reset 直接继承强绑定 —— 被否，遮挡后可能已换人，无脑继承会锁死错误。

### D5: uncertainty-aware association gate

`gate_ft = min(max_reacquire_gate_ft, base_gate_ft + uncertainty_scale × prediction_uncertainty_ft)`。状态分档：稳定连续匹配紧门（~3ft）；历史 local 重连 / 跨 epoch reacquire 随 Kalman uncertainty 扩展（上限 `max_reacquire_gate_ft`，结构示例 7-8ft）；尝试替换已有 global 用更严门。**参数不预拍**，用真实双摄 trace 的 residual 分布标定。

**与 D8 配合**：gate 扩宽只作用于"有资格参与普通关联"的 roster 玩家；stale 玩家（见 D8）不得利用扩宽门吸附普通观测。

- **Rationale**：固定 3ft 在剧烈运动（冲刺/跳跃）与同步/标定残差下必然失配。Kalman 已提供 `position_uncertainty_ft`，自然作为门宽依据。
- **Alternatives**：调成固定 6ft —— 被否，会引入错误关联（网前 1.5ft 间距场景换人风险上升）。

### D6: PendingReassociation 多帧迟滞 + "强证据"定义

`local_identity_switch_penalty`（0.25 cost penalty）升级为显式状态。**"一帧强证据"必须定义**，否则 challenger 每帧只比 incumbent 好 0.01 也能累计 5 帧错误换人。一帧计为"强证据"需同时满足：
1. challenger geometry 可行（在相应状态门限内）；
2. challenger cost 比 incumbent 好超过 `switch_margin`（默认配置，如 0.15，参数待标定）；
3. challenger 指向的 global 连续一致（同 global，非每帧不同 challenger）。

约束：连续达 `reassociation_frames`（默认 5）帧强证据才正式切换；challenger 每帧变化（global 不同或证据中断）则计数清零；切换记入 diagnostics。

- **Rationale**：cost penalty 是"软倾向"，不保证多帧连续性；网前 P1/P2 交叉跑位时单帧更近不足以换色，需要多帧强证据（P0 spec 本有此要求，实现未真正落地）。
- **Alternatives**：仅 `consecutive_hits=5` 计数 —— 被否，未定义证据强度，微弱优势也能累积换人。

### D7: Guided recovery 强身份约束（guided 观测专用，base 优先）

confirmed + cross_view_anchored + guidance 明确 `expected_global_player_id=G3` + guided candidate 通过 target-view pre-gate → 优先恢复 G3；G3 几何不可行 / pre-gate 拒绝 → reject / unresolved，不转投 G2。

**base observation 优先级规则**：上述强约束只作用于 `detection_origin=guided_roi` 的观测。同 tick 正常 full-frame/base 检测已可靠看到该球员时，base formal observation 正常走普通关联，stale guidance 不得覆盖 base evidence（与现有 recovery episode 的 `base_recovered` 语义一致：base 优先，guided 仅在 base 缺失时承担恢复）。

- **Rationale**：让 P1 跨视角 recovery 成为真正的"身份恢复链"而非"提供一个 ROI"。donor 明确告诉你找的是谁，target 在 ROI 里找到了真实像素证据，就不该因为 cost 差一点关联成别人；同时 base 检测是更强证据，不受 guidance 干扰。
- **Alternatives**：保持 0.5 penalty —— 被否，语义太弱；对 base 观测也强约束 —— 被否，stale guidance 会覆盖新 base 证据。

### D8: Confirmed roster 不删除，但 "存在" 与 "普通关联资格" 分离

candidate / 未 confirmed 的 tentative 可过期；roster 内 confirmed 出画只 weak → lost，等待 recovery，不删除；仅 roster reset 销毁（D3）。

**stale prediction 不得永远参与普通 association**：`GlobalPlayerState` 增加 association eligibility 判定——当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家**从普通紧门匹配中退出**，只允许通过以下路径回归：historical local continuity、guided recovery、strong reacquire（跨 epoch 弱绑定 + 扩宽门）。其余 roster 玩家与观测正常参与关联。

- **Rationale**：保留 lost G3 是对的，但 G3 失踪 40 秒后 Kalman prediction 仍存在，若继续以普通 candidate 身份抢观测会错误吸附。D5 扩宽 gate 与 D8 stale 退出必须配套，否则组合起来反而制造错误吸附。
- **Alternatives**：保留 lost 且始终参与普通匹配 —— 被否，长期 stale 预测会吸附别人观测；直接删除 lost —— 被否，回到"删 G3 → P3 回来 → G5"。

### D9: `global-player-roster.v1` 产物 + canonical display anchor + structured data

compose 产出 roster.v1（schema_version / expected_player_count / roster_occupied_count / confirmed_player_count / status / players[global_player_id ↔ Player_N ↔ Pn ↔ view bindings]）；`fused_to_projected_tracks` 以 roster 映射把 `global_player_id` 转 canonical `Player_N` 作为 `track_id`；joint 路径调用 `PositionVisualizationDataBuilder` 生成与单摄同契约的 `structured/data.json`（22×10 网格、P1-P4），替代仅旧 PNG heatmap。

**Global → canonical `Player_N` 映射规则（display anchor）**：以 reference view 的 formal local identity 作为 canonical display anchor——
1. 某 global 稳定绑定 `cam_1 / Player_3`（reference view）→ 公开身份即为 `Player_3`；
2. global 暂时只有 cam_2 evidence（reference 未绑定）→ canonical player id 暂缓分配，等 reference binding 出现后再确定；
3. 整场 reference 都缺失 → 使用明确的 deterministic fallback（如 slot 顺序），并在产物中标注。

**roster.v1 定位**：它是内部诊断 / 映射 contract，不是用户展示 identity。roster.v1 与内部 diagnostics 可保留 `global_player_N`；用户可见的 trajectory / metrics / structured visualization / report 中 SHALL NOT 出现 `global_player_`。

- **Rationale**：按 slot 晋升顺序编号会导致不同重跑同一物理球员映射到不同 Pn（今天近端左侧是 P1，明天同一场重跑变 P3）。reference view 的 local identity 做 anchor 与单摄 overlay / report 保持一致。
- **Alternatives**：按 slot 顺序编号 —— 被否，重跑不稳定；让前端显示 global id —— 被否，违背 player-identity-display spec。

### D10: F1 offline refinement 冻结 roster 映射

F1 可补充 observation、改善 fused position，但 SHALL NOT 改变 roster 身份映射（不得把 `G2 → Player_2` 改为 `G2 → Player_3`），SHALL NOT 在 F1 阶段分配新 roster slot。roster snapshot 与 F0 snapshot 一起冻结；F1 消费同一 roster 映射输出。

- **Rationale**：F0 immutable 原则已确立，roster 身份是比位置更硬的状态；F1 改身份会把已公开的轨迹身份搞乱。
- **Alternatives**：允许 F1 修正身份 —— 被否，身份修正应回到 F0 重跑或显式 roster_reset。

### 生命周期总图（本次修订后必须写死）

```text
unmatched observation
        ↓
candidate pool（candidate_N，按 D2 归属规则累积证据）
        ↓
promotion（D2：双摄 ≥2 tick 或单摄 ≥5 tick）
        ↓
provisional roster occupant（占 slot）
        ↓
activation confirmation（D3：全部 slot 占用 + 每 occupant 稳定 K tick 或 ≥1 次 cross-view anchoring）
        ↓
ROSTER_ACTIVE（只维护已知球员）

之后 observation 只走：
  ├─ stable continuity（强绑定）
  ├─ historical reacquire（弱绑定 + 证据）
  ├─ guided recovery（guided_roi 观测，expected global 强约束；base 优先）
  ├─ pending reassociation（D6 强证据迟滞）
  └─ unresolved（暂不确定，计数 + diagnostics）

绝不再走：unmatched → new global
```

## Risks / Trade-offs

- [bootstrap 早期错误配对被固定] → D2 候选晋升需连续证据 + D3 两级确认窗口（K tick / cross-view anchoring）+ D4 弱绑定可被重新证明推翻。
- [网前近距（~1.5ft）配对歧义] → D5 换人用更严门 + D6 强证据迟滞（switch_margin + 连续一致）；若仍不足，后续可引入 ReID（Non-Goal，第一版不引入）。
- [参数（2/5 tick、base/max gate、switch_margin、K tick）未经真实数据标定] → 本 change 提供结构 + 保守默认；Open Questions 中明确用 job-f473d041a6 同源 trace 的 residual 分布标定。
- [弱历史绑定在换人场景（替补上场）误复用] → 由 roster_reset / participant-change 事件兜底；普通赛内不处理换人。
- [ROSTER_ACTIVE 后误判 unresolved 导致漏检] → recovery 链路（guidance）仍可把观测救回 roster；unresolved 是"暂不确定"，非永久丢弃。
- [stale 玩家退出普通匹配后长期未恢复] → 由 guidance / historical reacquire 路径兜底；若整场未恢复，report 以 confirmed_player_count 如实呈现（见统计语义）。

## Migration Plan

1. 现有 `fix-joint-tracking-result-chain` 已归档且 tasks 全部完成（解帧 POS_FRAMES、时间戳契约、视觉层产物、stage 状态），基线干净，无需回滚。
2. 本 change 内部实现顺序（见 tasks.md）：registry roster 化 → candidate pool（含归属规则）→ associator 改造 → 两级 continuity → guided 强约束 + base 优先 → compose roster.v1 + structured data → 真实视频验收。
3. 兼容：`late_fusion_v1` 路径（P0 associator）不受影响；候选池与 roster 为增量语义，registry 接口变更以 `allocate_roster_slot` 取代 `new_global_id` 的公开调用点（仅 associator 内部一处）。
4. 回滚：若验收失败，恢复 registry 创建处传参并保留旧 associator 分支（保守默认参数不改变接口签名），可快速 revert。

## Open Questions

1. 候选晋升阈值（双视角 ≥2 tick / 单视角 ≥5 tick）与过期窗口——需用真实 trace 标定；先按保守默认实现并暴露配置。
2. `base_gate_ft` / `max_reacquire_gate_ft` / `uncertainty_scale` 具体值——需统计 job-f473d041a6 同源素材的 canonical residual 分布后确定；本 change 先实现机制。
3. roster 确认窗口 K tick（默认建议 30）与"至少一次 cross-view anchoring"的组合条件——验收时用真实 take 确定。
4. `switch_margin` 具体值（默认建议 0.15）——需用网前交叉场景 trace 标定。
5. stale 退出阈值（uncertainty / last_seen_age）——需真实遮挡场景数据标定。
6. `ROSTER_ACTIVE` 下 unresolved 观测是否需进 quarantine 缓冲（供后续回看）——第一版仅计数与 diagnostics，不进缓冲。
