# make-player-report-evidence-driven

## Why

现有 PB Vision 风格报告页（`pb-vision-style-report-page`，in-progress）已具备外框、卡片、配色与布局语言，但报告主体的**数据可信度与 Player-scoped 数据链**仍未对齐真实分析结果：

- 报告页把 `performanceInsights.subjects` 整体当作可选主体，没有强制 player-only，导致 team subject（如"近侧组合"）进入 Player Report，进而所有下游数据（总击球数/热力图/距离）匹配不到而显示 `0` 或 mock。
- 关键指标在 `report.source === "job"` 的真实任务下仍由前端伪造：`mockInPercent` / `mockSpeedPercentile` / `stableHash01` 生成球速拍速 / `mockServeReturnStats` / `mockServeReturnDepth` / `Court Coverage 727ft fallback` / Coach 与 LegalThirds 默认建议 / Skill Rating 顺序兜底 + 2.0~5.5 换算。
- 3D 球场虽然创建了轨迹但 `points: []`，完全没接上已存在的正式 Ball Trajectory / reconstructed trajectory artifact。
- 第三拍筛选用 `shotNumber = i + 1`（整场 shotRows 下标），不是 rally 内序号，语义错误。
- Coach"匹克球认证教练 · 8 年经验"是静态产品包装，缺 evidence 也能生成建议。
- 底层能力边界未核实：`ServeEventsArtifact` 目前只做"发球开始事件检测"，并不能直接产出 In/Out、落点、深度、接发事件；`global_player_N` 到 canonical `Player_N` 的映射由 `global-player-roster.v1` 决定，不能按尾号猜。

现状既有的 `pb-vision-style-report-page` Proposal 明确写着"Serves/Returns Depth、Δ 值、长期平均等无对应字段模块均采用前端 mock"。这与本变更要建立的可信度原则直接冲突，需要被取代。

本变更**不否定既有的 PB Vision 视觉布局能力**，而是把报告从"PB Vision 风格 + 为展示而生成类似数据"，收口为"PB Vision-inspired presentation + 瞬境自己的真实 evidence"。

## What Changes

- 引入 **evidence adapter（PlayerReportEvidence 层）**，并按 I/O 与纯转换拆分：`usePlayerReportEvidence(jobId, report, playerId)` 负责加载/缓存/组装 `PlayerReportEvidenceSources`（report + roster + serveEvents + ballTrajectory + reconstructedTrajectory + bounceEvents + visualization），`buildPlayerReportEvidence(sources, playerId)` 是纯函数转换，PB 组件只消费结果。
- 指标值采用强类型 **`EvidenceValue<T>`**（`status: available/unavailable/not_applicable/failed` + `provenance[]` + `reason` + `confidence`），替代 `number | null`，让"缺数据"与"来源/原因"成为机器可验证的契约，而非开发规范。
- **Player-only subject contract**：Player Report 主体只能是 `PerformanceSubject.kind === "player"` 的 canonical player（`Player_1..Player_4`）；`team_near / team_far` 不进入 player selector，未来 Team Report 另行实现。关联一律按 canonical player id，不再用 `row.player === subject.name` 展示名匹配。
- **全局身份解析：禁止按尾号猜映射**。`P1` / `player_1` 等做语法归一化到 `Player_1`；`global_player_N` 只能经 `global-player-roster.v1` 正式映射到 canonical `Player_N`；无映射时视为 `unavailable`。两个不同职责拆成 `normalizeCanonicalPlayerAlias()`（语法）与 `resolveGlobalPlayerId()`（roster），不合并。
- **source fail-closed**：仅 `report.source === "demo"` 走 Demo Adapter（页面显式标注"演示数据"）；`job / undefined / unknown` 一律 evidence-only。
- **source=job 全面清零 mock**：真实任务若 backend artifact 无对应指标，当 `EvidenceValue` 为 `unavailable`，统一显示"本次分析暂未生成"，绝不返回近似值。清理清单见 design.md，并用"`pb-vision` 组件不得 import mock/DemoAdapter（Demo 数据入口除外）"的架构测试锁死。
- **Serve/Return 先做 authority audit（P0 scope gate）**：`ServeEventsArtifact` 只能证明发球开始/发球者/发球起点，不能产出 In/Out、深度、接发。逐指标按"系统能证明什么就展示什么"降级；不能证明的显示"暂未生成"，而不是为了保住 PB 模块形态硬接错误数据。
- **3D Court 改接正式 Ball Trajectory artifact**：停止从轻量 `shotTrajectories` 伪造 Three.js 输入，改为消费正式球路产物 + 按 selectedPlayerId + filter 筛选后喂 `BallTrajectoryScene`。
- **第三拍（阶段）ordinal contract 先裁决再编码**：以 `rallyId + ordinalInRally` 标识第几拍（1=发球 2=接发 3=第三拍 4=第四拍 5+=后段）。先做 contract spike（rally boundary / hit event / ordering timestamp / duplicate-missing / player ownership / multiview-vs-single-view 的 authority），再决定 adapter-derived 还是 backend `ordinal_in_rally`，最后实施；PB 组件禁止 `i + 1` 推断。
- **Skill Rating 暂停仿 PB 分数（fail-closed）**：正式模型必须带 `player-skill-rating.v1` schema + `modelVersion`；在它出现前，job 模式一律不显示 PB 式 2.0~5.5 评分，模块改名为"本场表现概览"或提示"技能评分模型尚未生成"（不能把现有长度=6 的旧 `skillRatings` 误当作正式模型）。
- **Coach / Legal Thirds 改 evidence-driven**：去掉假"认证教练"身份，改"AI 训练洞察·基于本场可观测指标生成"；没有 numerator/denominator 时不再自称"合法第三拍率"。
- 本变更范围含**最小可用 Player Selector**（`P1..P4` chip/下拉）以验证各 player evidence 切换正确，但不做 PB 风格视觉优化。

