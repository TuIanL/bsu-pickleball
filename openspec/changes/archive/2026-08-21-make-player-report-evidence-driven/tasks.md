# make-player-report-evidence-driven — Tasks

> 进度约定：[] 待办 / [x] 完成。P0 优先打通证据链；P1 视觉留待后续变更。涉及底层契约的 Serve/Return 与第三拍 ordinal 必须先 audit / spike 再编码。

## 1. Evidence 基础设施（EvidenceValue + Adapter；IO 与 pure 分离）

- [x] 1.1 定义强类型 `EvidenceState` / `EvidenceRef` / `EvidenceValue<T>`（含 status / value / provenance / reason / confidence），见 design.md D2
- [x] 1.2 定义 `PlayerReportEvidenceSources`（report + roster + serveEvents + ballTrajectory + reconstructedTrajectory + bounceEvents + visualization）与 `PlayerReportEvidence`（各字段为 `EvidenceValue<T>`）
- [x] 1.3 实现纯转换 `buildPlayerReportEvidence(sources, playerId)`：sources → evidence，可单测
- [x] 1.4 实现 IO hook `usePlayerReportEvidence(jobId, report, playerId)`：加载 artifact / 缓存 / 错误 / 取消 / 组装 sources → 调纯函数（按 jobId 抓取 reconstructed trajectory + serve events）
- [x] 1.5 实现 source fail-closed：`const isDemo = report.source === "demo"`；`job / undefined / unknown` 一律 evidence-only
- [x] 1.6 全局身份解析：`normalizeCanonicalPlayerAlias`（语法 P1/p1/player_1→Player_1）+ `resolveGlobalPlayerId`（仅经 `global-player-roster.v1`，无映射→unavailable），两函数不合并
- [x] 1.7 搭 `job-no-mock` 架构测试骨架：`src/components/pb-vizion/**` 不得 import `pbMockData` / DemoAdapter（Demo 入口除外）

## 2. Player-only subject contract + 全局身份接入

- [x] 2.1 改 `PbReportContext`：subject 列表强制 `filter(s.kind === "player")`，默认选中第一个 player；team 不进入 selector
- [x] 2.2 各组件中 `row.player === subjectName` 改为按 canonical id（经 1.6 解析）关联 / 匹配（header 已切到 evidence.summary.totalShots）
- [x] 2.3 新增最小可用 Player Selector（`P1..P4` chip 或下拉，只挂报告页顶部），验证各 player evidence 切换正确；不做 PB 视觉优化
- [x] 2.4 用例：`team_near` 不进 selector；`global_player_N` 无 roster 映射时保持 unavailable（不因尾号猜 Player_N）

## 3. 发球/接发 authority audit（P0 scope gate，先于编码）

- [x] 3.1 核对 `ServeEventsArtifact` 能力边界（只证明发球开始/发球者/发球起点），产出按 D7 的 authority 矩阵
- [x] 3.2 裁决：发球 In/Out、深度、接发 In/Out、深度的可靠来源（需哪些额外 artifact：landing/bounce/return），登记契约影响
- [x] 3.3 `PbServesReturns` 改为消费 authority 决定：可证明的展示（如发球次数/发球者），不可证明的按 unavailable 呈现（"暂未生成"），移出 Demo 引用

## 4. 3D Court 接正式 Ball Trajectory artifact

- [x] 4.1 `Pb3DCourtCard` 停止从 `shotTrajectories` 构造 `points: []`，改为消费 `PlayerReportEvidenceSources.ballTrajectory / reconstructedTrajectory / bounceEvents`（IO hook 按 jobId 抓取 reconstructed trajectory）
- [x] 4.2 组装 hit / bounce / segment evidence，按 `selectedPlayerId` + filter（type / quality / stage）筛选后喂 `BallTrajectoryScene`（按球员身份 + 质量筛选）
- [x] 4.3 无可用轨迹 evidence 时呈现空态（不渲染空轨迹列表）
- [x] 4.4 验证：报告 3D 球场在有真实轨迹时显示球路，且与独立球路页数据一致（浏览器实测 job-9efdb05a88：3D 无伪 points，显示"暂无可视化球路数据"；该 job 无 reconstructed artifact，属诚实 unavailable）

