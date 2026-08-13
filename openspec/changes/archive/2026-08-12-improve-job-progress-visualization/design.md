# Design: Improve Job Progress Visualization

## Context

`AnalysisJobPage`（任务分析页，单摄 / 上传任务 / 双摄 Parent 共用）当前结构：

```
hero 卡（返回 / 标签 / 大标题 / 元信息 / 任务ID / 当前阶段 pill / 进度大数字卡）
  └ 双摄时：viewRuns A/B 子进度卡 + 数据来源表 + 融合质量（未完成也显示）
任务信息卡（10 行 kv） | 分析阶段卡（12 个纵向卡片：圆点 + 标题 + 详情 + 耗时）
结果入口 + 操作按钮
```

`AnalysisTasksPage` 任务卡右侧为"进度 XX% + 进度条"。

数据约束（后端本轮不动）：

- `job.progress` = 12 个阶段等权平均，阶段切换时跳变（8.3% 一档），active 阶段默认 `progress=10`，仅 frame-sampling 有真实细粒度值（10→95，每 30 帧回调）。
- `job.stages[]` 含 `label / status / detail / progress / durationMs / startedAt / endedAt`，状态枚举：`pending | active | done | partial | failed | skipped | unavailable | canceled`。
- 双摄 `job.viewRuns` 为 `{ cam_1: {status, stage, progress}, cam_2: {...} }`。

## Goals / Non-Goals

**Goals:**

- 用一行胶囊式横向 stepper 替代 12 张纵向阶段卡片，可左右滑动，默认聚焦并高亮当前运行阶段。
- 当前阶段的 `detail` 文案（含帧计数等实时信息）单独成行，让用户感知"任务在动"。
- hero 区重组为"返回 + 徽章 → 大标题 → 一行元信息 → 进度区"；进度区 = stepper + 当前阶段详情 + 整体百分比。
- 双摄 viewRuns 的 A/B 迷你进度条并入进度区，不单独成卡。
- 终态（completed / failed / canceled）下进度区收窄为一行摘要，结果入口与操作置顶。
- 任务信息 10 行 kv 默认折叠。
- `AnalysisTasksPage` 列表卡进度区与详情页表达一致（百分比 + 当前阶段名 + 紧凑 stepper）。
- 抽取出可在两页复用的 stepper 组件。

**Non-Goals:**

- 不改后端进度模型：等权平均、阶段内细粒度 progress 缺失、`job.progress` 跳变等均不在本轮处理（后续独立 change）。
- 不改变任何 API / 数据字段 / `types/report.ts`。
- 不新增页面路由。
- 双摄"数据来源表 / 融合质量"仅调整显示时机（完成后再展示），内容不改。

## Decisions

### D1. 新建共享组件 `JobStageStepper`

`src/components/platform/JobStageStepper.tsx`，两个使用方（详情页全尺寸、列表卡 compact 模式）。

- Props：`stages: AnalysisStage[]`、`activeId?: string`、`compact?: boolean`、`ariaLabel?: string`。
- 每个阶段渲染为胶囊：图标（按阶段 id 映射，复用 lucide：upload→Upload、queue→Clock、calibration→Ruler、video-read→FileVideo、frame-sampling→Frame、detection→Scan、pose→Bone、tracking→Footprints、projection→Crosshair、metrics→Activity、visualization→Film、report→FileText）+ 短标签 + 胶囊间细连接线。
- 状态配色（沿用现有 `sport-card` 浅色主题）：done=`bg-[#22C55E]` 绿、active=`bg-[#FF9500]` 橙呼吸、failed=`bg-[#FF4D4F]` 红、skipped/unavailable=`bg-slate-400` 灰、canceled=`bg-slate-500` 深灰、pending=`bg-slate-300` 浅灰。
- active 节点：`scale-110` + 自定义橙色呼吸动画（`@keyframes`，尊重 `prefers-reduced-motion`）。

**备选**：不抽组件、两页各自实现 → 两套表达易漂移，维护成本高；本轮改动两页同源同构，抽组件是自然选择。

### D2. 当前节点自动聚焦（滚动可见）

- 容器 `overflow-x-auto` + `scroll-snap-x`，每个胶囊 `snap-start`。
- `useEffect` 依赖 `stages`：定位 active（无则 failed）节点，**手动计算** `container.scrollLeft = node.offsetLeft - container.clientWidth/2 + node.clientWidth/2`（避免 `scrollIntoView` 触发整页滚动）。
- 首次进入 / 阶段变化时各执行一次；对 `prefers-reduced-motion` 用户跳过平滑滚动。

