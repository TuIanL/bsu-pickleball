# Tasks: reframe-library-and-match-workspace

## 1. P0 — 契约冻结与后端只读 catalog

- [x] 1.1 新增只读 `GET /api/videos` catalog：枚举现有 VideoMetadata，返回视频列表基础字段（无新表、无新实体）
- [x] 1.2 为只读 catalog 补充测试：返回全部独立上传视频、空列表稳定、不可写（POST 仍走 upload 接口）
- [x] 1.3 定义 `libraryAdapter.ts` 中的 `LibraryItemRef` typed union（upload/recording/sync_recording + sourceId）
- [x] 1.4 定义三轴状态类型 `mediaState / availabilityState / analysisState` 与 `requiredAction`，写入 `libraryAdapter` 类型声明
- [x] 1.5 定义 Primary Analysis Selection 契约（D9）：`primaryAnalysisJobId` + `analysisHistoryCount` 选择规则（双摄取 multiview Parent、A/B 不顶替、internal child 不参与）
- [x] 1.6 实现 upload 映射：读 `GET /api/videos` 构建 upload LibraryItem，而非从 `listAnalysisJobs` 反推
- [x] 1.7 实现 recording 映射：`recordingSessionId==sourceId` 归属 single-view primary
- [x] 1.8 实现 sync_recording 映射：`recordingSessionId` 为 canonical，`capture_take_id` 仅 legacy fallback，禁用 fileName/title 模糊匹配
- [x] 1.9 source-specific 状态映射表：merge pending→processing+merge_required、merge running→processing+none、availability 透传（存储暂不可用≠failed）
- [x] 1.10 资产所有权契约验收：删 AnalysisJob 不删 Library source video（upload/recording/sync 三路径）

## 2. P1 — 比赛库 Library 页面

- [x] 2.1 新增 `src/pages/LibraryPage.tsx`，基于 `libraryAdapter` 聚合三类素材为统一卡片
- [x] 2.2 新增 `src/services/libraryAdapter.ts`，把 backend 对象聚合成 `LibraryItemViewModel`
- [x] 2.3 新增 `src/components/library/*` 卡片组件：缩略图/标题/时间/机位与比赛形式/三轴状态/`primaryAnalysisJobId`
- [x] 2.4 实现搜索 / 过滤（全部/正在分析/已完成/失败/上传/录制/双摄）/ 排序 /「最近比赛」
- [x] 2.5 FieldSession 作为 Collection/Folder 分组（LibraryGrid 按场次分组；`engineering` 默认不进入普通列表）
- [x] 2.6 卡片生命周期显示：`requiredAction` 触发「合并视频/重新合并/开始分析」等操作，而非仅「处理中」
- [x] 2.7 卡片 ··· 菜单：重命名/加入场次/重新分析/查看原视频/下载/分享/查看技术信息/删除（源视频删除为显式独立动作）
- [x] 2.8 新增 Library route：`/library`、`/library/{kind}/{sourceId}?view=...` 纯函数解析 + 非法参数安全回退

## 3. P2 — LibraryItemWorkspace

- [x] 3.1 新增 `library-item-workspace` 外壳：`/library/{kind}/{sourceId}` 下显示素材上下文标题（比赛/训练/采集详情）
- [x] 3.2 workspace 一级 Tab（概览/视频/数据分析/球路/报告/片段/技术详情）与 `?view=` 绑定
- [x] 3.3 view 历史语义：Library→Workspace 用 push，view 切换用 replace（含 `?view=video&t=` 证据跳转）
- [x] 3.4 依据状态门控 view：素材未分析时数据分析/球路/报告不可用；`?view` 深链无成功 primary 时落到 stable fallback，不空白页
- [x] 3.5 将 Vision 内容抽为 workspace「数据分析」view 的 content component（保留 visual-analysis-workspace 行为契约）
- [x] 3.6 将 Report 内容抽为「报告」view 组件，复用 PB 风格视觉组件、剔除报告独立抽屉与 real-job mock
- [x] 3.7 将 BallTrajectory 抽为「球路」view 组件
- [x] 3.8 将 SegmentManager / RecordingWorkspace 分别抽为「片段」「视频」view 组件
- [x] 3.9 将 MultiviewObservability / AnalysisDetails / AnalysisJob 状态抽为「技术详情 / 概览」view（工程可见性）
- [x] 3.10 上传+创建分析成功落点改为 `/library/upload/{videoId}?view=analysis`；采集 durable 后进入对应 LibraryItem（落点逻辑随 workspace 路由就绪；详情见 design D15）

## 4. P3 — 导航收敛与旧路由迁移

- [x] 4.1 新 Sidebar：一级导航收敛为「比赛库→`/library` / 现场采集→`/capture` / 设备管理→`/camera`」，活跃高亮保留，录制状态块保留
- [x] 4.2 `/workspace` canonical redirect 到 `/library`（replaceState），移除「建设中」占位主导航
- [x] 4.3 `AnalysisTasksPage` 原地降级为 Engineering Console：保留 Job-centric 能力，`/analysis/tasks` canonical + `/tasks` alias，不出现在一级导航
- [x] 4.5 报告中心 `reports/:type` 收敛到 workspace「报告」view；旧入口兼容回退（报告中心退出主导航，旧 route 仍可用）
- [x] 4.6 旧 route 兼容保留（`/analysis/tasks`、`/tasks`、`/reports/:type`、`?legacy=1`）回到原入口正常渲染

不在本次范围内（后续 Change 收尾，design 已标注迁移期保留）：
- LegacyLibraryRouteResolver：旧 `/analysis/{job}/vision` 等旧 route 异步加载 job→解析 LibraryItemRef→replace 到 `/library/...`（当前旧 sibling RouteState 保留直渲，兼容不破坏）
- 清理：确认全部 sibling RouteState 迁移完成后删除旧 state（须待 resolver 与 view 迁移完成后再删）

## 5. 回归与验收

- [x] 5.1 跑既有分析任务删除/取消/批量/阶段进度测试，确认 Engineering Console 语义不回归（440 前端测试全绿）
- [x] 5.2 跑 ownership 契约测试（upload/recording/sync_recording 三条映射 + primary 选择）
- [x] 5.3 TypeScript + Vite build + 单测通过