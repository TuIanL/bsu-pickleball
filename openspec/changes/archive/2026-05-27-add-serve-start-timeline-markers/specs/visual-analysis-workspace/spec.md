## ADDED Requirements

### Requirement: 真实视频发球开始 marker

真实视频分析工作台 SHALL 在完成任务的播放器进度条上显示后端发球开始候选事件 marker，并支持用户快速跳转复盘。

#### Scenario: 发球事件 marker 可用
- **WHEN** 用户打开完成的真实视频分析工作台且发球事件 artifact 已加载并包含候选事件
- **THEN** 播放器进度条 SHALL 在每个候选事件时间位置渲染可见 marker，并展示候选时间、置信度和简短依据

#### Scenario: 用户点击发球 marker
- **WHEN** 用户点击进度条上的发球开始候选 marker
- **THEN** 播放器 SHALL 跳转到该事件的 `seek_time_seconds` 或等效预卷时间，并保持现有视频、人体框和骨架 overlay 同步

#### Scenario: marker 超出视频时长保护
- **WHEN** 发球事件 artifact 中的 marker 时间接近视频起点或终点
- **THEN** 播放器 SHALL 将跳转时间限制在有效视频时长范围内，避免 seek 到无效时间

### Requirement: 发球事件加载和降级状态

真实视频分析工作台 SHALL 将发球事件 artifact 作为独立数据层加载，使缺失、加载中或失败状态不影响基础视频播放。

#### Scenario: 发球事件正在加载
- **WHEN** 完成任务的 source video 已可播放但发球事件 artifact 仍在加载
- **THEN** 工作台 SHALL 保持视频和已有 overlay 可用，并在控制区或状态区域显示发球 marker 加载状态

#### Scenario: 发球事件不可用
- **WHEN** 发球事件 artifact 状态为 `unavailable`、`no_candidates` 或 `partial`
- **THEN** 工作台 SHALL 显示对应状态说明，并不得用 demo timeline marker 或模拟发球点填充真实视频进度条

#### Scenario: 发球事件请求失败
- **WHEN** 发球事件 artifact 请求失败
- **THEN** 工作台 SHALL 仅标记发球 marker 层失败，并继续允许用户播放、暂停、拖动进度条和查看已加载 overlay

### Requirement: 发球 marker 来源清晰

真实视频分析工作台 SHALL 清楚区分发球开始候选 marker、demo timeline marker 和未来可能的完整回合边界。

#### Scenario: 用户查看真实任务 marker
- **WHEN** 用户在真实视频播放器上看到发球开始 marker
- **THEN** UI SHALL 使用“发球候选”或等效文案表达不确定性，并避免称其为完整回合切分结果

#### Scenario: 用户查看 demo 页面
- **WHEN** 用户打开没有真实 job context 的 demo 视觉分析页面
- **THEN** 系统 SHALL 保持现有 demo timeline 行为，不得把 demo marker 表示为后端发球检测结果