**备选**：`scrollIntoView({inline:'center', block:'nearest'})` → 窄容器内可能连带页面滚动，体验差；手动计算更可控。

### D3. hero 区重组与进度区结构

新结构（单一 sport-card）：

```
[← 返回任务管理]            [状态徽章 · 分析模式徽章]
分析中 (大标题)
标题 · 文件名 · 场馆 · 任务 ID
──────────────────────────────
进度区：
  ●→●→●→◉→○→○→○ (JobStageStepper, 可滑动)
  当前阶段详情行：◉ 抽帧采样 · 正在逐帧分析：已处理 412/1200 帧
  整体 34%   [████████░░░░]      （百分比小字，不再是大数字卡）
──────────────────────────────
（双摄时，进度区下方 A/B 两条迷你进度条）
```

- "当前阶段详情行"取 `stages.find(s => s.status==='active' || s.status==='failed')` 的 `label + detail`；终态下不存在 active 阶段，走 D4。
- 整体百分比保留但降级为小字（跳变问题由 stepper 的"当前阶段"承担主要表达，百分比仅作辅助）。

### D4. 终态进度区降级

- completed：进度区收窄为一行 `12/12 阶段完成 · 总耗时 XX`（`durationMs` 汇总），结果入口按钮上移到 hero 卡内（原独立"结果入口"section 删除或仅保留新建/返回等次要操作）。
- failed / canceled：进度区显示失败/取消阶段摘要（红色/灰色），诊断卡（`DiagnosticNoticeCard`）保留在 hero 卡下方。

### D5. 双摄 viewRuns 并入进度区

- `isMultiview && job.viewRuns` 时，在进度区下方渲染两行紧凑条：`A 机位 62% [██████]`、`B 机位 58% [█████]`，点击可跳转对应机位（保持现状不做跳转，仅展示）。
- 原"双摄协同分析"独立卡中：viewRuns 子进度移走；数据来源表 + 融合质量仅在 `job.status === 'completed'` 时显示（现状是 manifest 存在即显示）。

### D6. 任务信息折叠

- 10 行 kv 用 `<details>` 包裹，默认收起，summary 为"任务信息"。
- 失败 / 取消诊断卡不受折叠影响，始终可见。

### D7. 列表卡（AnalysisTasksPage）

- 右侧进度卡改为：`百分比` + `当前阶段名胶囊`（`currentStage.label`）+ 紧凑版 stepper（`compact`，只显示已完成的绿点和当前橙点，后续灰色小点，不显示图标文字，节省空间）。
- 失败任务：进度区替换为错误摘要（现状已有错误卡，保留），进度条隐藏。

## Risks / Trade-offs

- **[12 个胶囊仍可能拥挤]** → 窄屏下 `compact` 自动退化为"圆点 + 当前阶段文字"；胶囊文字用 `truncate` 防溢出。
- **[scroll 计算依赖布局时机]** → 在 `useEffect` + `requestAnimationFrame` 中执行；阶段切换（轮询刷新）时若节点未变化不重复滚动。
- **[现有测试断言旧结构失败]** → tasks 中包含更新 `AnalysisJobPage` / `AnalysisTasksPage` 测试用例的步骤；先跑测试摸底再改。
- **[终态降级影响既有"结果入口"操作位置]** → 按钮集合保持不变，仅调整位置与优先级；`onNavigate` 契约不变。
- **[跳变问题仅缓解不根治]** → 前端展示尽力而为（当前阶段承担主表达）；在 design 中明确记录后端改进为后续 change，避免预期落空。

## Migration Plan

1. 新增 `JobStageStepper` 组件（含单元测试）。
2. 重构 `AnalysisJobPage`：hero 重组 → 进度区 → 终态降级 → 双摄并入 → 任务信息折叠。
3. 调整 `AnalysisTasksPage` 列表卡进度区。
4. 更新/补齐相关测试，`npm test` 全绿，`npm run build` 通过。
5. 本地 `npm run app:start` 冒烟：单摄上传任务、双摄任务、完成态、失败态四条路径各看一眼。
6. 回滚：本改动纯前端、无数据迁移，`git revert` 即可。

## Open Questions

- 无阻塞性问题。实现时若遇到 stepper 在列表卡中的空间问题，按 D7 的退化方案处理。
