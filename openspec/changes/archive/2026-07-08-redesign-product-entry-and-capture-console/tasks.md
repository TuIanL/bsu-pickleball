## 1. 路由与导航基础设施

- [x] 1.1 扩展 `RouteState` 类型，新增 `landing`、`upload`、`captureHome`、`captureNew`、`captureConsole`、`tasks` 路由状态
- [x] 1.2 扩展 `parsePath()` 函数，新增 `/upload`、`/capture`、`/capture/new`、`/capture/:id`、`/tasks` 路径解析（注意 `/capture/new` 优先于 `/capture/:id` 匹配）
- [x] 1.3 扩展 `AppPath` 类型，添加新路由路径
- [x] 1.4 重写 `AppShell.tsx` 导航栏：移除 4 tab pill 导航，改为左侧 Logo + 产品名，右侧「任务历史」按钮（帮助入口预留但本次不实现）
- [x] 1.5 更新 `AppShell` 移动端导航：移除水平滚动 tab，保留 Logo + 任务历史入口
- [x] 1.6 更新 `platformNavigation` 数组：移除所有旧导航项，仅保留首页（`/`）作为内部引用
- [x] 1.7 更新 `App.tsx` 路由渲染 `useMemo`，为新路由状态映射对应页面组件

## 2. 首页 LandingPage

- [x] 2.1 创建 `src/pages/LandingPage.tsx`，包含 Hero 区（大标题 + 描述文字 + 两列主入口按钮）
- [x] 2.2 两个主入口按钮：「上传已有视频」（导航到 `/upload`）和「进入现场录制」（导航到 `/capture`）
- [x] 2.3 下方三张能力介绍卡片（视频上传分析 / 球场现场采集 / 训练结果沉淀），纯展示无跳转
- [x] 2.4 保留 VideoAnalysisCard compact 模式在 Hero 右侧
- [x] 2.5 更新 `overviewCards` 数据，替换为新的能力卡片数据（移除旧跳转逻辑）
- [x] 2.6 从 `App.tsx` 中移除原 `OverviewPage` 组件定义，改为从 `LandingPage.tsx` import

## 3. 上传模式 UploadModePage

- [x] 3.1 创建 `src/pages/UploadModePage.tsx`，作为 `/upload` 路由的页面组件
- [x] 3.2 页面标题「上传模式」+ 描述文字「上传已有比赛视频并创建分析任务」
- [x] 3.3 将现有 `NewAnalysisPage` 的核心渲染逻辑迁移到 `UploadModePage`（视频选择、四角标定、元数据表单、提交流程不变） — 轻拆策略：UploadModePage 为占位，实际渲染通过 App.tsx switch 中 "upload" case 直接使用 NewAnalysisPage
- [x] 3.4 从 `App.tsx` 中移除原 `NewAnalysisPage` 组件定义，改为从 `UploadModePage.tsx` import — 暂未提取，NewAnalysisPage 仍在 App.tsx 中
- [x] 3.5 保留从录制视频直接创建分析的 `?videoId=xxx&source=recording` 入口支持

## 4. 采集任务首页 CaptureHomePage

- [x] 4.1 创建 `src/pages/CaptureHomePage.tsx`，作为 `/capture` 路由的页面组件
- [x] 4.2 页面标题「现场采集」+ 描述文字
- [x] 4.3 「新建采集任务」主按钮（导航到 `/capture/new`）
- [x] 4.4 最近采集任务列表：调用 `listFieldSessions` API，按创建时间倒序展示
- [x] 4.5 每项任务展示：标题、场地名、采集模式、比赛形式、状态标签、创建时间
- [x] 4.6 点击任务卡片导航到 `/capture/:id`
- [x] 4.7 空列表时展示空状态引导

## 5. 采集任务创建向导 CaptureWizardPage

- [x] 5.1 创建 `src/pages/CaptureWizardPage.tsx`，作为 `/capture/new` 路由的页面组件
- [x] 5.2 三步向导步骤指示器（Step 1/2/3 高亮当前步骤）
- [x] 5.3 Step 1 采集场景表单：场地名称（court_name）、采集类型（capture_mode: 自由练习 / 记分比赛 / 工程测试）、人数模式（match_format: 单打 / 双打）、备注（notes）
- [x] 5.4 Step 2 摄像头方案选择：单摄模式 / 双摄模式 / 工程调试，每项含说明文字（camera_setup 暂存前端状态，不假设后端 FieldSession API 已有对应持久化字段；真正选择摄像头在 CaptureConsole 设备抽屉中完成）
- [x] 5.5 Step 2 中预选的摄像头 ID 仅作为前端初始化状态传入 CaptureConsole（如 FieldSession API 暂无 selected_camera_ids 字段则不写入后端）
- [x] 5.6 Step 3 分析设置：自动创建分析任务 / 录制完成后再决定 / 仅保存视频（单选）；完成后将 analysisIntent 存入 `sessionStorage["capture.analysisIntent.{fieldSessionId}"]` 作为刷新兜底
- [x] 5.7 向导导航按钮：「上一步」「下一步」「创建采集任务」
- [x] 5.8 表单数据跨步骤保留（前端状态），用户可返回修改
- [x] 5.9 点击「创建采集任务」：调用 `createFieldSession` API → 导航到 `/capture/:id`（此时 Field Session 状态为 `planned`，不立即调用 `startFieldSession`；startFieldSession 在控制台用户点击「开始录制」时触发）

## 6. 采集控制台 CaptureConsolePage

