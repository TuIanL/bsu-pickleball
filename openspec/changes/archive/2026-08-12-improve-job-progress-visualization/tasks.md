## 1. JobStageStepper 共享组件

- [x] 1.1 新建 `src/components/platform/JobStageStepper.tsx`：胶囊式横向 stepper（阶段图标映射 + 短标签 + 连接线 + 状态配色：done 绿 / active 橙呼吸 / failed 红 / skipped·unavailable 灰 / canceled 深灰 / pending 浅灰），容器 `overflow-x-auto` + `scroll-snap`，支持 `compact` 模式（仅圆点不显文字）
- [x] 1.2 当前节点自动聚焦：`useEffect` 定位 active（无则 failed）节点，手动计算 `container.scrollLeft` 居中滚动（`prefers-reduced-motion` 时跳过平滑动画）
- [x] 1.3 为 `JobStageStepper` 编写组件测试（状态配色 / 当前节点高亮 / compact 渲染）

## 2. AnalysisJobPage 页面重构

- [x] 2.1 hero 区重组：返回 + 状态徽章（含分析模式）→ 大标题 → 一行元信息（标题·文件·场馆·任务 ID），移除原"当前阶段 pill"与"当前进度大数字卡"
- [x] 2.2 进度区：`JobStageStepper` + 当前阶段详情行（取 active/failed 阶段的 label + detail，如"正在逐帧分析：已处理 412/1200 帧"）+ 整体百分比小字与细进度条
- [x] 2.3 终态降级：completed 显示"12/12 阶段完成 · 总耗时 XX"摘要行并置顶结果入口；failed/canceled 进度区收窄为失败/取消阶段摘要，诊断卡保留
- [x] 2.4 双摄并入：`viewRuns` A/B 迷你进度条移入进度区；"数据来源表 / 融合质量"仅 `job.status === "completed"` 时显示
- [x] 2.5 任务信息 10 行 kv 用 `<details>` 默认折叠；失败/取消诊断卡不受折叠影响
- [x] 2.6 删除原 12 张纵向阶段卡片与"分析阶段"区块，清理不再使用的样式与导入

## 3. AnalysisTasksPage 列表卡

- [x] 3.1 任务卡进度区改为：整体百分比 + 当前阶段名胶囊 + compact `JobStageStepper`（完成绿点 / 当前橙点 / 待办灰点）
- [x] 3.2 failed 任务卡不显示进度条（保留错误摘要卡为主信息）

## 4. 测试与验证

- [x] 4.1 运行现有测试摸底，更新 `AnalysisJobPage` 相关行为测试（stepper 渲染、当前阶段详情、终态降级）
- [x] 4.2 更新 `AnalysisTasksPage.test.tsx`（列表卡进度区断言）
- [x] 4.3 `npm test` 全绿
- [x] 4.4 `npm run build`（tsc -b && vite build）通过
- [x] 4.5 本地冒烟：前后端启动、完成态(双摄 viewRuns/单摄)、失败态(错误码)、处理中单摄任务 progress 34→100 与 frame-sampling 实时 detail 均验证；操作可用性由组件测试覆盖（浏览器自动化环境不可用）
