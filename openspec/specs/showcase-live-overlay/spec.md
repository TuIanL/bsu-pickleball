# showcase-live-overlay Specification

## Purpose
TBD - created by archiving change showcase-mode-live-overlay. Update Purpose after archive.
## Requirements
### Requirement: 展示模式实时旁路生命周期

系统 SHALL 为 `display_mode=showcase` 的双摄录制创建独立的实时展示旁路，并 SHALL 将其生命周期绑定到当前双摄 CaptureTake，而不将旁路视为原始录制进程的一部分。

#### Scenario: 双摄录制启动后创建展示旁路

- **WHEN** 一个 `display_mode=showcase` 且 `camera_setup=dual` 的 Field Session 成功启动双摄录制
- **THEN** 系统 SHALL 为 cam_1 和 cam_2 创建实时展示 worker
- **AND** 系统 SHALL 返回可供展示屏订阅的展示运行 id 或等价引用
- **AND** 原始双摄 FFmpeg 录制 SHALL 继续使用既有录制流程

#### Scenario: 标准模式不创建展示旁路

- **WHEN** 一个 `display_mode=standard` 的 Field Session 启动双摄录制
- **THEN** 系统 SHALL 不创建 ShowcaseRuntime、实时模型 worker 或展示专用摄像头流
- **AND** 双摄录制行为 SHALL 与变更前一致

#### Scenario: 录制停止后关闭展示旁路

- **WHEN** 当前 CaptureTake 的双摄录制进入停止、取消或异常终态
- **THEN** 系统 SHALL 停止对应的展示 worker、队列和展示流订阅
- **AND** 展示流 SHALL 在旁路停止后返回可识别的终态或失效状态
- **AND** 系统 SHALL 不删除原始录制分段

### Requirement: 双路人体框实时叠加

展示旁路 SHALL 分别处理 cam_1 和 cam_2 的最新可用帧，并 SHALL 在输出帧上叠加可渲染的人体框、track ID 和检测置信度。

#### Scenario: 两路均检测到球员

- **WHEN** 两路 worker 均能读取视频帧并完成 YOLO 人体检测
- **THEN** cam_1 和 cam_2 展示流 SHALL 各自包含对应视角的人体框
- **AND** 每个可渲染框 SHALL 包含稳定的当前运行期 track ID 和置信度
- **AND** 一路的检测结果 SHALL NOT 被错误绘制到另一路画面

#### Scenario: 当前帧检测为空但轨迹短暂丢失

- **WHEN** 某一路当前推理帧没有可用人体检测但已有 track 尚未超过丢失阈值
- **THEN** 系统 SHALL 按既有轻量跟踪策略保留或平滑该 track 的展示状态
- **AND** 系统 SHALL 不创建新的虚假球员框

#### Scenario: 模型不可用

- **WHEN** YOLO 权重、运行依赖或推理设备不可用
- **THEN** 展示状态 SHALL 标记人体叠加为 `unavailable` 或 `degraded`
- **AND** 原始双摄录制 SHALL 继续
- **AND** 展示屏 SHALL 能回退到不带叠加的预览或显示明确的分析不可用状态

### Requirement: 有界低延迟帧处理

展示旁路 SHALL 使用受控的推理帧率和有界最新帧队列，优先限制端到端延迟，不得因推理变慢而无限积累待处理帧。

#### Scenario: 推理速度低于摄像头帧率

- **WHEN** worker 的推理耗时导致处理速度低于输入流帧率
- **THEN** 系统 SHALL 丢弃过期帧并优先处理最新可用帧
- **AND** 展示状态 SHALL 回显实际推理 FPS 或等价运行指标
- **AND** 展示流 SHALL 不持续累积旧画面延迟

#### Scenario: 展示客户端断开

- **WHEN** 展示屏断开某一路展示流
- **THEN** 系统 SHALL 释放该订阅资源
- **AND** 只要双摄录制仍在进行，展示 worker 和原始录制 SHALL 按各自引用计数继续或安全运行

### Requirement: 可选球点与短轨迹

展示旁路 SHALL 将球检测定义为可选能力，只在模型和运行状态可用时输出当前视角的球点与固定长度短轨迹。

#### Scenario: 球检测可用并连续观测

- **WHEN** 某一路球检测模型可加载，且 BallTracker 连续接受有效球候选
- **THEN** 该路展示帧 SHALL 绘制当前球点和最近固定长度的 image-space 短轨迹
- **AND** 球点 SHALL 带有可识别的观测置信度或状态

#### Scenario: 球检测不可用或没有有效候选

- **WHEN** 球模型不存在、依赖不可用、运行失败或当前没有有效球候选
- **THEN** 系统 SHALL 标记球叠加为 `unavailable`、`no_detections` 或 `degraded`
- **AND** 系统 SHALL 不绘制未经观测支持的连续球路
- **AND** 人体框展示和原始录制 SHALL 不因此停止

#### Scenario: 实时球路与正式球路分离

- **WHEN** 展示旁路输出实时球点或短轨迹
- **THEN** 该输出 SHALL 被标记为实时展示数据
- **AND** 系统 SHALL 继续将录制结束后的球路清洗、弹跳、重建和双摄融合交给现有正式分析流程

### Requirement: 展示运行状态

系统 SHALL 提供与 ShowcaseRuntime 绑定的状态读取能力，使操作屏和展示屏能够区分录制状态、预览连接状态、人体推理状态和球检测状态。

#### Scenario: 读取双路健康状态

- **WHEN** 前端读取活动展示运行状态
- **THEN** 响应 SHALL 至少包含展示运行 id、CaptureTake id、每个机位的连接状态、最近帧时间、实际推理 FPS、track 数量和降级原因
- **AND** 响应 SHALL 区分目标配置值与实际运行值

#### Scenario: 展示旁路异常但录制正常

- **WHEN** 展示旁路某一路发生断流、模型异常或资源错误且原始录制仍在运行
- **THEN** 状态 SHALL 反映该路异常
- **AND** CaptureTake 和双摄录制状态 SHALL 保持 recording
- **AND** 前端 SHALL 提供回退普通预览或重试展示流的可识别状态

