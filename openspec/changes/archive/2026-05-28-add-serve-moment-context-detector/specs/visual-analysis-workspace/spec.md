## MODIFIED Requirements

### Requirement: 真实视频发球开始 marker

真实视频分析工作台 SHALL 在完成任务的播放器进度条上显示后端发球时刻候选事件 marker，并支持用户快速跳转复盘。

#### Scenario: 发球事件 marker 可用
- **WHEN** 用户打开完成的真实视频分析工作台且发球事件 artifact 已加载并包含候选事件
- **THEN** 播放器进度条 SHALL 在每个候选事件时间位置渲染可见 marker，并展示候选时间、置信度、检测模式和简短依据

#### Scenario: 用户点击发球 marker
- **WHEN** 用户点击进度条上的发球时刻候选 marker
- **THEN** 播放器 SHALL 跳转到该候选的 `seek_time_seconds`，使用户能看到发球前准备和击球附近画面

#### Scenario: marker 超出视频时长保护
- **WHEN** 发球事件 artifact 中的 marker 时间接近视频起点或终点
- **THEN** 工作台 SHALL 将 marker 位置和跳转时间限制在有效视频时长内，避免播放器跳转到无效时间

#### Scenario: marker 展示信号摘要
- **WHEN** 发球候选事件包含 signal scores 或候选片段时间窗
- **THEN** marker tooltip、状态区域或相邻详情 SHALL 能展示底线站位、发球前静止、手臂或 ROI 峰值、后续回合激活等摘要，而不阻塞播放器操作

### Requirement: 发球事件加载和降级状态

真实视频分析工作台 SHALL 将发球事件 artifact 作为独立数据层加载，使缺失、加载中、降级或失败状态不影响基础视频播放。

#### Scenario: 发球事件正在加载
- **WHEN** 完成任务的 source video 已可播放但发球事件 artifact 仍在加载
- **THEN** 工作台 SHALL 保持视频和已有 overlay 可用，并在控制区或状态区域显示发球 marker 加载状态

#### Scenario: 发球事件不可用
- **WHEN** 发球事件 artifact 状态为 `unavailable`、`no_candidates` 或 `partial`
- **THEN** 工作台 SHALL 显示对应状态说明，并不得用 demo timeline marker 或模拟发球点填充真实视频进度条

#### Scenario: 发球事件请求失败
- **WHEN** 发球事件 artifact 请求失败
- **THEN** 工作台 SHALL 仅标记发球 marker 层失败，并继续允许用户播放、暂停、拖动进度条和查看已加载 overlay

#### Scenario: 发球事件使用降级检测模式
- **WHEN** 发球事件 artifact 或候选事件声明检测模式为无 pose、ROI 差分或其他 partial 模式
- **THEN** 工作台 SHALL 以候选语义展示 marker，并在可用状态说明中表达检测信号受限

### Requirement: 发球 marker 来源清晰

真实视频分析工作台 SHALL 清楚区分发球时刻候选 marker、demo timeline marker 和未来可能的完整回合边界。

#### Scenario: 用户查看真实任务 marker
- **WHEN** 用户在真实视频播放器上看到发球时刻 marker
- **THEN** UI SHALL 使用“发球候选”“发球时刻候选”或等效文案表达不确定性，并避免称其为完整回合切分结果

#### Scenario: 用户查看 demo marker
- **WHEN** 用户打开没有真实 job context 的 demo 视觉分析页
- **THEN** 系统 SHALL 保持现有 demo timeline 行为，不得把 demo marker 表示为后端发球检测结果

#### Scenario: 调试 artifact 可用
- **WHEN** 真实任务包含发球候选调试 artifact 引用
- **THEN** 工作台 SHALL 可提供非阻塞入口或状态说明，使用户理解 marker 来自后端上下文检测而不是 demo 数据
