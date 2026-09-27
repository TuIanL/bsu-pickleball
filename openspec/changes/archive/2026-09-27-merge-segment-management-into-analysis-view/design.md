# Design: merge-segment-management-into-analysis-view

## Context

片段管理页（`SegmentManagerPage.tsx`，1801 行）承载两类能力：① 生产浏览（只读回合列表 + auto-skip 回合连播）；② QA 复核（`?mode=boundary-review`，模型候选/人工边界/分序号编辑，约一半代码量）。数据分析页（`VisionPage.tsx` → `VideoAnalysisCard.tsx`，1796 行）承载视觉叠加播放（人物框/骨架/球/小地图/球场 HUD）。两页共享同一素材却互不感知。

已确认的产品决策（探索阶段拍板）：
1. 片段页普通模式右侧面板（筛选 pills + 自动切分摘要 + 模型回合列表 + 人工标记列表）整体迁入数据分析页右栏；
2. 数据分析页现有右栏信息（任务状态/视觉层状态）折叠成 info 图标弹层；
3. boundary-review QA 模式连同其前端流程全部删除（后端 API 保留，清理留独立 change）；
4. Library 工作区「片段」Tab 删除，8 个 view 收敛为 7 个。

关键既有不变量（迁移中必须原样保持，来源：归档 change `auto-skip-rally-playback`）：
- 回合窗口区间左闭右开 `[start, end)`；终点缺省 `endMs ?? max(durationMs, startMs + 500)`（不退成 `?? durationMs`）；
- 续播目标 = 「起点不早于当前窗口结束时间」的首个回合，不按数组下标递推；
- 末回合之后起播 → 保持暂停，不播尾部非比赛时间；
- 只有用户显式起播才解析窗口；拖动/逐帧不触发续播（弱约束）；
- auto-skip 开关默认开启、不持久化；
- `autoRallySegments` 以已发布 run 的 active algorithm rally 为唯一来源，不受列表筛选影响。

## Goals / Non-Goals

**Goals:**
- 数据分析页成为「带视觉叠加的回合连播」单一入口：auto-skip、回合色带、中央回合提示在 VideoAnalysisCard 上可用。
- 片段浏览（列表/摘要/筛选）成为数据分析页右栏面板，点击回合可定位主画面。
- 删除 SegmentManagerPage / SegmentVideoPlayer / EditableSegmentTimeline 与 QA 前端，收窄维护面。
- 回合毫秒轴 → 播放器时间轴的映射成为显式、可测试的单一契约。

**Non-Goals:**
- 后端任何行为变更（segment-editing 契约、boundary-review API、候选复核 API 全部保留原样）。
- VideoAnalysisCard 既有控件（全屏/静音/进度条/机位切换/court HUD）的行为重设计。
- 双摄双机位并排同步播放（QA 复核的形态）——数据分析页维持单 display view 播放。
- 片段边界的任何编辑能力（只读化是刻意的）。

## Decisions

### D1: auto-skip 状态机抽为共享 hook，而非在 VideoAnalysisCard 里重写

新 hook `useAutoRallyPlayback`（建议 `src/hooks/useAutoRallyPlayback.ts`），从 SegmentManagerPage 迁移并参数化：
- 输入：`autoRallySegments`（已按 startMs 排序的 `{id, ordinal, startMs, endMs|null}[]`）、`durationMs`、`isPlaying`、`playheadMs`、`requestSeek(ms)`、`requestPlay()`/`requestPause()`；
- 输出：`activeRally`（含 `cause: "user" | "autoAdvance"`）、`autoSkipEnabled`、`autoSkipUnavailableReason`、`resolveWindow(playheadMs)`、`handlePlaybackToggle()`；
- 既有不变量逐条保留（见 Context）；`resolveAutoRallyWindow` 的左闭右开与终点缺省逻辑原样搬运并带单测。

