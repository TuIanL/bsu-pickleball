## Why

当前应用导航层（AppShell）只有顶部 header，所有页面平铺切换，缺少专业级站点应有的导航层次。实时录制工作台（CaptureConsolePage）是一个 743 行单体组件，视觉上使用大面积浅绿渐变背景，信息层级不清晰，不符合比赛现场长时间使用的专业控制台要求。

## What Changes

### 全局导航
- **LandingPage** 简化为纯营销落地页，只保留一个「进入开始使用」入口按钮
- 所有内部页面共享新的侧边栏导航布局（216px 固定左侧导航）
- 侧边栏底部显示当前录制状态块（通过独立 API 获取活跃录制信息）
- 侧边栏导航项：工作台、视频管理、分析任务、报告中心、设备管理、设置

### 实时录制工作台重构
- 从 743 行单体组件拆分为捕获工作台布局（CaptureWorkspaceLayout）和子组件
- 重构策略：先搭新骨架（方案 A），再逐块提取组件并切换样式
- 新布局结构：侧边栏 | 标题栏 → 双摄预览 → 控制栏 → 事件标注时间线（统一卡片） → 底部三栏信息
- 视觉迁移：页面背景改为 `#F7F8FA`，绿色保留为品牌强调色，不再作为页面大底色

### MiniTimeline 改进
- 时间刻度从三点标签改为等距时间刻度（自动计算整洁间隔）
- 新增重点标记（highlight marker）独立轨道行
- 区间序号截断问题搁置

### 后端
- 新增 `GET /api/capture-takes/active` 接口，供侧边栏查询当前活跃录制状态

## Capabilities

### New Capabilities
- `app-sidebar`: 全局侧边栏导航组件，含导航项高亮、品牌标识、底部活跃录制状态块
- `capture-workspace-layout`: 实时录制工作台新布局，含子组件插槽定义和视觉 token 系统

### Modified Capabilities
- `live-coding-console`: MiniTimeline 的行为变更（等距刻度、重点标记轨道），事件按钮的视觉分组与样式更新
- `frontend-capture-runtime`: 新增主动录制查询接口（`GET /api/capture-takes/active`）供侧边栏独立消费

## Impact

- **AppShell.tsx**: 从单纯 header 升级为 header + sidebar 布局壳，需感知路由以决定是否渲染侧边栏
- **App.tsx**: 路由状态可能需提升或下传到 AppShell
- **CaptureConsolePage.tsx**: 743 行 → 拆分为 10+ 子组件，逐步替换渲染函数
- **MiniTimeline.tsx**: 刻度渲染逻辑重写 + 新增轨道
- **analysisClient.ts**: 新增 `getActiveCaptureTake()` API 方法
- **router.ts / navigationTypes.ts**: 可能需新增路径常量
- **LandingPage.tsx**: 大幅简化，只保留品牌展示和 CTA
