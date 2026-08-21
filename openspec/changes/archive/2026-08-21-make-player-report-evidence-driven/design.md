# make-player-report-evidence-driven — Design

## Context

当前报告页（PB Vision 风格）构建在 `PbReportProvider` + 8 个 `Pb*` 组件之上，数据来源混乱、可信度无约束。已核实的现状：

- `PbReportContext.getAllSubjects()` 直接把 `performanceInsights.subjects` 当候选，未强制 `kind === "player"`，默认选中 `subjects[0]`（可能是 `team_near`）。
- 多个组件按 `row.player === subjectName`（展示名）匹配，heatmap 却是按 id（`Player_1` / `global_player_1`）匹配，两者脱节。
- `Pb3DCourtCard` 把每个 `report.shotTrajectories` 条目转成 `EstimatedBallTrajectory` 但 `points: []`；而系统已有正式 `BallTrajectoryArtifact` / `ReconstructedBallTrajectorySample`（hit event / segment）未被报告页消费。
- 第三拍筛选在组件里用全局 `i + 1` 当作拍序号；`ShotRow` 只有 `rally_id`，没有 `shot_ordinal_in_rally`。
- `src/utils/pbMockData.ts` 集中了 `mockInPercent / mockSpeedPercentile / mockServeReturnStats / mockServeReturnDepth / stableHash01`，`PbPlayerHeaderCard` 还用 `stableHash01` 直接造球速/拍速。
- Skill Rating：`skillRatings` 按 label 匹配，匹配不到就按数组顺序硬塞六个维度，再 `raw01 * 3.5 + 2` 映射到 2.0~5.5、六项平均得综合分。
- Coach 卡硬编码"匹克球认证教练 · 8 年经验"，无 evidence 时返回固定建议；LegalThirds 标题叫"合法第三拍率"但只在文本里搜"第三拍"，没有真实比例。
- 底层能力边界：`ServeEventsArtifact` 只检测"发球开始"（timestamp / frame_index / confidence / player_id / court_position / detection_mode / signals），**无** In/Out、落点、深度、接发事件；`global_player_N → Player_N` 由 `global-player-roster.v1` 决定，非全局/槽位序号。

根因是：报告页绕过了底层真实 artifact，自己拼了一套 `ShotRow[]` + mock。修复思路是加一层 **evidence adapter**，让 PB 组件不再各自找数。

## Invariants（不可违反）

1. **Player Report 的主体只能是 canonical player**（`PerformanceSubject.kind === "player"`，id 为 `Player_1..Player_4`）；team（`team_near/team_far`）永不进入 player selector。
2. **`source === "job"` 必须 evidence-only**：真实任务零 mock / stableHash / 固定 fallback。
3. **缺失数据表现为 `unavailable`，不表现为近似值**：真实 job 缺什么就显示"本次分析暂未生成"，绝不回退成可信数字。
4. **PB Vision 只作为信息组织与视觉参考，不复制其评分值**：不借用 PB 的历史 profile / rating 数值做展示。
5. **所有报告指标必须能追溯到明确 artifact / event / finding**：任何展示数字都要有 `provenance`（来源链），不能只来自"长得像"。
6. **`global_player_N` 只能经 `global-player-roster.v1` 映射到 canonical，禁止按尾号猜**；无映射 = `unavailable`。
7. **系统只能展示其底层能力能证明的指标**：发球/接发的 In/Out、深度、落点在 authority 未建立前一律 `unavailable`，不硬凑。
8. **source 分流 fail-closed**：仅 `source === "demo"` 允许 mock；`job / undefined / unknown` 一律 evidence-only。

## Goals / Non-Goals

**Goals:**
1. 建立 `PlayerReportEvidence` 证据层（`EvidenceValue<T>` + provenance），作为 PB 组件读取球员数据的唯一入口，并拆分为 IO hook 与纯转换。
2. fail-closed 的 `source` 分流；mock 隔离在独立 Demo Adapter。
3. Player Report 主体收口为 player-only，全局身份经 roster 解析。
4. 3D Court 消费正式 Ball Trajectory / reconstructed trajectory artifact。
5. Serve/Return 先 authority audit，只展示能证明的指标。
6. 第三拍改 `rallyId + ordinalInRally`，先 contract spike 再编码。
7. Skill Rating fail-closed 降级；Coach / Legal Thirds 改 evidence-driven。

**Non-Goals:**
1. 不继续"美化"报告页视觉（布局密度、radial skill chart、Player summary 合并首屏等留到后续 P1 变更）。
2. 不实现正式 6 维技能评分模型（后续单独变更 `introduce-player-skill-rating-model`；需要 `player-skill-rating.v1` schema + `modelVersion`）。
3. 不做 Team Report（后续单独实现）。
4. 不重写 `BallTrajectoryScene` 内部 Three.js 渲染逻辑。
5. 不改动首页/录制/分析工作区等其他页面。
6. 不在 Serve/Return / 第三拍 authority 未建立前编造指标（允许这些子模块先 unavailable）。