**理由**：逻辑在 SegmentManagerPage 是页面私有的（199-244、593-639 行），直接重写一遍必然漂移；抽取后 hook 可用纯时间轴单测覆盖（不需要渲染播放器），VideoAnalysisCard 只做接线。

### D2: 时间轴契约——回合毫秒 = canonical 轴，映射收在单一模块

**判定**：回合窗口毫秒（segment `start_ms`/`effective_*`）与 VideoAnalysisCard 的 canonical 播放头（`sourceTimeToCanonicalTimeMs(video.currentTime*1000, displayTimeMapping)`，VideoAnalysisCard.tsx:487）同轴。依据：切分 run 的 planning job 消费 multiview 管线，其时间轴是 canonical tick（双摄）；单摄 canonical 与源视频恒等（`offsetMs=0, rate=1`）。

**实现**：
- 回合命中判定直接用 canonical 播放头对比 `autoRallySegments` 区间；
- seek 用 `canonicalTimeToSourceTimeMs(rallyStartMs, displayTimeMapping)` 换算到目标视频时间（该函数已存在且带边界 clamp 语义）；
- 换算只允许出现在 `useAutoRallyPlayback` 接线层与面板点击定位处，禁止散落。

**验证门槛（apply 阶段第一个任务）**：取一个真实双摄 take（含正式切分结果 + 双摄分析 job），断言「回合 start_ms 落在 canonical 轴」：用回合区间内的 canonical 时间 seek 后，画面应处于回合内容中，而不是系统性偏移。若验证失败（轴不一致），不得上线该映射，改为在 `src/utils/segmentTimeAxis.ts` 集中实现显式换算并重跑验证。此风险已在 Risks 登记。

### D3: 片段面板 = 新组件 `AnalysisSegmentPanel`，job→take 反查走既有元数据

- 新组件 `src/components/platform/AnalysisSegmentPanel.tsx`，渲染原片段页普通模式右栏四块：筛选 pills（全部/盘/局/分）、自动切分摘要（状态徽标/模型版本/生成时间/回合数）、模型回合列表（`ReadOnlyModelSegmentRow` 行为）、人工标记列表。
- 数据加载沿用原 `loadData` 的独立兜底模式：take 详情、`listSegments`、`getFormalSegmentationSummary` 各自 try/catch，任一失败只降级对应块，不阻塞面板与页面。
- take 反查：`job.metadata.capture_take_id`（types/report.ts:553）。无 capture_take_id（上传视频 job）→ 面板显示「该素材无片段数据」占位，auto-skip 开关禁用（`autoSkipUnavailableReason = "该分析不关联采集片段"`）。
- 点击回合行 = 显式导航：seek 主画面到回合起点（canonical→source 换算）并自动开始播放（延续原「点击片段行自动起播」契约）；播放中点击 = 从新位置继续。`cause: "user"` 触发中央回合提示（不受节流，见 auto-rally-playback-cues）。
- 面板只读化：不含标签双击编辑（`patchSegment` 前端消费者随 QA 一并清理），列表行点击仅承担定位/起播。

### D4: StatusRail 折叠为 info 弹层，不删信息

- `AnalysisStatusRail` 重构：任务状态卡与视觉层状态（8 层）收进播放器卡头部的 ⓘ 图标弹层（复用「confidence 仅 info icon 暴露」的既有产品约定）；弹层内容即现有两卡内容，不做二次裁剪。
- 下级报告入口（分析详情/报告按钮）保留为常驻：安置在片段面板底部独立卡片（低频但属于导航，不应藏进弹层）。
- 原 380px 右栏槽位让给 `AnalysisSegmentPanel`。

### D5: 删除策略——旧 URL 重定向，不做死链