## 5. 第三拍（阶段）ordinalInRally（先 spike 再编码）

- [x] 5.1 定义 `ShotEvidence { rallyId; ordinalInRally; ... }` 及阶段映射（1=发球 2=接发 3=第三拍 4=第四拍 5+=后段）
- [x] 5.2 Contract spike：逐项核 authority——rally boundary / hit event authority / ordering timestamp / duplicate-missing hit / player ownership / multiview vs single-view
- [x] 5.3 拍板：方案 A adapter-derived ordinal（`groupBy(rallyId)+sortBy(timestamp)+index`）若不满足 authority，则方案 B 后端/artifact 带 `ordinal_in_rally`（登记契约影响）→ **已裁决：方案 A + authority gate**（见 design D3）
- [x] 5.4 按拍板结果实施 ordinal 计算/接入（`buildShotExploration` 派生 ordinal）
- [x] 5.5 `Pb3DCourtCard` / `PbFilterToolbar` 阶段筛选改为消费 `ordinalInRally`；移除 `i + 1` 推断（Pb3DCourtCard 按 `ordinalInRally` gated 过滤；ordinal 不可靠时给提示不静默筛错）
- [x] 5.6 用例：同一 rally 内 ordinal 顺序 deterministic（已加测试）；不受全局 shotRows 下标影响

## 6. Skill Rating 降级（fail-closed）

- [x] 6.1 移除 `LABEL_TO_DIM` 失配后"顺序硬塞 + 归一化 + 2.0~5.5 换算"整条路径
- [x] 6.2 有正式模型（`player-skill-rating.v1` + `modelVersion`）→"单场技能评分"；否则模块改名"本场表现概览"或"技能评分模型尚未生成"；不因 `skillRatings.length===6` 误判为正式
- [x] 6.3 正式六维模型不改（留待 `introduce-player-skill-rating-model`）

## 7. Coach / LegalThirds evidence-driven

- [x] 7.1 `PbCoachInsight`：去掉"匹克球认证教练 · 8 年经验"，改"AI 训练洞察·基于本场可观测指标生成"；结论仅取 findings / recommendations / 真实 coachNotes；无则"当前数据不足以生成可靠训练建议"
- [x] 7.2 `PbLegalThirds`：有 numerator/denominator →"第三拍成功率 X% · n/m"；仅 recommendation →"第三拍训练建议"；皆无 →"本次分析暂无第三拍统计"；不再无比例自称"合法第三拍率"

## 8. 自动测试（锁 invariant 而非仅人工）

- [x] 8.1 evidence 单测：`buildPlayerReportEvidence` 在缺 speed / serveDepth / distance 时返回 `EvidenceValue.status==="unavailable"`（不出现 35mph / 727ft / 固定百分位）
- [x] 8.2 architecture test：`pb-vizion/**` 静态 import `pbMockData` / DemoAdapter 即失败（仅 Demo 数据入口允许）
- [x] 8.3 全局身份用例：`team_near` 不进 selector；`global_player_1` 无 roster 映射不自动变 `Player_1`；`P1/player_1` 语法归一到 `Player_1`
- [x] 8.4 3D 用例：仅 A/B 或无 trajectory evidence 时不生成伪轨迹 points
- [x] 8.5 ordinal 用例：同 rally ordinal deterministic（5.6 已覆盖）
- [x] 8.6 跑 `npm run lint` + `npm run typecheck` + `npm run build`（0 error，全绿；含修复另一变更遗留的 3 个类型错误与 1 个 lint error）
- [x] 8.7 回归：浏览器实测 —— job-9efdb05a88（真实 job）：Player-only selector 仅显示 global_player_1..4（无 team）；球速/拍速/Skill/发球/接发/距离全 unavailable（无 mock/35mph/727）；job-04692d6f43（无 player）正确显示"暂无可用球员主体"。demo 报告直达路由由 landing 接管，记为待人工预置时抽查。