## Decisions

### D1. Player-only subject contract + 全局身份解析
`PbReportProvider` 的 subject 列表强制 `filter(s => s.kind === "player")`，default 选中第一个 player。所有跨模块关联一律用 canonical player id，**禁止** `row.player === subjectName`。

全局身份解析拆成**两个职责不同的函数**，不合并：

```ts
// 语法别名：仅处理大小写/前缀，纯字符串
normalizeCanonicalPlayerAlias(id: string): string | null
// P1 / p1 / player_1 / Player_1  →  "Player_1"

// 内部全局身份：必须经 roster 映射，禁止按尾号猜
resolveGlobalPlayerId(id: "global_player_N", roster: GlobalPlayerRosterV1): string | null
// global_player_1  →  roster 里的 canonical（可能是 Player_3）
// 无 mapping → null（= unresolved / unavailable）
```

**为什么拆分**：`P1→Player_1` 是纯语法，`global_player_N→Player_N` 是语义映射。塞进一个函数极易被误用成"按尾号猜"。

### D2. EvidenceValue 强类型 + Adapter（IO 与 pure 分离）
指标不再用 `number | null`，改用带来源/原因/置信度的强类型：

```ts
type EvidenceState = "available" | "unavailable" | "not_applicable" | "failed";

interface EvidenceRef {
  kind: "report" | "serve_events" | "ball_trajectory" | "reconstructed_trajectory"
      | "heatmap" | "performance_insight" | "roster";
  artifactId?: string;
  eventId?: string;
  field?: string;
}

type EvidenceValue<T> =
  | { status: "available"; value: T; provenance: EvidenceRef[]; confidence?: number }
  | { status: "unavailable" | "not_applicable" | "failed"; value: null; reason: string; provenance?: EvidenceRef[] };
```

`PlayerReportEvidence` 的每个字段都是 `EvidenceValue<T>`：

```ts
interface PlayerReportEvidence {
  playerId: string;
  summary:       { totalShots: EvidenceValue<number>; inRatePct: EvidenceValue<number>;
                   ballSpeedMph: EvidenceValue<number>; paddleSpeedMph: EvidenceValue<number>; ... };
  courtCoverage: { distanceFt: EvidenceValue<number>; heatmap: EvidenceValue<HeatmapPlayerGrid>; ... };
  serveReturn:   { serves: EvidenceValue<...>; returns: EvidenceValue<...>; depth: EvidenceValue<...>; ... };
  shotExploration: ShotEvidence[];         // 每条含 rallyId + ordinalInRally
  trajectories:   EvidenceValue<EstimatedBallTrajectory[]>;
  insights:       { findings; recommendations; coachNotes;
                    thirdShot: EvidenceValue<{numerator;denominator;...} | null>; ... };
}
```

**IO 与纯转换分离**（避免 adapter 变成一个自己 fetch 一切的 VisionPage）：

```ts
interface PlayerReportEvidenceSources {
  report: AnalysisReport;
  roster?: GlobalPlayerRosterArtifact;
  serveEvents?: ServeEventsArtifact;
  ballTrajectory?: BallTrajectoryArtifact;
  reconstructedTrajectory?: ReconstructedBallTrajectoryArtifact;
  bounceEvents?: BounceEventsArtifact;
  visualization?: StructuredVisualizationData;
}

// 纯函数：sources → evidence，可单测
buildPlayerReportEvidence(sources: PlayerReportEvidenceSources, playerId: string): PlayerReportEvidence;

// IO：加载 artifact / 缓存 / 错误 / 取消 / 组装 sources → 调纯函数
usePlayerReportEvidence(jobId: string | null, report: AnalysisReport, playerId: string): PlayerReportEvidence;
```

**三层边界**：`Hook = IO`，`buildPlayerReportEvidence = pure transformation`，`PB Components = presentation`。

UI 消费统一风格：

```tsx
if (ballSpeedMph.status === "available") return <Metric value={ballSpeedMph.value} provenance={...} />;
return <Unavailable reason={ballSpeedMph.reason} />;
```

**为什么单独成层 + 强类型**：避免"修完一个 mock 明天另一组件又 fallback"；provenance/reason 让 invariant #5 机器可验证。

### D3. 第三拍 ordinal contract（先 spike 再编码）
正式定义 `ShotEvidence { rallyId; ordinalInRally; ... }`，语义 `1=发球 2=接发 3=第三拍 4=第四拍 5+=后段`。

