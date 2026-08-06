## 1. 选择状态辅助逻辑

- [x] 1.1 在 `src/utils/analysisHelpers.ts`（或新建选择辅助模块）实现模式勾选态计算函数：输入 `analysisMode`、该类可删任务集合、`selectedJobIds`，输出 `"checked" | "indeterminate" | "unchecked"` 三态
- [x] 1.2 实现批量增删函数：勾选模式 = 将 `eligible(m)` 全部加入 `selectedJobIds`；取消 = 全部移除（保持 set 语义、去重、不产生副作用）
- [x] 1.3 为上述纯函数补充单元测试（三态判定、勾选/取消、空集边界、运行中任务排除）

## 2. 弹层组件

- [x] 2.1 新建轻量 popover 组件（`src/components/platform/` 下），支持外部 `mousedown` 点击关闭与 `Escape` 关闭，面板内点击不关闭
- [x] 2.2 组件渲染三个分析模式行：模式中文标签（复用 `analysisModeLabel`）、可删任务计数、三态复选框（`indeterminate` 属性），全部无可删任务时禁用
- [x] 2.3 组件以受控方式接入：由调用方传入模式统计与勾选态、以及 check/uncheck 回调

## 3. AnalysisTasksPage 集成

- [x] 3.1 在「上传视频任务」tab 工具栏新增「按类型选择」按钮（带小箭头图标），点击展开弹层；弹层打开/关闭状态用局部 state 管理
- [x] 3.2 计算各模式可删任务集合与计数（基于现有 `eligibleJobIds` 与 `jobs.analysisMode`），并派生三态
- [x] 3.3 模式勾选/取消回调写入现有 `selectedJobIds`，卡片复选框与「已选 N 个」计数随现有渲染路径自动同步
- [x] 3.4 手动单卡勾选/取消后重算模式三态，半选态正确显示
- [x] 3.5 删除仍复用现有「批量删除」按钮与确认/反馈流程，验证模式选择 + 批量删除端到端可用（含本地样例任务删除兜底）

## 4. 验证

- [x] 4.1 `npm test` 通过（含新增辅助函数测试），`npm run build` 通过
- [x] 4.2 手工验证：勾选/取消模式、手动调整卡片后半选态、弹层点击外部/Escape 关闭、空列表与无可删任务禁用、模式选择后批量删除结果反馈与列表刷新

## 5. 类型筛选扩展（弹层同时承担分类功能）

- [x] 5.1 弹层改造为两区：顶部「按类型筛选」单选区（全部/样例任务/有限分析/真实视频分析，点击即过滤列表），下方保留「批量选择」多选区
- [x] 5.2 `AnalysisTasksPage` 新增 `modeFilter` state（`AnalysisModeFilter = AnalysisModeValue | "all"`），`filteredUploadJobs` 基于排序结果过滤；点击当前激活项回到「全部」
- [x] 5.3 工具栏「全选」与「已选 N 个」计数改为按筛选后可见可删任务计算（`visibleEligibleIds` / `selectedVisibleIds`），批量删除仍按全局选择集
- [x] 5.4 组件测试覆盖：筛选区 4 选项渲染、aria-pressed 激活态、与批量选择区并存
- [x] 5.5 `npm test`（38 文件 270 用例）与 `npm run build` 通过，dev server 热更新生效

## 6. 视觉反馈与跨路由持久化

- [x] 6.1 筛选激活时按钮显示「按类型选择 · {模式标签}」，并切换为深底白字的激活态样式；默认时保持浅色原样
- [x] 6.2 `modeFilter` 状态改为 `useState` lazy init 从 `sessionStorage["analysis-tasks-mode-filter"]` 读取；新增 `updateModeFilter` 写入 sessionStorage；handleSelectModeFilter 走 updateModeFilter
- [x] 6.3 读取/写入均做 try/catch，隐私模式或无 sessionStorage 时静默回退
- [x] 6.4 spec 同步新增两条 requirement（active filter on trigger、mode filter survives navigation）
- [x] 6.5 `npm test`（38 文件 270 用例）、`npm run build`、`openspec validate --changes` 通过