## Capabilities

### New Capabilities

- `player-report-evidence`: 报告页证据适配层。定义 `PlayerReportEvidence` 聚合契约（summary / court coverage / serve & return / shot exploration / trajectory / evidence-driven insight）、强类型 `EvidenceValue<T>`、全局身份解析（syntactic alias + `global-player-roster.v1`）+ I/O hook 与纯转换，统一按 canonical player 取数，并在 fail-closed 的 source 策略下执行"缺失即 unavailable"，是 PB 组件与底层 artifact 之间的唯一数据入口。

### Modified Capabilities

- `pb-vision-style-report`: 修改其数据来源与可信度契约——保留既有视觉布局能力，移除 fake-mock/伪映射/伪 Serve-return 深度/假教练/伪第三拍统计，消费 `player-report-evidence` 层。
- `interactive-performance-report`: 表现洞察面板纳入 evidence adapter，findings/recommendations 仅在真实 evidence 存在时作为 Coach/训练建议来源。
- `report-detail-pages`: 报告详情页在 `job` 源下不再展示 mock/近似值，缺失模块按 unavailable 呈现。
- `multiview-global-player-roster`: 作为 `global_player_N → Player_N` 映射的权威来源被 `player-report-evidence` 消费（只读引用，不改契约）。

## Impact

**Affected code**:
- `src/contexts/PbReportContext.tsx` — subjects 收口为 player-only，采用 canonical id 关联，接入 evidence adapter
- `src/utils/pbMockData.ts` — 从"默认 mock"收紧为"仅 demo 可用"，并迁移至独立 Demo Adapter，真实 job 路径不再引用
- `src/components/pb-vizion/` 下 `PbPlayerHeaderCard.tsx` / `Pb3DCourtCard.tsx` / `PbSkillRatingSection.tsx` / `PbCourtCoverage.tsx` / `PbServesReturns.tsx` / `PbCoachInsight.tsx` / `PbLegalThirds.tsx` / `PbFilterToolbar.tsx` / `PbSkillPieChart.tsx` — 统一改读 evidence adapter，移除各自 fallback/伪数据
- 新增 evidence layer：`EvidenceValue` 类型、`buildPlayerReportEvidence`（纯转换）、`usePlayerReportEvidence`（IO hook）、全局身份解析工具、Demo Adapter/Provider（位置见 design.md）

**Affected APIs / dependencies**:
- 无第三方新增。Serve/Return 与第三拍 ordinal 均以 authority audit / contract spike 先行裁决（可能动 ServeEvents / hit event / reconstructed trajectory contract，登记于 design.md）。`player-report-evidence` 只读引用 `global-player-roster.v1`。

**Affected systems**:
- **Library-first** 报告视图（`/library/...?view=report` 的 report view，`LibraryItemWorkspace` 内挂载 `PbReportContent`）+ 若仍保留的 legacy 报告路由 `/report/:id` 兼容路径；`job`/`demo` 两源分流。首页/录制/分析工作区等同 `pb-vision-style-report-page` 保持一致，不受此变更影响。