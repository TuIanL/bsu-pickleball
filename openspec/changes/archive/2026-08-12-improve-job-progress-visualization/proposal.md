# Improve Job Progress Visualization

## Why

任务分析页（`AnalysisJobPage`）与任务列表页（`AnalysisTasksPage`）的进度展示不直观、页面臃肿：

1. **主进度条与阶段列表不对齐**：主进度 `job.progress` 是 12 个阶段等权平均的结果，只会在阶段切换时跳变（用户感知为"10%、34%"等预设值），用户无法把百分比对应到"正在跑哪一步"。
2. **12 个分析阶段纵向罗列冗长**：每个阶段一张卡片（状态点 + 标题 + 详情 + 耗时），信息密度低、占满一屏，与顶部进度卡形成两套割裂的表达。
3. **hero 区元素堆叠**：返回、标签、大标题、元信息、任务 ID、当前阶段 pill、进度大数字卡挤在一起；任务完成后进度区仍占据主要位置。

本轮只改**前端展示形式**，后端进度模型（等权平均、阶段内细粒度 progress）不动，作为后续独立 change。

## What Changes

- **胶囊式横向阶段 stepper**：`AnalysisJobPage` 的 12 个纵向阶段卡片改为一行横向胶囊节点（图标 + 短标签 + 连接线），可左右滑动（`overflow-x-auto`），已完成=绿、当前=橙色呼吸、失败=红、跳过=灰、待办=浅灰；当前节点自动滚动到可视区，默认聚焦当前运行阶段。
- **当前阶段详情单独成行**：stepper 下方突出显示当前阶段的 `detail` 文案（如"正在逐帧分析：已处理 412/1200 帧"），让用户看到"任务在动"。
- **hero 区重组**：返回 + 状态徽章 → 大标题 → 一行元信息（标题·文件·场馆·任务 ID）→ 进度区（stepper + 当前阶段详情 + 整体百分比）。
- **双摄 viewRuns 并入进度区**：A/B 机位迷你进度条从独立区块移入进度区，不再单独成卡。
- **完成 / 失败 / 取消态的进度区降级**：终态下进度区收窄为一行摘要，结果入口与操作按钮置顶。
- **任务信息折叠**：10 行 kv 信息默认折叠（`<details>`），失败 / 取消诊断卡保留。
- **任务列表卡进度区调整**：`AnalysisTasksPage` 卡片右侧进度区与详情页保持一致的表达（百分比 + 当前阶段名），弱化跳变感知。

## Capabilities

### New Capabilities

无（本轮为既有页面行为修改，不引入新能力域）。

### Modified Capabilities

- `video-analysis-job-flow`: "Analysis job status page" 需求的进度与阶段展示要求从纵向 stage 列表改为横向胶囊 stepper + 当前阶段详情高亮，终态下进度区降级。
- `analysis-task-management`: 任务列表卡（task row / card）的进度展示要求细化为"百分比 + 当前阶段名"的一致表达。

## Impact

- `src/pages/AnalysisJobPage.tsx`：页面重构主体（hero 区、进度区、阶段展示、双摄区块、任务信息折叠）。
- `src/pages/AnalysisTasksPage.tsx`：任务列表卡进度区调整。
- 新增共享组件（建议 `src/components/platform/JobStageStepper.tsx`）：胶囊式 stepper，供详情页与列表卡复用。
- 测试：`AnalysisJobPage` 相关行为测试、`AnalysisTasksPage.test.tsx` 需同步更新（若断言了旧 stage 列表结构）。
- 无后端 / API / 数据模型改动；`types/report.ts` 现有字段（`stages[].progress`、`viewRuns`）已满足需求。
