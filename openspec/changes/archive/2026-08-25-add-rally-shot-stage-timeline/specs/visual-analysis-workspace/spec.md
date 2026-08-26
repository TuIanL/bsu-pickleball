## ADDED Requirements

### Requirement: 数据分析区域展示回合—击球阶段时序图

对于已完成的真实视频分析任务，视觉分析页的数据分析区域 SHALL 在现有位置热力图、位置散点图和区域空间热力图之外，提供回合—击球阶段时序图卡片。该卡片 SHALL 标明数据来源为当前任务，并与视频和其他可视化模块保持独立加载。

#### Scenario: 完成任务存在可用事件 artifact

- **WHEN** 用户打开包含可用 `shot-rally-events.v1` 的已完成真实任务视觉分析页
- **THEN** 数据分析区域 SHALL 显示回合—击球阶段时序图
- **AND** 页面 SHALL 保留现有三张位置类可视化图

#### Scenario: 完成任务缺少事件 artifact

- **WHEN** 用户打开已完成真实任务，但该任务没有可读取的 `shot-rally-events.v1`
- **THEN** 数据分析区域 SHALL 保留时序图卡片并显示明确 unavailable/failed 状态
- **AND** SHALL NOT 回退为 demo 时序图

### Requirement: 时序图状态不得阻塞视频优先工作区

视觉分析页 SHALL 将回合—击球阶段时序图的请求、解析和渲染状态限制在该卡片内，不得因为时序 artifact 加载慢、缺失或失败而阻塞视频播放、任务状态、报告入口或已有位置可视化。

#### Scenario: 时序图慢于视频和位置图

- **WHEN** 视频、任务状态和位置可视化已经加载，而时序 artifact 仍在加载
- **THEN** 页面 SHALL 先显示视频和已有位置可视化
- **AND** 时序图卡片 SHALL 单独显示 loading

#### Scenario: 时序图发生解析错误

- **WHEN** 时序 artifact 返回格式错误或前端解析失败
- **THEN** 页面 SHALL 将时序图标记为 failed 并提供可读原因
- **AND** SHALL 保持视频、状态栏和其他可视化可用