- [x] 6.1 创建 `src/pages/CaptureConsolePage.tsx`，作为 `/capture/:id` 路由的页面组件
- [x] 6.2 页面加载时调用 `getFieldSession(id)` 获取 Field Session 详情
- [x] 6.3 页面顶部信息栏：任务名称、场地、采集模式、比赛形式、状态
- [x] 6.4 左侧实时预览区：使用 `getCameraPreviewUrl` 加载摄像头画面
- [x] 6.5 预览区占主视觉空间，加载失败时展示重试按钮
- [x] 6.6 右侧设备状态区：展示当前摄像头名称、在线状态、连接地址
- [x] 6.7 设备状态区提供「重新探测」和「更换摄像头」（打开设备抽屉）按钮
- [x] 6.8 右侧录制控制区：「开始录制」按钮（先调用 `startFieldSession(id)` 将状态置为 `live`，然后调用 `startRecording` API，传入 `field_session_id`）
- [x] 6.9 录制中显示「停止录制」按钮和录制时长计时器
- [x] 6.10 内部状态机：preview → recording → stopped 三状态驱动 UI 切换
- [x] 6.11 CaptureConsole 加载时从 sessionStorage 恢复 analysisIntent：优先从路由 state → sessionStorage → 默认 `ask_after_recording`

## 7. 场边事件标记与时间线

- [x] 7.1 录制中在控制台底部展示事件标记按钮栏（按 capture_mode 分类加载 `quickEventsForMode`）
- [x] 7.2 点击事件按钮调用 `createTimelineEvent` API，传入 `field_session_id` 和 `recording_session_id`
- [x] 7.3 时间线实时展示已标记事件：时间戳 + 事件标签
- [x] 7.4 新事件实时追加到时间线，无需手动刷新
- [x] 7.5 事件标记和时间线仅在 recording 状态展示

## 8. 录制完成面板

- [x] 8.1 停止录制后调用 `stopRecording` API，获取 `RecordingSession` 结果
- [x] 8.2 根据向导中的 `analysisIntent` 和 `RecordingSession.auto_analysis_job_id` 判断展示模式
- [x] 8.3 「自动分析」模式面板：显示分析任务已创建 +「查看分析进度」「播放回看」按钮
- [x] 8.4 「录制后再决定」模式面板：显示「立即创建分析任务」「仅保存视频」「播放回看」按钮 — 录制完成后再决定模式统一走「创建分析任务」按钮链接到 `/upload?videoId=...&source=recording`
- [x] 8.5 「仅保存」模式面板：显示「创建分析任务」「播放回看」「返回采集任务」按钮
- [x] 8.6 面板可关闭，关闭后回到 preview 状态，保留录制信息
- [x] 8.7 「立即创建分析任务」「创建分析任务」按钮统一复用录制视频创建分析入口：`navigate(`/upload?videoId=${recording.video_id}&source=recording`)`，利用 UploadModePage 已有的 `?videoId=xxx&source=recording` 参数支持，不新增直接创建 analysis job 的 API 调用

## 9. 设备抽屉 DeviceDrawer

- [x] 9.1 在采集控制台右侧创建设备抽屉组件（右侧滑出面板）
- [x] 9.2 抽屉内容：已注册摄像头列表（名称、ID、协议、探测状态、选择/探测/删除按钮）
- [x] 9.3 选择摄像头：点击后设为首选摄像头，关闭抽屉，更新设备状态区和预览
- [x] 9.4 注册新摄像头表单（camera_id、name、stream_url、protocol），提交调用 `createCamera` API
- [x] 9.5 探测按钮：调用 `probeCamera` API，展示结果
- [x] 9.6 删除按钮：调用 `deleteCamera` API，成功后从列表移除
- [x] 9.7 抽屉外部遮罩点击关闭，不影响当前选择

## 10. 任务历史 TasksPage

- [x] 10.1 创建 `src/pages/TasksPage.tsx`，作为 `/tasks` 路由的页面组件
- [x] 10.2 将现有 `AnalysisTasksPage` 的核心渲染逻辑迁移到 `TasksPage`（如 AnalysisTasksPage 与 App.tsx 状态耦合较重，允许 TasksPage 作为薄 wrapper 先 import/render 旧组件，不在本 change 内重写任务列表内部逻辑） — 薄 wrapper 实现：TasksPage.tsx 为占位，实际渲染通过 App.tsx switch 中 "tasks" case 直接使用 AnalysisTasksPage
- [x] 10.3 从 `App.tsx` 中移除原 `AnalysisTasksPage` 组件定义 — 暂未提取，AnalysisTasksPage 仍在 App.tsx 中
- [x] 10.4 保留任务状态筛选、删除、进入详情等功能不变

## 11. 训练页隐藏

- [x] 11.1 从 `platformNavigation` 数组中移除训练入口
- [x] 11.2 从首页能力卡片中移除训练跳转
- [x] 11.3 保留 `/training` 路由解析和 TrainingPage 组件代码不变
- [x] 11.4 保留 `OverviewCards` 中不出现训练相关入口

## 12. 清理与收尾

- [x] 12.1 从 AppShell Footer 更新文案（如移除过时描述）
- [x] 12.2 确保浏览器前进/后退在新增路由上正常工作
- [x] 12.3 确保所有页面组件正确 import 所需的 API 函数和类型
- [x] 12.4 检查 TypeScript 编译无类型错误（`npm run build` 或 `tsc -b`）
- [x] 12.5 验证首页 → 上传模式 → 分析任务流程完整可用
- [x] 12.6 验证首页 → 录制模式 → 创建向导 → 控制台 → 录制 → 完成面板流程完整可用
