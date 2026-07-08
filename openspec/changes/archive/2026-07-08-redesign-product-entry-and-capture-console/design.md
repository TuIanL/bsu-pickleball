## Context

当前前端页面像「把已有功能都摆出来的开发展示页」：顶部 4 个一级 tab 导航（总览/视频分析/球场采集/训练），CameraHubPage 把所有摄像头列表、实时预览、录制控制、最近录制平铺在同一个页面上。用户需要的是两个清晰的产品工作流入口：上传已有视频分析，和现场录制采集。

本次重构基于已有的 Field Session、Recording、Camera、TimelineEvent API，纯前端重组产品工作流，不做后端改动。

## Goals / Non-Goals

**Goals:**
- 简化顶部导航为「Logo（左）+ 辅助入口（右）」，移除所有一级 tab
- 首页改为两个主工作流入口按钮（上传模式 / 录制模式）
- 录制模式拆为 4 状态工作流：采集任务首页 → 三步向导 → 采集控制台 → 录制完成面板
- 摄像头管理收入设备抽屉，控制台主界面只显示当前使用的摄像头
- 训练页从所有导航中隐藏（代码保留）
- 新页面组件按「轻拆策略」拆为独立文件（`src/pages/`）

**Non-Goals:**
- 不改变后端 API
- 不彻底拆分 App.tsx 所有子组件
- 不大改上传分析（NewAnalysisPage）流程
- 不引入 react-router 等新依赖
- 不删除 TrainingPage / HardwarePage 代码
- 不新增自动比分、双摄同步等算法能力

## Decisions

### D1: 路由扩展策略

**决策**: 在手写 `parsePath()` 状态机上扩展 `RouteState` 联合类型，新增 5 个路由状态。

```typescript
// 新增路由状态
| { name: 'landing'; path: '/' }
| { name: 'upload'; path: '/upload' }
| { name: 'captureHome'; path: '/capture' }
| { name: 'captureNew'; path: '/capture/new' }
| { name: 'captureConsole'; path: `/capture/${string}`; sessionId: string }
| { name: 'tasks'; path: '/tasks' }
```

**替代方案**: 引入 react-router-dom —— 否决，因为手写路由足够简单且现有 `NavigateFn` 类型已大量使用于页面组件 props 中。

**注意**: `parsePath()` 中 `/capture/new` 必须在 `/capture/:id` 之前判断，避免 `new` 被误判为 sessionId。

### D2: 轻拆策略

**决策**: 仅拆分页面级组件到 `src/pages/`，不拆页面内部表单项、卡片等子组件。

```
src/pages/
├── LandingPage.tsx          ← 从 App.tsx OverviewPage 演化
├── UploadModePage.tsx       ← 包裹现有 NewAnalysisPage 逻辑
├── CaptureHomePage.tsx      ← 新：采集任务列表 + 新建入口
├── CaptureWizardPage.tsx    ← 新：三步向导
├── CaptureConsolePage.tsx   ← 从 App.tsx CameraHubPage 剥离核心
└── TasksPage.tsx            ← 包裹现有 AnalysisTasksPage 逻辑
```

**替代方案**: 全面拆 App.tsx → 否决，本次重构范围已经很大，全面拆会增加 review 面和 bug 风险。

### D3: 录制模式状态机

**决策**: 采集工作流的页面级状态使用 URL 路由，CaptureConsole 内部的录制瞬态使用前端 state。

```
页面级状态（URL 路由）：

/capture          → CaptureHomePage      （采集任务列表 + 新建入口）
/capture/new      → CaptureWizardPage     （三步创建向导）
/capture/:id      → CaptureConsolePage    （采集控制台）

CaptureConsole 内部录制状态（前端 state）：

'preview'     — 实时预览 + 设备状态 + 开始录制按钮
'recording'   — 预览 + 停止录制 + 事件标记 + 时间线
'stopped'     — CaptureComplete 面板（覆盖或内嵌），关闭后回到 'preview'
```

页面间跳转通过 `navigate()` 改变 URL，控制台内部状态切换只用 `useState`，不改 URL。

**替代方案**: 用 URL 参数控制录制瞬态 → 否决，状态过于瞬态不适合 URL。

### D4: 设备抽屉

**决策**: 控制台主界面只显示「设备状态区」（当前采集方案使用的摄像头），点击「更换摄像头」打开右侧抽屉展示所有已注册摄像头、注册新摄像头、探测、删除操作。

**替代方案**: 在控制台里保留旧版摄像头列表 → 否决，会退回开发调试页的感觉。

### D5: 自动分析设置两层设计 + sessionStorage 兜底

**决策**: 向导第三步设置默认行为；录制完成面板根据默认行为展示对应选项。`analysisIntent` 不写入 Field Session（后端零改动），但用 sessionStorage 兜底避免刷新丢失。

**analysisIntent 生命周期**：

```
CaptureWizard 创建任务时：
  → 把 analysisIntent 存入 sessionStorage["capture.analysisIntent.{fieldSessionId}"]

CaptureConsole 加载时（优先级从高到低）：
  1. 从路由 state / 组件 local state 读取
  2. 从 sessionStorage["capture.analysisIntent.{fieldSessionId}"] 恢复
  3. 均无 → 默认 'ask_after_recording'（录制完成后再决定）

开始录制时：
  → 根据 analysisIntent 设置 RecordingStartRequest.auto_analyze_after_stop:
    'auto_analyze'       → auto_analyze_after_stop = true
    'ask_after_recording'→ auto_analyze_after_stop = false
    'save_only'          → auto_analyze_after_stop = false

停止录制后：
  → 读取 RecordingSession.auto_analysis_job_id 判断是否已自动创建分析
  → CaptureComplete 面板始终允许用户手动发起分析任务
```

**CaptureComplete「创建分析任务」按钮行为**：

「立即创建分析任务」「创建分析任务」按钮统一复用现有录制视频创建分析入口：

```
navigate(`/upload?videoId=${recording.video_id}&source=recording`)
```

这会复用 `UploadModePage`（原 `NewAnalysisPage`）已有的 `?videoId=xxx&source=recording` 参数支持，用户进入四角标定 + 元数据 → 创建分析任务流程。不在本 change 新增直接创建 analysis job 的 API 调用。

**替代方案**: 给 Field Session 新增 `analysis_intent` 字段 → 暂不做，保持后端零改动。

### D6: 训练页隐藏策略

**决策**: 从 `platformNavigation`、首页卡片、AppShell 所有导航中移除训练入口。保留 `/training` 路由和 TrainingPage 组件代码不删。

## Risks / Trade-offs

- **[风险] App.tsx 仍较大**（路由壳 + 保留的旧页面组件仍在文件中）→ 缓解：本次轻拆已拆出 6 个页面文件，App.tsx 从 5000+ 行缩减到约 3000+ 行，后续可渐进拆分
- **[风险] 录制控制台状态复杂度** → 缓解：使用 3 个明确状态（preview/recording/stopped），每个状态对应清晰的 UI 区块
- **[风险] `/capture/new` 和 `/capture/:id` 路由冲突** → 缓解：在 parsePath 中先匹配 `/capture/new` 再匹配 `/capture/:id`
- **[取舍] 向导第三步的 analysisIntent 不持久化到后端** → 通过 sessionStorage 兜底确认；CaptureComplete 面板始终提供手动创建分析任务的入口，刷新不影响核心路径
