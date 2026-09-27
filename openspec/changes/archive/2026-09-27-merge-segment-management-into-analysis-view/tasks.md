# Tasks: merge-segment-management-into-analysis-view

## 1. 时间轴映射验证门槛（design D2，最先执行）

- [x] 1.1 选取含正式切分结果的真实双摄 take + 对应分析 job（从 backend/data/outputs 或外接盘 captures 目录确认素材可用），记录素材 ID 到本 change 目录
- [x] 1.2 写临时验证脚本/测试：取某回合 `effective_start_ms`，经 `sourceTimeToCanonicalTimeMs`/恒等映射对照 canonical 播放头，确认回合毫秒与 canonical 轴一致（画面内容与回合对应，无系统性偏移）；验证通过才允许后续任务使用 D2 判定，失败则停止并回到 design 修订映射方案

## 2. auto-skip 状态机抽取（design D1）

- [x] 2.1 新建 `src/hooks/useAutoRallyPlayback.ts`：从 `SegmentManagerPage.tsx` 迁移 `autoRallySegments` 构建口径（已发布 run 的 active algorithm rally、`effective_*` 缺省链、按 startMs 排序）、`resolveAutoRallyWindow`（左闭右开、终点缺省 `max(durationMs, startMs+500)`、续播按「起点不早于窗口结束」选取）、`autoSkipEnabled`（默认开启不持久化）与 `autoSkipUnavailableReason`
- [x] 2.2 为 hook 写纯时间轴单测：回合内起播、回合前/间隙起播、末回合后起播保持暂停、播完续播、末段播完停止、拖动/逐帧中断不续播、终点缺省兜底（含 durationMs 未知分支）
- [x] 2.3 从 `SegmentVideoPlayer.tsx` 抽出中央回合提示组件 `RallyCueOverlay`（含提示合并/约 2 秒淡出/最小静默间隔/user 导航不受节流状态机，输入为 `activeRally.cause`），带单测

## 3. VideoAnalysisCard 接入 auto-skip 与提示（design D6）

- [x] 3.1 `VideoAnalysisCard` 新增可选 props（`autoRallySegments`、`autoSkip` 控制、`onPlaybackToggle` 语义等），未传入时渲染与交互零变化（对应 auto-rally-playback-cues「未传入自动回合数据」场景）
- [x] 3.2 自绘进度条增加回合色带层：区间/非区间两色、当前回合高亮、按媒体总时长归一化、越界裁剪与退化区间丢弃、时长不可用不着色、保留已播放读数与拖动定位
- [x] 3.3 挂载 `RallyCueOverlay` 到视频舞台层（pointer-events 穿透、高对比文字、暂停/定位同样触发、离开回合重置）
- [x] 3.4 接线 `useAutoRallyPlayback`：起播解析窗口、播完自动续播、末段停止；round-trip 用 2.2 的单测口径在组件层复验

## 4. 片段面板与右栏（design D3/D4）

- [x] 4.1 新建 `src/components/platform/AnalysisSegmentPanel.tsx`：筛选 pills（全部/盘/局/分）、自动切分摘要（状态徽标/模型版本/生成时间/回合数）、模型回合只读列表、人工标记列表；行结构复刻原 `ReadOnlyModelSegmentRow` 与人工行
- [x] 4.2 面板数据加载：`getCaptureTake`（经 `job.metadata.capture_take_id` 反查）/`listSegments`/`getFormalSegmentationSummary` 各自独立 try/catch 兜底；无 `capture_take_id` 时显示降级占位
- [x] 4.3 面板与播放器联动：点击回合行 → canonical→source 换算 seek + 自动起播（cause=user 触发中央提示）；播放头驱动列表高亮；只读（不发 PATCH/复核请求）
- [x] 4.4 重构 `AnalysisStatusRail`：任务状态卡与视觉层状态收进主画面卡头部 ⓘ 图标弹层（内容不裁剪、开关弹层不改变播放状态）；下级报告入口迁为片段面板底部独立卡片；原 380px 右栏槽位交给 `AnalysisSegmentPanel`
- [x] 4.5 `VisionPage`（embedded 与独立路由两种形态）接线新右栏，确认窄视口下面板堆叠在视频下方不遮挡控件

## 5. 删除与路由收口（design D5）

- [x] 5.1 删除 `SegmentManagerPage.tsx` + `SegmentManagerPage.test.tsx`、`SegmentVideoPlayer.tsx` + 测试、`EditableSegmentTimeline.tsx` + 测试
- [x] 5.2 路由收口：删除 `segmentManager` route（router.ts/navigationTypes.ts/AppRouter.tsx），为 `/capture/:fs/takes/:take/segments` 保留 redirect 到素材 workspace `analysis` view（丢弃 `?mode=boundary-review`）；更新 `router.test.ts`
- [x] 5.3 Library 工作区：`viewCapabilities.ts` 删除 `segments` capability、`LibraryItemWorkspace` 删除「片段」tab 与 `SegmentManagerView` lazy import、`LibraryView` 类型删去 `"segments"`；更新 `viewCapabilities.test.ts` 与 `LibraryItemWorkspace.test.tsx`
- [x] 5.4 清理前端 service：删除仅被 QA/编辑消费的函数（`getBoundaryReview`、`getMatchStateCandidates`、`decideMatchStateCandidate`、`reviewSegmentBoundary`、`renumberRallyOrdinals`、`createRallySegment`、`splitSegment`、`mergeSegments`、`patchSegment`、`archiveSegment`、`restoreSegment`）及仅其使用的类型；保留 `listSegments`/`getFormalSegmentationSummary`/`getCaptureTake`/`listTimelineEvents`/`getVideoStreamUrl`
- [x] 5.5 全仓扫尾：搜索 `SegmentManager|SegmentVideoPlayer|EditableSegmentTimeline|boundary-review|reviewQueue` 等残留引用并清零

## 6. 验收

- [x] 6.1 用 1.1 的真实素材人工验收：数据分析页 auto-skip 连播（含续播/末段停止/开关关闭行为）、回合定位落点正确（无时间偏移）、中央提示与色带表现、ⓘ 弹层信息完整、旧片段页 URL redirect 生效
- [x] 6.2 前端全量测试通过（`--maxWorkers=2`），既有基线失败（`MultiViewAnalysisSetupPage` 3 例）保持只报告不修；eslint 与 HEAD 版对比无新增 error（`SegmentManagerPage` 既有 14 条 no-unused-vars 随删除消失）
- [x] 6.3 对照 specs delta 逐条核对场景（auto-skip 开关/续播/弱约束/提示合并、面板联动、降级路径、映射契约、StatusRail 折叠）
