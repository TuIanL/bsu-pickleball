## Why

当前上传分析和实时录制链路对视频帧率的处理不一致：前端存在 90fps/30fps 写死值，后端也有多个按固定帧数表达的时间窗口。不同设备可能以 24、25、30、50、60、90、120fps 拍摄，如果分析仍按隐含帧率计算，会导致时间戳、跟踪缓冲、静止球过滤、弹跳检测和可视化节奏偏离真实视频。

## What Changes

- 在上传视频创建分析任务时，让用户选择或确认源视频 FPS，并允许覆盖视频 metadata 读取结果。
- 在实时录制界面中为单摄和双摄录制提供 FPS 选择，不再把单摄写死为 90fps、双摄写死为 30fps。
- 在分析任务元数据/API 中保存用户确认的源 FPS，并在任务签名、任务摘要和产物 source metadata 中保留该值。
- 后端分析流水线统一计算 `effective_fps`：优先使用用户确认 FPS，其次使用视频 metadata FPS，最后使用安全兜底值。
- 后端所有时间敏感计算必须依据 `effective_fps` 运行：帧时间戳、轨迹缓冲、插值窗口、静止球过滤、弹跳事件间隔、overlay/小地图渲染窗口等。
- 将关键的固定帧数配置逐步改为秒语义，运行时按 `round(seconds * effective_fps)` 转为帧数，保留必要的环境变量兼容。
- 修复从录制视频进入分析任务创建页时无法仅凭 `videoId` 提交的问题，并用录制 session FPS 预填分析 FPS。

## Capabilities

### New Capabilities

- `source-fps-selection`: 定义用户选择/确认源视频 FPS、保存 FPS 元数据、后端计算 effective FPS，以及所有时间敏感分析按真实 FPS 换算的统一能力。

### Modified Capabilities

- `recording-session-control`: 录制开始请求和录制界面必须使用用户选择的 FPS，不得使用硬编码帧率。
- `video-analysis-job-flow`: 上传/录制视频创建分析任务时必须携带用户确认的源 FPS，并允许没有本地上传文件但已有 `videoId` 的录制视频创建任务。
- `analysis-job-orchestration`: 任务签名、任务保存和 worker 执行必须包含 FPS 选择，并传递给分析流水线。
- `player-tracking-engine`: 跟踪时间戳、身份缓冲、主球员窗口和轨迹插值等计算必须依据 effective FPS。
- `ball-tracking`: 球跟踪、静止候选黑名单和弹跳事件去重等时间敏感逻辑必须依据 effective FPS。

## Impact

- 前端：`NewAnalysisPage` 上传/录制分析入口、`CaptureConsolePage` 单摄/双摄录制控制、相关 TypeScript 类型和 API client。
- 后端 API/schema：`AnalysisUploadMetadata`、`AnalysisJobCreate`/`AnalysisPipelineOptions`、录制请求/响应模型和任务摘要持久化。
- 后端流水线：`AnalysisPipeline._run_tracking()`、job orchestration、tracking/identity/player lock/ball tracking/bounce detection/overlay writer 的 FPS 传递与时间窗口换算。
- Specs：新增 `source-fps-selection`，并为录制、分析任务、任务调度、球员跟踪和球跟踪补充 delta。
- 测试：覆盖上传 FPS、录制 FPS、metadata FPS fallback、effective FPS 计算、30/60/90/120fps 下时间窗口一致性。
