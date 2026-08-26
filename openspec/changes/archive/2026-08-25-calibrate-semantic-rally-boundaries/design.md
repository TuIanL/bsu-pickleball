## Context

第二阶段已经把 manual/corrected 时间线接入单摄和双摄正式球链，并通过 `boundary_action_id` 保证封存、重置和重新打开不会在连续 tick 中重复执行。当前不足在于：算法证据仍以单 tick 判断为主，`RALLY_END_CANDIDATE`、`PRE_SERVE` 和 `SERVE_ARMED` 缺少统一的持续窗口与冲突处理；真实球场中的漏检、球员短暂停止和捡球动作可能让语义状态在相邻 tick 之间抖动。

本阶段需要在不改动球体模型、不破坏 Shadow/fail-open 默认行为的前提下，将语义层从“当前 tick 的策略建议”提升为“带证据历史的回合边界仲裁”。主要消费者包括单摄 `AnalysisPipeline`、双摄 canonical runner、`BallTracker`、ServeStartDetector 和可审计 artifact 体系。

## Goals / Non-Goals

**Goals:**

- 建立统一、可序列化、带来源和时间范围的 semantic evidence ledger。
- 用多证据 corroboration、时间迟滞、最小持续窗口和 contradiction handling 稳定回合开始/结束边界。
- 在尚未确认结束时保留 pending 状态；在有效球运动和比赛活动重新出现时支持 `rescued_active`，避免过早封存真实球路。
- 让确认后的 boundary action 继续复用第二阶段的幂等 Tracker 生命周期，不重复 detector，不跨段发布。
- 生成可重放的语义边界评估 artifact，并输出 precision、recall、延迟、误抑制和跨段污染等指标。
- 以 2026-07-20 双摄素材和合成案例建立稳定的回归基线，支持 Shadow/Enforced 对照。

**Non-Goals:**

- 不重新训练、替换或修改 `models/ball/tennis-ball.pt`。
- 不让 algorithmic evidence 单独触发正式 hard gate、比分变更或最终 rally result。
- 不在本阶段实现最终击球者归属、真实出界裁决、比分裁决或新的技能评分。
- 不引入在线自学习或自动修改生产阈值；校准结果必须通过版本化配置显式发布。
- 不删除或回写历史 `ball_trajectory`、`reconstructed_ball_trajectory` 和已有分析 artifact。

## Decisions

### 1. 使用不可变 evidence ledger，而不是在 snapshot 中覆盖证据

每个 canonical tick 生成 `SemanticEvidenceRecord`，至少包含 `evidence_id`、`timestamp_ms`、`kind`、`source`、`confidence`、`fresh_until_ms`、`payload_summary` 和 `provenance`。`MatchSemanticSnapshot` 只引用本 tick 的 evidence ids 和聚合摘要，原始证据不被后续状态覆盖。

这样可以区分“ServeStartDetector 没有返回候选”和“本 tick 没有运行 detector”，也可以在回放中识别 7 月 20 日验证中人工复用的 serve candidate evidence，避免把测试输入误报为模型输出。

替代方案是继续向 snapshot 追加布尔字段。该方案实现简单，但无法表达证据新鲜度、来源冲突和回放 provenance，因此不采用。

### 2. 使用确定性的 BoundaryAdjudicator 和迟滞计数

在 `SemanticStateMachine` 与 `BallSearchPolicy` 之间增加边界仲裁逻辑。仲裁器按 canonical 时间顺序维护：

- 当前确认 phase；
- `pending_start` / `pending_end` 的起始时间和累计 corroboration；
- contradiction evidence 与 freshness；
- 当前 formal segment id；
- 最近一次确认 boundary 的 id。

默认策略要求结束或开始证据跨越配置的最小持续时间/ tick 数，并根据证据类型使用不同权重；单一球丢失、单一 bounce 候选或单次球员静止只能进入 candidate，不得直接确认边界。所有 tie-break 都由 `policy_version` 和配置快照决定，保证相同输入重放一致。

替代方案是使用滑动窗口平均后直接切换 phase。平均值无法表达边界方向、证据冲突和 rescue，因此不采用。

### 3. 权威边界与算法 rescue 分层