**不允许 PB 组件根据数组顺序 `i + 1` 推断。** 实施顺序：

1. 定义 `ShotEvidence` contract（见 5.1）。
2. **Contract spike**，逐项核 authority：
   - rally boundary authority（一段拍序归属哪回合）
   - hit event authority（谁定义一次击球）
   - ordering timestamp（排序时间来源/时钟）
   - duplicate / missing hit（漏检、重复检测的处理）
   - player ownership（击球归属谁）
   - multiview vs single-view（双摄合并 vs 单摄）
3. 拍板：方案 A adapter-derived ordinal（`groupBy(rallyId) + sortBy(timestamp) + index`）是否可信；不可信则方案 B 后端/artifact 带 `ordinal_in_rally`。
4. 实施。
5. PB filters（阶段）改消费 `ordinalInRally`。

**拍板（已裁决）——方案 A，带 authority gate**：由证据层 `buildShotExploration` 按 `rally_id` 聚合、以行序（视为时间序）赋确定性 `ordinalInRally`；源里**无 `rally_id`（无法判 rally 边界）→ ordinal 一律 `null`**，此时阶段筛选显示"暂不可按阶段筛选"，绝不 `i+1` 伪造。若未来发现行序不可靠（漏检/重复/跨 rally 错连实际发生）再升级为方案 B（后端带 `ordinal_in_rally`）。

**为什么先 spike**："第三拍"是强比赛语义；若 hit event 有漏检/重复/跨 rally 错连，纯 sort+index 算得出一个数字却不一定是可靠拍序。

### D4. source 分流（fail-closed）
以 `AnalysisReport.source` 为准，**白名单判 demo**：

```ts
const isDemo = report.source === "demo";        // 只有显式 demo 才允许 mock
const evidenceOnly = !isDemo;                    // job / undefined / unknown → evidence-only
```

- `demo`：允许代表性演示数据（独立 Demo Adapter/Provider），页面显式标注"演示数据"；mock 只在该 provider 内存在。
- 其他（`job / undefined / unknown`）：evidence-only，缺什么显示 unavailable。

**为什么 fail-closed**：历史报告若 `source` 缺失或未知，不能因缺字段误入 mock。

### D5. Skill Rating 降级（fail-closed）
- 正式模型必须带 `player-skill-rating.v1` schema + `modelVersion`。
- 在正式 artifact/schema 出现前，job 模式一律不显示 PB 式 2.0~5.5 评分；模块改名"本场表现概览"或显示"技能评分模型尚未生成"。
- **不能把现有 `skillRatings.length === 6` 当作正式模型**（那是旧评分）。
- 移除 `LABEL_TO_DIM` 失配后"顺序硬塞 + 归一化 + 2.0~5.5 映射"整条路径。
- 正式六维模型留待 `introduce-player-skill-rating-model`。

### D6. 去掉 fake 身份与伪统计
- Coach 卡：去掉"匹克球认证教练 · 8 年经验"，改"AI 训练洞察 · 基于本场可观测指标生成"；结论来源仅限 `performanceInsights.findings / recommendations` 和真实人工 `coachNotes`；无则"当前数据不足以生成可靠训练建议"。
- LegalThirds：有 numerator/denominator →"第三拍成功率 78% · 25/32"；只有 recommendation →"第三拍训练建议"；都无 →"本次分析暂无第三拍统计"。不再把无比例的情况叫"合法第三拍率"。

### D7. Serve/Return authority audit（P0 scope gate）
`ServeEventsArtifact` 只支持"发球开始"。逐指标按"系统能证明什么就展示什么"：

| 指标 | 依据 | 现阶段 |
|---|---|---|
| 发球次数 | ServeEventsArtifact | available |
| 发球者 | ServeEventCandidate.player_id | available |
| 发球起点 | ServeEventCandidate.court_position | available（若映射得通） |
| 发球 In/Out | 需 rally + first bounce / landing evidence | 先 unavailable，待 audit |
| 发球深度 | landing coordinate + court-zone 分类 | 先 unavailable，待 audit |
| 接发事件 | rally 内 ordinal=2 的 hit evidence | 关联 D3 spike 后定 |
| 接发 In/Out | return hit → landing/result evidence | 待 audit |
| 接发深度 | return landing + court-zone 分类 | 待 audit |

不可证明的指标绝不硬接，宁可显示 "发球进区率：暂未生成"。

### D8. 3D Court 接线（属 D2 数据源之一）
`Pb3DCourtCard` 停止从轻量 `shotTrajectories` 构造空 `points: []`，改为消费正式球路 artifact：

```
PlayerReportEvidenceSources.ballTrajectory / reconstructedTrajectory / bounceEvents
   → hit / bounce / segment evidence
   → 按 selectedPlayerId + filter 筛选
   → BallTrajectoryScene
```

