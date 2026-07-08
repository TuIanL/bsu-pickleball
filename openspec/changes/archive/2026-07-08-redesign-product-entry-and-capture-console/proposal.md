## Why

当前前端页面组织方式更像是「把已有功能都摆出来的开发展示页」——顶部「总览 / 视频分析 / 球场采集 / 训练」四个一级 tab 导航，CameraHubPage 里摄像头列表、实时预览、录制控制、最近录制全部平铺在同一个页面上。这不符合一个用户真正到球场使用产品的心理路径。需要将前端从「功能调试集合页」重构为「两个清晰产品工作流入口」：上传已有视频分析，和现场录制采集。

## What Changes

- **BREAKING**: 移除顶部「总览 / 视频分析 / 球场采集 / 训练」一级 tab 导航，替换为「Logo + 产品名（左）+ 任务历史（右，帮助入口预留但本次不实现）」的极简导航
- 新增产品首页（LandingPage），保留 Hero 大视觉区，中央放置「上传模式」「录制模式」两个主入口按钮，下方放三个纯展示能力卡片
- 上传模式入口进入现有视频上传 → 四角标定 → 创建分析任务流程（NewAnalysisPage 流程不变，只换入口）
- 录制模式拆分为 4 状态工作流：采集任务首页（CaptureHome）→ 新建采集任务三步向导（CaptureWizard）→ 采集控制台（CaptureConsole）→ 录制完成面板
- 摄像头列表从主页面平铺收进「设备抽屉」，控制台主界面只显示当前采集方案使用的摄像头状态
- 训练页从所有一级导航和首页入口中完全隐藏，保留 `/training` 路由和代码
- 任务历史从顶部导航移动至首页右上角辅助入口，不再作为一级 tab
- 采用「轻拆策略」：将新页面组件拆为独立文件（`src/pages/`），现有的上传分析、摄像头卡片等内部子组件暂不拆

## Capabilities

### New Capabilities
- `product-landing`: 产品首页，包含 Hero 区、两个主工作流入口按钮（上传模式 / 录制模式）、三个能力介绍卡片（纯展示无跳转）
- `capture-workflow`: 现场采集完整工作流，包含采集任务首页（任务列表 + 新建入口）、三步创建向导（采集场景 / 摄像头方案 / 分析设置）、采集控制台（左预览右控制 + 场边事件标记 + 时间线）、录制完成面板（创建分析 / 保存视频 / 回看）
- `device-drawer`: 摄像头设备管理抽屉——将摄像头注册、探测、删除操作从主页面收入侧边抽屉，主界面仅显示当前采集方案正在使用的摄像头状态

### Modified Capabilities
- `layered-product-navigation`: 移除四 tab 一级导航，改为 Logo + 产品名（左）+ 任务历史（右，帮助预留）的极简导航；首页成为两个工作流的唯一入口
- `field-sessions`: 采集任务创建从弹窗表单改为三步向导流程；Field Session 作为核心对象串联摄像头、录制、事件标记和分析任务
- `camera-ingest-management`: 摄像头列表不再平铺在主页面，改为通过设备抽屉访问
- `training-feedback-loop`: 从所有一级导航和首页入口隐藏，代码和路由保留但不在 UI 中暴露

## Impact

- **前端文件**: AppShell.tsx（重写导航）、App.tsx（扩展路由 + 轻拆页面）、demoData.ts（overviewCards 改为 landing 卡片）、新增 src/pages/ 下 6 个页面文件
- **API**: 无变更，复用现有 Field Session、Recording、Camera、TimelineEvent API
- **后端**: 无变更
- **依赖**: 不引入新库，保持 React 19 + Vite 7 + TypeScript + Tailwind CSS 4 技术栈