manual/corrected 的确认 `non_play`、`rally_end` 和 `rally_start` 仍然是 Enforced 正式生命周期的唯一硬 authority。algorithmic evidence 可以推进 pending、改变搜索优先级和生成 `rescued_active` 诊断，但不能单独执行 `seal_formal_segment` 或 `reset_tracker_for_next_rally`。

如果结束候选尚未确认，随后出现满足运动性、连续性和球员比赛活动的证据，仲裁器撤销 pending end 并记录 `rescued_active`。如果权威 boundary 已确认并执行 reset，后续有效球只能通过新的 serve/rally start 重新打开 segment，不允许偷偷追加到旧 segment。

替代方案是让算法证据在稳定若干帧后直接 hard reset。该方案可能减少捡球误检，但会把规则误判变成不可逆的正式轨迹损失，因此暂不采用。

### 4. 诊断与评估 artifact 独立于正式球轨迹

新增 `ball_semantic_boundary_eval.v1`（建议文件名 `ball_semantic_boundary_eval.json`），记录输入 take、policy/rollout 版本、每 tick evidence ledger 摘要、候选/确认 phase、boundary action、formal candidate before/after、segment id、人工参考标签（若存在）和评估指标。

该 artifact 是可选诊断产物，不替代 `ball_trajectory` 或 `reconstructed_ball_trajectory`。正式结果仍由既有 tracker 和轨迹 artifact 提供，便于 Shadow 与 Enforced 结果并行比较。

### 5. 以固定案例和真实素材回放校准，不做在线阈值学习

将 7 月 20 日双摄 take 的代表性时刻和合成时间线案例纳入 fixture。回放脚本必须记录每条 evidence 的来源，区分真实 detector/ServeStartDetector 输出、人工时间线和测试注入。阈值通过版本化配置调整，评估输出只给出建议，不自动改写配置。

### 6. 双摄共享仲裁结果，单摄复用同一 policy contract

双摄每个 canonical tick 只创建一个 evidence ledger、snapshot、adjudication result 和 boundary action id；两路 tracker 在 commit 前消费同一结果。单摄直接调用相同的 policy contract，不另建一套 phase 推断逻辑。缺帧、`available_extrapolated` 或 provider 失败保持现有 fail-open 行为。

## Risks / Trade-offs

- [确认延迟增加] → 使用独立的 `pending` 和 `confirmed` 状态，并将延迟纳入指标；权威人工边界仍可立即确认。
- [rescue 让捡球误检重新进入搜索] → rescue 只在结束尚未确认时有效，并要求球运动、连续性和球员活动的联合证据。
- [证据来源不一致] → 使用 evidence provenance、freshness 和 policy version；冲突时保守降级到 pending/UNKNOWN。
- [真实素材标注成本高] → 先覆盖 7 月 20 日关键窗口和小型合成 fixture，指标设计支持逐步扩充。
- [诊断 artifact 增大] → 每 tick 保存摘要和引用，原始大对象只保留必要字段；artifact 仍可选，不阻塞主分析。
- [新配置影响历史结果] → 默认 Shadow/fail-open，配置快照写入 job；历史 artifact 不回写，Enforced 只对显式启用的 take 生效。

## Migration Plan

1. 先实现 evidence ledger、adjudicator 和 replay artifact，但默认只生成 Shadow 诊断。
2. 在合成 fixture 和 2026-07-20 双摄素材上建立基线，核对 boundary action、detector 调用次数和现有正式轨迹不变。
3. 对显式 rollout take 启用确认边界的 Enforced 生命周期，比较误抑制率和跨段污染率。
4. 若指标退化，关闭 rollout 即回退到第二阶段行为；不删除 raw evidence 或诊断 artifact。

## Open Questions

- 7 月 20 日素材首批人工参考边界是否只标注回合开始/结束，还是同时标注发球预热区间？
- `grace_window_sec` 和 `min_confirm_ticks` 是否按 60 FPS 与抽帧 stride 分别配置，还是统一换算到 canonical seconds？
- 评估 artifact 是否需要在前端提供逐 tick 时间线可视化，还是先通过后端 JSON 和离线报告验收？
