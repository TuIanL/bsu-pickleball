# analysis-flow-navigation Delta

## ADDED Requirements

### Requirement: 分析工作区保留展示机位选择

分析工作区 SHALL 使用独立的 `displayView` 查询参数表达当前双摄展示机位。该参数 SHALL 与已有 workspace `view` 和 `analysisJob` 参数共存，且在刷新、Tab 切换、嵌入式结果导航和返回当前任务时保持不变；非法值 SHALL 回退到任务默认 reference view。

#### Scenario: Tab 切换保留展示机位

- **WHEN** 用户在 `view=analysis&displayView=cam_2&analysisJob=job-1` 切换到球路或技术详情
- **THEN** 目标 URL SHALL 保留 `displayView=cam_2` 与 `analysisJob=job-1`
- **AND** 返回分析视图时 SHALL 继续展示 `cam_2`

#### Scenario: 历史任务没有展示机位字段

- **WHEN** 用户打开历史双摄结果且 URL 没有 `displayView`
- **THEN** 系统 SHALL 使用任务 `referenceViewId` 作为默认展示机位
- **AND** SHALL 保持既有返回路径和历史结果读取行为
