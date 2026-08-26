## Context

报告页通过 `PbReportContext` 保存 `selectedPlayerId`，球员抽屉切换后，`Pb3DCourtCard` 会重新渲染。3D 球路的主数据来自 reconstructed trajectory artifact；每个 segment 可能包含 `shot_id`、`hitter_player_id`、`ownership_status` 和质量字段。

当前卡片已经尝试在组件内按 `hitterPlayerId` 筛选，但逻辑会保留击球者为空的轨迹，并随后把保留下来的轨迹全部改写成当前球员。这会把未归属球路混入个人视图，也破坏 artifact 的归属证据。项目已有 `buildShots`、`filterTrajectories` 和 canonical player identity 工具，可复用其 Shot 聚合与身份语义。

## Goals / Non-Goals

**Goals:**

- 选择球员后，3D 球路只展示该球员已确认击打的 Shot。
- 同一 Shot 包含多个 segment 时，保留该 Shot 的全部 segment，并保持各 segment 独立渲染。
- 未归属、击球者不明、无 Shot 上下文或无法解析身份的轨迹不进入任何球员个人视图。
- 保留 artifact 原始归属字段，不在视图层伪造或覆盖击球者。
- 让显示数量、空态和 Shot 级统计与筛选结果一致，并用自动化测试锁定行为。

**Non-Goals:**

- 不修改后端击球归属算法、reconstructed trajectory artifact schema 或 `Player_N` 身份协议。
- 不新增 API、数据库表、持久化筛选状态或报告页之外的全局筛选功能。
- 不改变“全部轨迹”和“未归属”模式的既有语义；本变更只修正报告页球员选择后的个人视图。
- 不重新计算轨迹、补点、平滑轨迹或改变 Three.js 渲染样式。

## Decisions

### 1. 以 Shot 作为球员筛选的归属单位

先用现有 `buildShots` 按 `shot_id` 聚合源轨迹，再筛选 `hitter_player_id` 与当前 canonical player 相同且 `ownership_status === "confirmed"` 的 Shot，最后将这些 Shot 的全部 segment 传入现有质量与阶段筛选流程。

这样可以满足“同一 Shot 的多个 segment 一起显示”，也避免只筛某个 segment 导致一个 Shot 的球路被截断。选择 Shot 级筛选而不是简单逐 segment 筛选，是因为 `shot_id` 才是产品统计和点击高亮的业务单位。

备选方案是只在 `Pb3DCourtCard` 中对每个 segment 做 `hitterPlayerId` 比较。该方案改动较小，但无法保证多 segment Shot 的完整性，也容易让组件绕过已有 Shot 级语义，因此不采用。

### 2. 严格使用 canonical 身份并对未知归属 fail-closed

使用 `resolveCanonicalPlayerId` 归一化选择值和轨迹值。当前端无法解析选择球员，或某个 segment/Shot 没有可确认的 `hitter_player_id` 时，个人视图不把它当作当前球员；必要时显示“当前筛选下没有可显示的球路”。

不再使用“未知归属也保留”的保守逻辑，也不再通过映射覆盖 `hitterPlayerId`。未归属数据仍可由全局/未归属视图使用，但不能进入任一球员统计。

### 3. 将筛选逻辑收敛到可测试的纯函数

在 `src/services/ballTrajectoryVisualization.ts` 中复用或扩展现有纯筛选函数，使球员归属筛选、Shot 聚合和未归属排除可以脱离 React 单测。`Pb3DCourtCard` 只负责组合 artifact、当前球员、阶段筛选和质量阈值，并把最终轨迹交给 `BallTrajectoryScene`。

组件不再通过 `.map((t) => ({ ...t, hitterPlayerId: playerCanonical }))` 改写 view model。显示数量从最终筛选结果派生；Shot 级数量从最终轨迹重新 `buildShots` 后按 `shot_id` 去重。

### 4. 保持现有筛选顺序和交互状态

球员归属筛选先于质量筛选和数量限制；阶段筛选继续使用 canonical shot evidence 的 `shot_id` 集合。切换球员时清理或校验当前选中的 `selectedShotId`，避免选中一个不再可见的 Shot，但不重置相机视角和其他筛选控件。

### 5. 用行为测试覆盖报告页回归

测试至少覆盖：

- Player_1 / Player_2 / null 混合轨迹中选择 Player_1 时只显示 Player_1 的 Shot；
- 同一 Shot 的多个 segment 会全部保留；
- `ambiguous`、`unassigned`、`shot_id = null` 不进入个人球员视图；
- 切换选择球员后结果随 `selectedPlayerId` 更新；
- 没有匹配球路时显示空态，且不会把整场轨迹传给场景；
- 显示数量和 Shot 级统计只来自筛选结果。

## Risks / Trade-offs

- [旧 artifact 缺少归属字段时个人视图可能为空] → 明确显示当前筛选下无可用球路，并保留全局/诊断入口；禁止静默把整场球路当成某一球员数据。
- [部分 Shot 归属为 ambiguous 会减少个人视图样本] → 个人报告只使用 confirmed 归属，保留 ambiguous 数据在未归属视图和 artifact 中供审计。
- [阶段筛选与球员筛选组合后结果更少] → 继续显示现有空态，并在测试中分别验证球员筛选和阶段筛选，避免把空结果误认为 WebGL 或数据加载失败。
- [现有测试 fixture 未提供 hitter 字段] → 更新 fixture 为显式 ownership 数据，并新增 null/ambiguous 场景，避免测试继续默许错误的全量回退。

## Migration Plan

这是纯前端行为修复，无需数据迁移或 API 版本升级。实现后运行球路 view model、报告 3D 卡片和 TypeScript 构建测试；若需要回滚，只需回退本 change 的前端提交，后端 artifact 保持兼容。

## Open Questions

- 当前需求按“已确认击球”处理 ambiguous 归属；若产品希望把“唯一候选但未确认”的球路也显示给球员，需要单独定义候选标识和视觉提示，不应在本次修复中隐式放宽。
- 卡片顶部数量继续展示“可见 segment 数量”，而 Shot 级击球数按 `shot_id` 去重；若要把顶部文案改为“Shot 数量”，应另行确认 UI 文案范围。
