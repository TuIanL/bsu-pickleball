## Context

当前录制链路分为前端选择、API 请求模型、录制服务和 FFmpeg 进程四层。`CaptureConsolePage` 的 `recordingFps` 同时用于单摄录制和双摄同步录制；旧的 `App.tsx` 录制入口也仍保留 FPS 下拉框。后端 `RecordingStartRequest` 与 `SyncStartRequest` 目前默认 30fps 且允许到 120fps，单摄 `Recorder.start()` 函数签名还残留 90fps 默认值。

这个变更的约束很明确：采集硬件无法稳定支撑 90fps，因此 60fps 要成为录制默认值和最高支持值。分析上传的源视频 FPS 选择不属于本次录制能力收敛范围，仍可表达外部视频的实际帧率。

## Goals / Non-Goals

**Goals:**
- 让单摄与双摄录制默认以 60fps 启动。
- 从录制 UI 中移除 90fps/120fps，避免用户误选高负载录制参数。
- 在后端 API 合同层拒绝 `fps > 60` 的录制请求，防止绕过前端。
- 清理录制器函数签名中的 90fps 遗留默认值。
- 用测试覆盖单摄/双摄录制请求的 60fps 合同。

**Non-Goals:**
- 不改变上传视频分析页面对源视频 FPS 的表达能力；外部视频可能仍是 90fps 或 120fps。
- 不新增自动降帧、转码、硬件性能检测或摄像头能力探测。
- 不改变已完成历史录制 session 中保存的 FPS 值。

## Decisions

1. 后端使用硬上限而不是仅隐藏前端选项。
   - 选择：将 `RecordingStartRequest.fps` 与 `SyncStartRequest.fps` 的校验上限设为 60，默认值设为 60。
   - 原因：只改 UI 无法防止测试脚本、旧客户端或手工 API 请求提交 90fps。
   - 替代方案：前端将 90fps 显示为“不推荐”。该方案仍可能让硬件进入不可承载状态，不采用。

2. 前端录制入口保留低帧率选项，但最高值为 60。
   - 选择：录制下拉框保留 `24/25/30/50/60`，默认选中 60。
   - 原因：部分摄像头或场景可能需要低帧率录制，但用户明确希望落实 60fps 选项并避免 90fps。
   - 替代方案：只允许 60fps。该方案会移除低负载回退选项，不利于兼容弱设备或低带宽摄像头。

3. 不把分析源 FPS 选择同步收紧。
   - 选择：只修改实时录制相关入口，不修改上传/分析元数据中用于描述已有视频的 FPS 选项。
   - 原因：录制硬件限制不等于外部视频源限制；分析流程需要保留真实源 FPS 表达能力。
   - 替代方案：全站移除 90fps/120fps。该方案会误伤非录制视频分析，不采用。

## Risks / Trade-offs

- [Risk] 某些调用方依赖提交 90fps 录制请求。
  → Mitigation: 本变更在 proposal 中标记为 breaking，并通过 Pydantic 校验返回清晰的请求错误。

- [Risk] 摄像头实际输出帧率可能不是请求的 60fps，因为当前 FFmpeg 单摄路径偏向 copy/passthrough。
  → Mitigation: 本变更约束的是录制请求合同和 session metadata，不引入重编码强制帧率，避免增加 CPU 压力。

- [Risk] 旧入口 `App.tsx` 与新控制台 `CaptureConsolePage.tsx` 同时存在，可能出现配置漂移。
  → Mitigation: 两处录制入口同步更新默认值和可选列表，并在任务中要求全仓搜索 90/120 录制选项。
