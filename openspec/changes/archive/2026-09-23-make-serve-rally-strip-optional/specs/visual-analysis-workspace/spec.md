## MODIFIED Requirements

### Requirement: 真实视频发球开始 marker

真实视频分析工作台 MAY 在完成任务的播放器下方提供独立的发球候选回合导航条，用于快速跳转复盘；该导航条默认不展示，仅当部署侧显式开启前端开关（`VITE_SERVE_RALLY_STRIP_ENABLED`）时才渲染。发球候选 SHALL 始终保持候选语义，MUST NOT 被表述为确认发球或完整回合切分。播放器进度条 SHALL 保留为播放控制，MUST NOT 作为密集发球候选的主要浏览入口。发球候选的检测与 artifact 发布与前端是否展示导航条无关。

#### Scenario: 导航条默认关闭
- **WHEN** 前端开关未开启（默认部署状态）
- **THEN** 工作台 SHALL 不渲染发球候选导航条，也不显示发球候选计数文案
- **AND** SHALL NOT 影响视频播放、其它已加载 overlay 与产物可用性状态展示

#### Scenario: 发球事件导航条可用
- **WHEN** 前端开关已开启、用户打开完成的真实视频分析工作台，且发球事件 artifact 已加载并包含候选事件
- **THEN** 播放器下方 SHALL 渲染与视频播放器宽度对齐的横向导航条，每个候选事件显示为可点击矩形卡片，并展示候选序号、时间、置信度、检测模式和简短依据

#### Scenario: 用户点击发球候选卡片
- **WHEN** 前端开关已开启且用户点击发球候选导航条中的矩形卡片
- **THEN** 播放器 SHALL 跳转到该候选的 `seek_time_seconds`，使用户能看到发球前准备和击球附近画面

#### Scenario: 候选数量较多
- **WHEN** 前端开关已开启且发球候选数量超过播放器宽度能够舒适展示的数量
- **THEN** 导航条 SHALL 在固定宽度容器内支持横向平滑滚动，而不得把所有候选铺成超出页面的静态长横排

#### Scenario: 当前播放时间命中候选片段
- **WHEN** 前端开关已开启且当前视频时间处于某个候选的 `start_time_seconds` 到 `end_time_seconds` 范围内，或接近该候选 `timestamp_seconds`
- **THEN** 导航条 SHALL 以可见样式高亮对应候选卡片，且不得改变视频播放状态

#### Scenario: marker 超出视频时长保护
- **WHEN** 前端开关已开启且发球事件 artifact 中的候选时间接近视频起点或终点
- **THEN** 工作台 SHALL 将候选卡片的跳转时间限制在有效视频时长内，避免播放器跳转到无效时间

#### Scenario: 候选展示信号摘要
- **WHEN** 前端开关已开启且发球候选事件包含 signal scores、候选片段时间窗或覆盖诊断
- **THEN** 候选卡片、tooltip、状态区域或相邻详情 SHALL 能展示底线站位、发球前静止、手臂或 ROI 峰值、后续回合激活、覆盖不足等摘要，而不阻塞播放器操作

## REMOVED Requirements

### Requirement: 发球候选导航条加载和降级状态

**Reason**: 该 requirement 整体只描述发球候选导航条的加载与降级行为；导航条改为默认不展示后它没有承载对象，继续保留会使规格要求一个默认不存在的 UI。

**Migration**: 产物侧的加载与降级契约继续由「发球事件加载和降级状态」约束——`serve_events` artifact 仍作为独立数据层加载，缺失、加载中、降级或失败均不影响基础视频播放与其它 overlay。需要恢复导航条时开启 `VITE_SERVE_RALLY_STRIP_ENABLED`，其加载与降级行为按「真实视频发球开始 marker」中的场景执行。
