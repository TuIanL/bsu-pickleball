## Context

发球候选导航条（`ServeRallyStrip`）于 2026-06-03 引入（提交 `a430464`），用于替代拥挤的进度条 marker：把发球时刻候选渲染为播放器下方可点击的横向卡片。当前 `visual-analysis-workspace` 主规格里共有 4 条与之相关的 requirement：

- `真实视频发球开始 marker`（要求工作台 SHALL 显示导航条，含跳转/滚动/高亮/时长保护/信号摘要场景）
- `发球事件加载和降级状态`（要求发球 artifact 作为独立数据层加载）
- `发球候选导航条加载和降级状态`（整体只描述导航条的加载与降级）
- `发球 marker 来源清晰`（要求文案不得把候选说成完整回合切分）

2026-09-23 双摄 joint 链路新增 `_publish_joint_serve_candidates()`（`backend/app/services/multiview_joint_executor.py:74`，调用点 `:1161`）后，双摄任务首次产出 `serve_events.json` 与 `serve_events_url`，导航条因此在双摄任务中重新出现（44 个候选、`status=partial`）。而这些候选是 tracking-only 的降级信号，放在播放器下方作为主视觉引导会强化"已确认发球"的错误印象，与本项目的诚实展示原则冲突。前端已有同类开关约定：`src/config/featureFlags.ts` 的 `kitchenArrivalCardEnabled`（`envFlag`，默认 `true`）。

## Goals / Non-Goals

**Goals:**
- 默认隐藏发球候选导航条与播放器内的"发球候选：N 个候选"计数文案。
- 保留发球候选的计算、`serve_events.json` 产物与 `serve_events_url/status/detail` 字段。
- 保留 `ServeRallyStrip` 组件与 `resolveServeMarkers` 解析函数及其单测，便于日后恢复。
- 提供可逆开关（`VITE_SERVE_RALLY_STRIP_ENABLED`），恢复展示无需重算产物。
- 让规格与实现重新自洽：收窄 1 条 requirement，移除 1 条只服务于导航条的 requirement。

**Non-Goals:**
- 不改后端、产物 schema、artifact API、数据库与调度。
- 不删除发球候选检测（含 joint 链路的 tracking-only 候选）。
- 不改变评分校准工作台（`ScoringCalibrationWorkbenchPage`）中其它发球相关 UI。
- 不改变播放器内"弹跳候选"文案行与弹跳/球路展示。
- 不做"确认发球"语义升级（无骨架时仍只发布候选）。

## Decisions

**D1｜用前端 feature flag 控制渲染，而不是删除渲染代码。**
新增 `serveRallyStripEnabled = envFlag(import.meta.env.VITE_SERVE_RALLY_STRIP_ENABLED, false)`，与既有 `kitchenArrivalCardEnabled` 同构：默认关闭即隐藏，置 `true` 可恢复。
考虑过的替代方案：① 直接删除 JSX 与其测试（不可逆、以后要恢复得重写）；② 后端不再发布 `serve_events`（会让"保留检测与产物"的决策落空，并影响后续评分校准与检测评估）。

**D2｜门控点放在 `RealVideoOverlay` 内的两处渲染，而不是 VisionPage 的 `shouldLoadServeEvents`。**
`ServeRallyStrip` 只在 `loadState === "idle"` 时返回 `null`；而 `VisionPage` 在无产物时传的是 `"unavailable"`，因此改 `shouldLoadServeEvents` 并不能真正隐藏组件。放在渲染处门控还能保留 `overlayRows` 里「发球候选」这一行的产物状态展示，使"产物仍在"对操作者可解释。

**D3｜规格侧同时使用 MODIFIED 与 REMOVED。**
`真实视频发球开始 marker` 改为"MAY 提供、默认不展示，受前端开关控制"（保留候选语义与不得冒充确认发球的约束）；`发球候选导航条加载和降级状态` 整体移除，因为它只描述导航条的加载/降级，默认不展示后没有承载对象——若仅改成"MAY"，会留下一条永远不生效的要求。
考虑过的替代方案：只改 MODIFIED、保留另一条不动（规格与实现继续不一致，正是本次要消除的问题）。

**D4｜`发球事件加载和降级状态` 与 `发球 marker 来源清晰` 保持原文不改。**
前者约束的是 artifact 作为独立数据层加载，产物仍在、契约不变；后者约束文案口径，与是否展示导航条无关。

## Risks / Trade-offs

- [导航条长期无人使用后与产物脱节] → 开关注释与规格中写明恢复方式与产物用途（评分校准、检测能力评估）。
- [`REMOVED` / `MODIFIED` 标题与主规格不逐字一致会让 `openspec archive` 原子中止] → 归档前逐字比对 requirement 标题；CLI 失败不写任何文件，可直接修正后重试。
- [外部评审误判"发球检测已被移除"] → proposal 与 design 的 Non-Goals 明确保留检测与产物；`serve_events.json` 继续生成，`overlayRows` 仍显示发球候选层状态。
- [默认隐藏导致相关回归不被发现] → 组件与解析函数单测保留并在 CI 中继续执行。
