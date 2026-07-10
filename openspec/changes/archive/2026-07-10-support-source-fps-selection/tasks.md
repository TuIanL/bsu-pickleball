## 1. 数据模型与 API 契约

- [x] 1.1 在前端 `AnalysisUploadMetadata` / 分析任务请求类型中新增 `sourceFps`，并设置合理默认值与校验范围
- [x] 1.2 在后端 `AnalysisUploadMetadata`、`AnalysisJobCreate`、`AnalysisJobSummary` 或 pipeline options 中新增源 FPS 字段
- [x] 1.3 更新 API client 的 `createAnalysisJob()` 请求序列化，确保上传和录制来源都传递 `sourceFps`
- [x] 1.4 更新 `analysis_signature()`，将源 FPS 纳入任务输入或配置签名
- [x] 1.5 更新旧任务/旧 metadata 的解析兼容，缺失源 FPS 时不破坏已有 job list/report 读取

## 2. 前端 FPS 选择

- [x] 2.1 在上传分析页面新增 FPS 控件，提供 24/25/30/50/60/90/120 和自定义输入
- [x] 2.2 在上传分析提交逻辑中要求 `sourceFps` 有效，并随任务创建请求提交
- [x] 2.3 修复从录制 `videoId` 进入分析页面时的提交条件，允许没有本地 `selectedFile` 也能创建任务
- [x] 2.4 从录制 session 预填 `sourceFps`，并允许用户覆盖
- [x] 2.5 在实时录制控制台为单摄录制新增 FPS 选择状态，替换硬编码 `fps: 90`
- [x] 2.6 在实时录制控制台为双摄同步录制复用/新增 FPS 选择状态，替换硬编码 `fps: 30`
- [x] 2.7 更新相关前端测试，覆盖上传 FPS、录制 FPS 和录制视频创建分析路径

## 3. 后端 effective FPS

- [x] 3.1 在分析流水线中新增集中 helper：校验源 FPS、读取 metadata FPS、计算 `effective_fps`
- [x] 3.2 修改 `_run_tracking()` 签名和调用链，从 worker/API 接收用户源 FPS
- [x] 3.3 用 `effective_fps` 替换 `_run_tracking()` 内分散的 `raw_fps`/`fps if fps > 0 else 30.0` 时间敏感 fallback
- [x] 3.4 确保 `TrackingResult`、pose overlay、ball artifact、analysis artifact source metadata 写入 `effective_fps`
- [x] 3.5 在诊断信息中记录 `fps_source`、`user_source_fps`、`metadata_fps` 和 `effective_fps`
- [x] 3.6 更新自动分析录制任务的创建逻辑，将录制 session FPS 传入分析任务

## 4. 秒语义窗口换算

- [x] 4.1 新增 `frames_for_seconds(seconds, fps, minimum=1)` 等公共 helper，并添加单元测试
- [x] 4.2 为主球员选择窗口增加 seconds 派生配置，并按 `effective_fps` 传入 `PrimaryPlayerSelector`
- [x] 4.3 为 `PlayerIdentityManager` 的 lost/inactive/interpolation buffer 增加 seconds 派生配置，并按 `effective_fps` 换算
- [x] 4.4 为 `PlayerLockManager` 的 bootstrap、lost grace、lost max 等时间窗口增加 seconds 派生配置或运行时换算
- [x] 4.5 为 `BallTracker` 的 stationary blacklist、missing window 等时间窗口增加 seconds 派生配置或运行时换算
- [x] 4.6 确认 `BounceDetectorConfig(fps=...)` 始终接收 `effective_fps`，事件间隔按真实 FPS 换算
- [x] 4.7 更新 overlay/minimap/visualization 调用点，保证与 `smooth-minimap-player-motion` 使用同一个 `effective_fps`
- [x] 4.8 保留旧 frame-based 环境变量兼容，并新增 seconds 环境变量优先级

## 5. 测试与验证

- [x] 5.1 为 effective FPS 优先级编写后端单元测试：用户 FPS > metadata FPS > 30fps fallback
- [x] 5.2 为任务签名编写测试：相同 video/calibration 但不同 FPS 产生不同签名
- [x] 5.3 为 tracking timestamp 编写测试：60fps 第 120 帧时间戳约为 2 秒
- [x] 5.4 为 identity/primary/player lock 的秒窗口换算编写 30/60/90/120fps 参数化测试
- [x] 5.5 为 ball tracking 静止黑名单和 bounce event gap 编写 FPS 参数化测试
- [x] 5.6 为录制启动请求编写前端测试，确认单摄/双摄发送用户选择 FPS
- [x] 5.7 为上传分析页编写前端测试，确认 `sourceFps` 随 create job 请求提交
- [x] 5.8 运行相关前后端测试套件，并记录验证命令与结果

## 6. 文档与回归检查

- [x] 6.1 更新后端 README 或配置说明，解释 `sourceFps`、`effective_fps` 和 seconds 配置
- [x] 6.2 更新录制/上传界面文案，避免暗示系统会强制重编码为所选 FPS
- [x] 6.3 检查分析产物 JSON，确认 `fps` 字段均为 effective FPS 而不是旧 fallback
- [x] 6.4 手动验证 30fps、60fps、90fps 视频的分析时间戳和关键事件位置不随硬编码默认值漂移