轨迹由 IO hook 加载进 `sources`，纯转换筛出，这基本是接线而非重写 Three.js。

## Mock 清理清单（job 源必清）

| 位置 | 现行为 | 新契约 |
|---|---|---|
| `PbPlayerHeaderCard` 球速/拍速 | `stableHash01` 造 35/27 mph | `EvidenceValue`；无则"暂未生成" |
| `mockInPercent` | 造 0.85~0.95 | 移到 Demo Adapter |
| `mockSpeedPercentile` | 造 60~90 百分位 | 移到 Demo Adapter |
| `mockServeReturnStats` / `mockServeReturnDepth` | 造 100%/89%/深度分布 | 按 D7 authority 逐指标；能证明的展示，其余 unavailable |
| `PbCourtCoverage getDistanceFt` | `return 727` | 无真实距离 → "暂无移动距离数据" |
| `PbCoachInsight` | 默认建议 + 假教练 | evidence-driven |
| `PbLegalThirds` | 文本搜"第三拍" + 默认建议 | 有 ratio 显示比例，否则降级标题 |
| `PbSkillRatingSection` | 顺序兜底 + 2.0~5.5 | 仅正式模型（`player-skill-rating.v1`）展示，否则改名 |
| 全局身份 `global_player_N` | （未见现成，防患） | 仅经 `global-player-roster.v1` 映射；无 → unavailable |

## Risks / Trade-offs

- **[Risk] 竞赛评审需要"看起来有数据"的 demo 展示，evidence-only 会让 demo 报告变空**
  → Mitigation：D4 demo/job 分流保住了 demo 的代表性数据并加"演示数据"标注；评审演示走 `demo` 源。
- **[Risk] 真实/旧 job 报告很多模块变 unavailable，短时间观感倒退**
  → 这是"正确 > 好看"的取舍；空态做清晰、克制（带 reason）。
- **[Risk] 组件残留自己 fallback 的历史代码** → D2 强类型 + 架构测试锁定（pb-vizion 不得 import mock/DemoAdapter，除 demo 入口）。
- **[Risk] `global_player_N` 误按尾号归一化成 `Player_N`** → invariant #6 + `resolveGlobalPlayerId` 只有 roster 一条路，缺映射返回 unavailable；配单测。
- **[Risk] Serve/Return / 第三拍 认真接但接出语义不真实数据** → D7 / D3 先 audit/spike，核不清就不展示。
- **[Risk] 3D 轨迹 artifact 与 selectedPlayerId 对齐（单摄/双摄、legacy id）对不上** → 全局身份经 roster 解析后再筛选，未命中显示空态而非伪造。

## Migration Plan

1. 建 `EvidenceValue<T>` + `PlayerReportEvidenceSources` + `buildPlayerReportEvidence`（纯）+ `usePlayerReportEvidence`（IO）+ 全局身份解析工具，并写 `job-no-mock` 架构测试骨架。
2. `PbReportContext` 收口 player-only + canonical id + 全局身份解析。
3. Serve/Return authority audit（D7）+ 第三拍 contract spike（D3）先行，产出待办/契约影响。
4. 拆分 Demo Adapter / Provider，迁移 `pbMockData.ts` 函数并加"演示数据"标注。
5. 逐组件由 mock 切到 evidence adapter（header / court / serves-returns / skill / coach / legalThirds），3D Court 接正式轨迹 artifact。
6. Skill Rating 降级 + Coach / LegalThirds evidence-driven。
7. 自动测试补齐（见 tasks 8）+ `npm run lint` + `npm run typecheck` + Library 报告视图与 legacy 路由回归。

## Open Questions

1. ~~第三拍 ordinal（方案 A vs B）~~ → **已裁决：方案 A + authority gate**（见 D3）。若真实数据出现漏检/重复/跨 rally 错连，再升 B（后端带 `ordinal_in_rally`）。
2. **Serve/Return 权威来源**：已确认 serve_events 只证明发球开始/发球者/发球起点；In/Out、深度、接发需要额外 landing/bounce/return 权威（D7 矩阵），当前一律保守 unavailable。**待有对应 artifact 的接口/契约后接线**。
3. **demo 默认路由**：评审演示走 `demo` 源（代表性数据+标注）还是看真实 job 原始空态（影响 D4 默认路由）。
4. **全局身份映射来源面**：报告页是直接拿当前 `report` 内嵌 roster，还是根据 `primaryAnalysisJobId` 去拉 `global-player-roster.v1` 独立 artifact（影响 D1/IO hook 组装）。
5. **Player Selector 形态**：`P1..P4` chip 还是下拉（只做最小可用，不做 PB 视觉优化）。