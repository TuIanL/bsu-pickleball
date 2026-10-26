## MODIFIED Requirements

### Requirement: 上传/采集默认落点

Library-first 后，上传与现场采集的分析 SHALL 遵循统一生命周期：创建 Job 后先进入 Analysis Progress（transient），legacy_v1（含缺省 engine）完成后再进入对应 LibraryItem Workspace；modular_v1 由同一任务路由承接模块结果并保留来源返回，不自动进入完整分析 Workspace，也不回到任务列表。

#### Scenario: 上传创建分析后进入进度页再入比赛详情

- **WHEN** 用户完成上传 + 四角标定 + 创建 legacy_v1 分析
- **THEN** 系统 SHALL 先进入 `/analysis/:jobId?return=/library/upload/{videoId}?view=overview`（Analysis Progress）
- **AND** 任务完成后 SHALL 进入 `/library/upload/{videoId}?view=analysis`
- **AND** SHALL NOT 导航回 `AnalysisTasksPage`

#### Scenario: 采集 durable 后进入库卡片

- **WHEN** 现场采集完成后素材 durable 化
- **THEN** 该素材 SHALL 以对应 LibraryItem 呈现在比赛库中

#### Scenario: 全新上传无 return 时合成 Library return

- **WHEN** 用户从比赛库「上传视频」进入 `/upload`（无 `return` 且 `videoId` 尚未生成），上传成功并创建 Job
- **THEN** 系统 SHALL 先进入 `/analysis/:jobId?return=/library/upload/:videoId?view=overview`（Analysis Progress）
- **AND** legacy_v1 完成后 SHALL 进入 `/library/upload/:videoId?view=analysis`；modular_v1 SHALL 留在模块结果并保留该 Library return
- **AND** SHALL NOT 被识别为 task-console，也不进入 `/analysis/tasks`

#### Scenario: 专项任务保持模块结果边界
- **WHEN** 上传或录制入口创建 modular_v1 任务并完成
- **THEN** `/analysis/:jobId` SHALL 展示该模块清单结果并提供原素材返回入口
- **AND** SHALL NOT 自动加载 legacy 固定结果、报告或球路

## ADDED Requirements

### Requirement: 专项创建逻辑按领域共用

三个创建页 SHALL 共用专项 API 合同、纯模式映射、创建状态管理和配置/预览组件；页面仅承担来源解析、展示与导航编排。依赖展开 SHALL 由后端 Planner 负责，重型专项页面 SHALL 保持现有按需加载边界。

#### Scenario: 修改专项模式配置
- **WHEN** 调整首批模式名称或目标映射
- **THEN** 三个入口 SHALL 消费同一配置，不维护三份独立依赖图或请求序列化

#### Scenario: 未访问分析创建页
- **WHEN** 用户只打开 landing
- **THEN** 新增专项创建代码 SHALL NOT 使分析工作台成为首屏静态重依赖
