## Context

当前系统已有逐帧 canonical `Player_N` 轨迹、球场坐标、正式 `AnalysisWindowPlan` 以及 `shot-rally-events.v1` / `metric-snapshot.v1`。前置 change `add-analysis-roster-and-rally-context` 将提供任务绑定的发球队、Team A/B、端位、身份 audit 与正式窗口 context；本 change 不创建或修正这些事实。

## Goals / Non-Goals

**Goals:**

- 用真实轨迹的厨房线距离和毫秒级稳定条件计算可审计的分子、分母及充分度状态。
- 在 `/analysis/:jobId/vision` 的真实任务数据分析区提供四人对照卡，且不影响视频和既有图表。

**Non-Goals:**

- 不通过 CV 猜测发球队、真实姓名、Team A/B 或端位；缺失前置 job-bound context 的任务不计算该指标。
- 不把进入厨房区、全局 `zone_stats`、第三拍机会、回合时长或技能评分混入 V1。
- 不提供逐回合回跳、视频 clips 或单回合 0%/100% 卡片。

## Decisions

### 1. 只消费前置冻结上下文

每个 rally/player 输入必须同时具有 Job-bound `AnalysisRallyContextSnapshot`、confirmed identity audit、formal window binding 和真实轨迹。计算器从 context 读取队伍、发球队和己方端位，不读取当前 LiveCodingState、可编辑名册或 `initial_side`；任一前置输入 unavailable 时，样本不得进入分母。

### 2. 非对称证据状态机

配置 `kitchen-arrival-reference.v1` 至少包括 `arrival_band_m`、`stable_ms`、`arrival_min_detected_support_ms`、`not_arrived_min_coverage_ratio`、`not_arrived_max_gap_ms` 与最小样本数。真实 `detected` 点及稳定支持可证明 `arrived`；回合开始时已经稳定进入到位带为 `already_present`、到位时间为零。只有达到覆盖率、最大缺口、且无可能跨越到位带的不确定区间时，才可判定 `not_arrived`；其余为结构化 `excluded`。

### 3. 格式无关 calculator，双打优先发布

calculator 只依赖 context 和轨迹证据，不含“双摄”分支。当前产品通过 feature flag 仅向满足双打入口要求的任务展示 card；未来单摄只要提供同一输入契约，即无需重写指标。

产物计算与卡片发布使用两个独立开关：`PICKLEBALL_KITCHEN_ARRIVAL_ENABLED=false`
停用 `kitchen-arrival.v1` 计算并写出 `skipped` 状态；
`PICKLEBALL_KITCHEN_ARRIVAL_CARD_ENABLED=false` 或前端
`VITE_KITCHEN_ARRIVAL_CARD_ENABLED=false` 只停用卡片加载/展示，不删除已存在的审计产物。
当 artifact 为 `skipped` 时，前端也不得发起 artifact 请求或渲染卡片。

### 4. 汇总与 UI 均诚实表达不确定性

`kitchen-arrival.v1` 保存 per-player 计数、证据/排除诊断及所有输入版本。有效分母低于最小样本数时，`metric-snapshot.v1` 保留计数但写 `status=insufficient_evidence`、`value=null`；UI 显示“1/2 · 样本不足”而非 50%。主卡独立加载，无 artifact 或前置输入时局部 unavailable，不以 demo 或厨房占用率代填。

## Risks / Trade-offs

- [前置 context 或 identity audit 不可用] → 整个指标 honest unavailable，不回读现场可变状态或猜测。
- [遮挡造成假阴性] → `not_arrived` 采用覆盖率、最大缺口和跨越不确定性三重反证门。
- [阈值未经校准] → 参数版本化，并在锁定人工回放集上校准。
- [较早阶段开放 single-view] → 以产品 feature flag 控制，不污染计算器语义。

## Migration Plan

1. 等待前置 change 发布 roster/context/formal-binding contract；旧 Job 继续显示 unavailable。
2. 发布 calculator 与 artifact 路由，先以 unavailable/insufficient 状态验证真实输入。
3. 以小规模人工回放样本校准参数，再启用双打产品入口的 card feature flag。
4. 如发现计算缺陷，停用 artifact/card；不影响视频、计分、轨迹或既有指标，既有产物按 calculation/reference version 区分。

## Open Questions

- `arrival_band_m`、`stable_ms`、最大允许缺口及最小样本数应由哪个锁定人工回放集校准；实现不应把未校准数值写死。