- `/capture/:fs/takes/:take/segments` 路由删除，但 router 中保留一条 redirect 到该 take 所属素材的 workspace `analysis` view（`buildLibraryWorkspacePath`）；`?mode=boundary-review` 参数被丢弃（QA 入口消失是刻意行为）。
- `LibraryView` 联合类型删去 `"segments"`；`viewCapabilities` 中 `segments` capability 与 `LibraryItemWorkspace` 的 tab/渲染分支同步删除。
- 仅被 QA 消费的前端 service 函数（`getBoundaryReview` / `getMatchStateCandidates` / `decideMatchStateCandidate` / `reviewSegmentBoundary` / `renumberRallyOrdinals` / `createRallySegment` / `splitSegment` / `mergeSegments` / `patchSegment` / `archiveSegment` / `restoreSegment`）及对应类型一并删除；`listSegments` / `getFormalSegmentationSummary` / `getCaptureTake` / `listTimelineEvents` 保留（新面板消费）。
- 后端 API 端点不动；`openspec/specs/segment-editing` 等后端契约 spec 不动。

### D6: 进度条回合色带与中央提示在 VideoAnalysisCard 落地

- VideoAnalysisCard 自绘进度条（已有 `progress` 计算，:604）增加回合色带层：渲染 `autoRallyBands`（与 SegmentVideoPlayer 的 band 渲染语义一致：区间块 + 当前回合高亮）；
- 中央回合大字提示组件从 SegmentVideoPlayer 抽出为 `RallyCueOverlay`（含提示合并/最小静默间隔/user 不受节流的状态机——即归档 change `auto-skip-rally-playback` 的提示契约），VideoAnalysisCard 挂在视频舞台层；
- 提示状态机以 `activeRally.cause` 为输入，逻辑不重写。

## Risks / Trade-offs

- **[D2 轴判定错误 → 跳转到错误时刻]** → apply 阶段首任务做真实双摄素材验证（见 D2 验证门槛）；映射集中在单一模块 + 单测锁定换算；验证失败则切换显式换算方案，不硬上。
- **[VideoAnalysisCard 复杂度叠加（1796 行 + auto-skip 接线）引入回归]** → auto-skip 逻辑全部收在 hook 与 `RallyCueOverlay`，VideoAnalysisCard 只接线；既有 VisionPage 测试（synchronized overlay playback 等）必须保持通过；前端全量测试加 `--maxWorkers=2`。
- **[删除 QA 复核是不可逆产品决策]** → proposal 已明示；后端 API 与数据保留，若日后需要复核流程可重建前端，但历史复核工作流（候选决策 UI）不可从本仓库恢复（git 历史除外）。
- **[上传视频 job 无 take → 片段面板空占位]** → 刻意的降级路径，占位文案明确说明原因；不影响数据分析其余能力。
- **[旧片段页深链失效]** → D5 redirect 兜底；`?mode=boundary-review` 深链 redirect 后落到只读分析 view（无复核功能，符合预期）。
- **[测试基线既有失败（MultiViewAnalysisSetupPage 3 例）]** → 沿用「既有失败只报告不修」约定，不混入本 change 的通过判定。

## Migration Plan

单 PR 顺序（见 tasks.md），无数据迁移、无后端部署依赖：
1. 先建新能力（hook + 面板 + 弹层 + VideoAnalysisCard 增强），旧页面共存期间新能力可用 `?` 参数或直接在 workspace 验证；
2. 删除旧页面/路由/tab/service，补 redirect；
3. 全量前端测试 + eslint 对比基线（SegmentManagerPage 既有 14 条 no-unused-vars 随文件消失）。

回滚：纯前端变更，revert 即回滚；无数据库/契约影响。

## Open Questions

（实现阶段解决，不阻塞 proposal/design/specs 定稿）
- Q1: D2 验证使用的具体素材 take/job 清单（需要含正式切分结果的双摄 take + 对应分析 job）——apply 阶段从 `backend/data/outputs` 或外接盘 captures 目录选取。
- Q2: 弹层组件选型——用现成的 popover 模式（仓库内已有 info icon 模式可参照，如 confidence 暴露）还是引 headless 组件；倾向前者（零新依赖）。
