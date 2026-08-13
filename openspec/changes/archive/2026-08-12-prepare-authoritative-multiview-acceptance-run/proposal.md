## Why

P1-0/P1-A 的双摄 timing authority、canonical clock 和在线恢复链路已经具备，但历史真实 CaptureTake 尚未物化 registered video 的 PTS sidecar，也没有经过多锚点拟合的 `sync_calibration.json`。因此真实素材目前只能进入 fallback/degraded 路径，无法进行可信的 `joint_authoritative` 验收。现在需要先把一组真实 take 升级为可审计的 authoritative 输入，再观察自然视频中的跨视角恢复行为。

## What Changes

- 为历史双摄 CaptureTake 提供 registered video PTS sidecar 的物化与校验流程，禁止 nominal FPS fallback 被误报为 source timing。
- 支持使用跨越视频时段的人工共同事件锚点生成 `dual_camera_sync_calibration.v1`，由 residual 和 anchor 数量自动判定 `good`/`degraded`，禁止手工强制 good。
- 提供一个仅用于验收准备的双路逐帧同步标注工作台，读取 registered video 的 source PTS，帮助人工记录共同事件 anchors，并导出给现有 calibration CLI 的原始输入。
- 在真实 take 准备阶段校验 CaptureTrack、manifest、registered video、sidecar、camera identity 和 calibration 的一致性；必要时从已有 session metadata 恢复缺失的视频索引。
- 以 `resolve_sync_authority()` 作为最终门控，只有 `joint_authoritative / good / True` 才进入 P1 authoritative acceptance run。
- 为 `joint_tracking_v2` 增加 opt-in 的 `joint_debug_trace.v1` 诊断产物，保存逐 canonical tick 的 source frame、timing、bbox、local/global identity、binding、guidance、recovery 和融合状态。
- 使用现有 joint run 消费 trace、v2 trajectory 和原视频生成 debug MP4 与 summary JSON；不重新运行 tracker，不改变 P1-A、`late_fusion_v1` 或业务真值 artifact 的语义。
- 默认关闭 debug trace，并将开关纳入任务配置/签名，避免正式运行产生不必要的逐 tick IO。

## Capabilities

### New Capabilities

- `multiview-visual-acceptance`: 定义真实 authoritative joint acceptance run、opt-in debug trace、debug MP4 和 summary report 的输入、输出与验收边界。

### Modified Capabilities

- `multiview-timing-authority`: 增加历史 registered video sidecar materialization、provenance 校验和失败时的结构化准备结果。
- `dual-camera-timestamp-alignment`: 明确人工多锚点 calibration 的生成、valid interval、residual 质量判定和历史 take remediation 语义。
- `multiview-analysis-input-contract`: 允许从 capture session manifest 恢复缺失的 registered video index，同时保持 camera identity、calibration、orientation 和 sync authority 的严格门控。
- `multiview-fusion-run`: 增加 joint run 的 opt-in debug trace 输出约束，保持 `late_fusion_v1` 和现有融合产物不变。

## Impact

- 影响 `backend/app/services/frame_timing_provider.py`、`dual_camera_sync.py`、`multiview_coordinator.py`、`multiview_joint_executor.py`、CaptureTrack/manifest 解析和 multiview artifact 输出。
- 新增 backend debug/diagnostic artifact、视频渲染脚本及相关测试；新增一个不参与正式分析产品流程的 calibration workbench 页面。
- 已对真实 take `ct_6949bef776a5` 提供 3 组跨时段人工共同事件锚点；本 Change 的短片验收窗口为 `3.4s–60s`，全程约 `699s` 分析尚未执行。
- 不修改 tracking、association、guidance、fusion 算法，不启动 P1-B，不引入 GT 或 controlled dropout。
