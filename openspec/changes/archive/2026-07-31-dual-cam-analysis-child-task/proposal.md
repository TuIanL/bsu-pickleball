## Why

双摄同步录制（SyncRecordingSession）已经能正常产出 cam_1 与 cam_2 两路视频并完成注册，但分析链路只暴露了 cam_1 入口，cam_2 无法被提交分析。同时，录制完成的视频仍需经过 `NewAnalysisPage`（字段填写 + 四角标定 + 元数据表单）重新创建独立的分析任务，录制时已标记的场地、比赛时间、相机角度、帧率等属性被浪费，用户需要重复填写。侧边栏导航标签与实际目标完全颠倒（"分析任务"→采集列表，"视频管理"→分析任务列表），加剧了定位混乱。

## What Changes

- **双摄录制卡片新增 A/B 机位分析入口**：合并完成后，录制卡片为 cam_1 和 cam_2 各显露一个「分析 A/B 机位」按钮，可独立发起分析。
- **录制→分析迷你配置面板**（新增路由）：点击任一机位的分析按钮后，跳转迷你页面，仅展示从录制继承的只读元数据 + 四角标定 + 确认启动，不重复填写 8 个字段。
- **分析任务归属录制**：后端 `AnalysisJobCreate` 新增 `recording_session_id` / `camera_slot` 字段；前端分析任务卡片展示「来源录制」标签，分析和录制形成可追溯的父子关系。
- **侧边栏导航标签对调**：`/analysis/tasks` 标签修正为「分析任务」，`/capture` 标签修正为「视频管理」。
- **默认帧率对齐**：`NewAnalysisPage.sourceFps` 默认值从 30 改为 60，与录制端默认 fps 60 一致。
- **清理死代码**：删除从未被调用的 `src/pages/TasksPage.tsx` 和 `src/pages/UploadModePage.tsx`。
- **录制链路与 NewAnalysisPage 解耦**：录制→分析不再经过 `NewAnalysisPage`；`NewAnalysisPage` 降级为纯文件上传路径的入口。

## Capabilities

### New Capabilities
- `recording-analysis-bridge`: 录制→分析的迷你配置面板，从录制继承元数据（只读），仅做四角标定 + 机位选择后直接 POST 创建分析任务；建立分析任务到录制 session 的父子归属关联。

### Modified Capabilities
- `analysis-task-management`: AnalysisJobCreate 新增 `recording_session_id` / `camera_slot` 字段；分析任务列表支持按录制 session 过滤；分析任务展示「来源录制」关联信息。
- `app-sidebar`: 修正两个导航项标签与路径的对应关系（"分析任务"→`/analysis/tasks`，"视频管理"→`/capture`）。
- `dual-camera-sync-recording`: 合并完成后 cam_2 的 `registered_video_id` 可参与分析任务创建（当前只有 cam_1 被设为 `default_analysis_video_id`）。

## Impact

- **前端**：`NewAnalysisPage`（降级 + 默认 fps 改为 60）、`AnalysisTasksPage`（双摄 tab 内 A/B 按钮）、`AppSidebar`（标签对调）、新增页面 `RecordingAnalyzePage`、删除 `TasksPage.tsx` 与 `UploadModePage.tsx`、`AppRouter` 新增路由。
- **后端**：`schemas/analysis.py`（`AnalysisJobCreate` / `AnalysisJobSummary` 加字段）、`api/analysis*.py`（过滤参数 `recording_session_id`）、`sync_recorder_service.py`（cam_2 注册后同样允许参与分析——逻辑上已就绪，仅需确认）。
- **数据**：现有已合并的双摄录制在升级后将可对 cam_2 创建分析（向后兼容）。
