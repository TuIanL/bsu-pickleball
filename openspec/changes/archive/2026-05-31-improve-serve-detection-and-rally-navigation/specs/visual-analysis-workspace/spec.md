## MODIFIED Requirements

### Requirement: 真实视频发球开始 marker

真实视频分析工作台 SHALL 在完成任务的播放器下方显示独立的发球候选回合导航条，并支持用户快速跳转复盘；播放器进度条 SHALL 保留为播放控制，不再作为密集发球候选的主要浏览入口。

#### Scenario: 发球事件导航条可用
- **WHEN** 用户打开完成的真实视频分析工作台且发球事件 artifact 已加载并包含候选事件
- **THEN** 播放器下方 SHALL 渲染与视频播放器宽度对齐的横向导航条，每个候选事件显示为可点击矩形卡片，并展示候选序号、时间、置信度、检测模式和简短依据

#### Scenario: 用户点击发球候选卡片
- **WHEN** 用户点击发球候选导航条中的矩形卡片
- **THEN** 播放器 SHALL 跳转到该候选的 `seek_time_seconds`，使用户能看到发球前准备和击球附近画面

#### Scenario: 候选数量较多
- **WHEN** 发球候选数量超过播放器宽度能够舒适展示的数量
- **THEN** 导航条 SHALL 在固定宽度容器内支持横向平滑滚动，而不得把所有候选铺成超出页面的静态长横排

#### Scenario: 当前播放时间命中候选片段
- **WHEN** 当前视频时间处于某个候选的 `start_time_seconds` 到 `end_time_seconds` 范围内，或接近该候选 `timestamp_seconds`
- **THEN** 导航条 SHALL 以可见样式高亮对应候选卡片，且不得改变视频播放状态

#### Scenario: marker 超出视频时长保护
- **WHEN** 发球事件 artifact 中的候选时间接近视频起点或终点
- **THEN** 工作台 SHALL 将候选卡片的跳转时间限制在有效视频时长内，避免播放器跳转到无效时间

#### Scenario: 候选展示信号摘要
- **WHEN** 发球候选事件包含 signal scores、候选片段时间窗或覆盖诊断
- **THEN** 候选卡片、tooltip、状态区域或相邻详情 SHALL 能展示底线站位、发球前静止、手臂或 ROI 峰值、后续回合激活、覆盖不足等摘要，而不阻塞播放器操作

## ADDED Requirements

### Requirement: 发球候选导航条加载和降级状态

真实视频分析工作台 SHALL 将发球候选导航条作为独立数据层加载，使缺失、加载中、降级或失败状态不影响基础视频播放。

#### Scenario: 发球事件正在加载
- **WHEN** 完成任务的 source video 已可播放但发球事件 artifact 仍在加载
- **THEN** 工作台 SHALL 保持视频和已有 overlay 可用，并在播放器下方导航区域显示发球候选加载状态

#### Scenario: 发球事件不可用
- **WHEN** 发球事件 artifact 状态为 `unavailable` 或 `no_candidates`
- **THEN** 导航条区域 SHALL 显示对应状态说明，并不得用 demo timeline marker 或模拟发球点填充真实视频

#### Scenario: 发球事件部分可用
- **WHEN** 发球事件 artifact 状态为 `partial` 或候选声明降级检测模式
- **THEN** 导航条 SHALL 仍显示可用候选，并以候选语义表达检测信号受限

#### Scenario: 发球事件请求失败
- **WHEN** 发球事件 artifact 请求失败
- **THEN** 工作台 SHALL 仅标记发球候选导航层失败，并继续允许用户播放、暂停、拖动进度条和查看已加载 overlay
