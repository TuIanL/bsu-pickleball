## Context

P1-0 已建立 source PTS、canonical tick、frame selection provenance 和 sync authority 分层；P1-A 已建立双向 cross-view guidance、guided redetection、local/global identity continuity 与 recovery funnel。真实验收 take `ct_6949bef776a5` 的最终 registered MP4 已物化 `<video>.pts.jsonl`，并通过人工多锚点生成 `timeline/sync_calibration.json`，因此具备进入 `joint_authoritative` 的输入条件。

本 Change 分为两个相互衔接但职责独立的阶段：先准备和验证真实输入，再对成功的 joint run 做 opt-in 诊断可视化。输入准备产生可复现的 timing/sync artifacts；debug trace 只记录运行时证据，不成为新的业务真值来源。

## Goals / Non-Goals

**Goals:**

- 对历史 registered video 幂等物化并验证 PTS sidecar，保留 media 和原始 TS 不变。
- 使用人工共同事件锚点生成可审计的 `dual_camera_sync_calibration.v1`，由拟合 residual 自动决定质量。
- 提供一个开发/验收工具，让操作者在两路 registered video 上逐帧选择共同事件，并导出 camera-local source PTS anchors。
- 修复或恢复 CaptureTrack 到 registered video metadata 的索引关系，并在任务创建前验证 camera identity、calibration、orientation 和 sync mapping 一致。
- 只有两路 `source_pts`、sync `good` 且 resolver 返回 `joint_authoritative / True` 时，才执行 authoritative acceptance run。
- 为 `joint_tracking_v2` 提供默认关闭的 `joint_debug_trace.v1`，并基于同一 run 产出 debug MP4 与 summary JSON。
- 让 debug renderer 复用 trace 中的 source frame decision，绝不为画面重新运行 tracker 或重新选择 secondary frame。

**Non-Goals:**

- 不修改 tracking、guided recovery、global association、fusion 权重或 `late_fusion_v1` 语义。
- 不启动 P1-B offline refinement、GT 标注、controlled dropout 或正式 precision/recall 实验。
- 不把自动 segment timing 推导的 `degraded` 校准升级为 `good`。
- 不新增正式产品分析页面或对历史 CaptureTake 的原始视频重新编码；人工锚点工作台仅属于开发/验收工具。

## Decisions

### D1: Sidecar 绑定最终 registered video

PTS sidecar 固定使用 `<registered_video_path>.pts.jsonl` 命名，并由现有 `write_frame_timing_sidecar()` 通过 ffprobe 从最终用于分析的 video 读取 `best_effort_timestamp_time`。sidecar 采用临时文件加原子替换写入；已存在且通过校验的 sidecar 直接复用。这样 sidecar 的 authority 与 executor 实际打开的 media 一一对应，而不是与原始 TS 或 nominal FPS 混淆。

替代方案是直接在 joint executor 中实时调用 ffprobe，或把 PTS 放入数据库。前者会让长任务启动不可预测，后者会把大量逐帧数据塞进 SQLite；两者都不如旁车文件适合复现和审计。

### D2: 人工多锚点是 authoritative calibration 的唯一入口

使用现有 `calibrate_dual_camera_sync.py` 接受 camera-local seconds 的共同事件锚点，至少 3 个且跨越分析窗口，推荐 4-6 个。拟合 `offset + rate * reference_time`，由现有 residual threshold 自动生成 `quality`、`valid interval`、`drift_ppm` 和 `residual_rms_ms`。`generate_dual_camera_sync.py` 只允许作为结构/降级诊断工具，其固定 `degraded` 结果不得进入 authoritative acceptance。

替代方案是仅使用录制开始时间或只取一个开头锚点；它们无法验证长时间 drift，因此不能支持 `good` claim。

### D3: 输入索引恢复优先修复 CaptureTrack metadata

准备流程先读取 CaptureTake 的 session metadata 和 `registered_video_ids`，验证 VideoService metadata 的文件存在且路径与 take directory 一致。若 SQLite CaptureTrack 的 `video_id` 为空且 manifest 有明确 registered id，则通过 idempotent service operation 补齐 `video_id`、sidecar path 和 timing authority；若 metadata 有冲突、文件不可读或 camera identity 不一致，则结构化失败，不猜测或按 slot 重排。

替代方案是在每次任务创建时临时绕过数据库直接读取 manifest。这样虽然能启动一次任务，却会留下不可重启恢复的 Parent input，不符合 `jointViewInputs` 持久化契约。

### D4: resolver 是唯一 authoritative gate

输入准备、preflight 和 joint executor 都可以报告中间状态，但最终是否允许 authoritative run 只由 `resolve_sync_authority()` 结合两路实际 provider authority 决定。必须同时满足：两路 `source_pts`、结构校验通过、mapping quality `good`、valid interval 有效，且运行 tick 的 selection error 在 tolerance 内。失败时可以输出 preparation diagnostics 或 degraded/fallback 结果，但不得伪装为 P1 authoritative。

### D5: debug trace 作为 additive、opt-in 的运行诊断

新增 `joint_debug_trace.v1.json`，按 canonical tick 保存 source frame/timing、bbox/footpoint、local identity/epoch/track、binding visibility、prediction、guidance ROI/provenance、detection origin、pre-gate、lock/tracking status、canonical observation、fused position 和 recovery event。trace 由 `MultiViewJointRun` 的同一 tick 上下文采集，使用已有 bundle、guidance snapshot、ViewFrameResult、association update 和 fused state；它不能反向影响任何算法分支。

`debug_trace_enabled` 默认 false，进入 input/config signature。只有 Visual Acceptance Run 显式开启时才写 trace。trace 与 `fused_player_trajectory.v2`、`fused_diagnostics.json` 并列保存，业务报告仍以现有 v2 artifact 为准。

### D6: renderer 只消费既有运行证据

独立 debug renderer 读取两路原视频、trace、v2 trajectory、diagnostics、canonical frame 和 timing mapping，按 trace 的 source frame index 解码，不按相同 frame number 拼接。输出四区 debug MP4 和 summary JSON；如果 trace 或 authority contract 缺失，renderer 失败并指出缺口，不自动重跑分析。

### D7: 人工锚点工作台只生成 calibration input

新增 `/sync-calibration?take=<capture_take_id>` 开发工具页面。页面通过已登记的 `video_id` 获取两路视频流，并通过受保护的 timing API 获取对应 PTS sidecar 的 frame index/PTS 映射。逐帧按钮只改变 camera-local frame selection；“记录锚点”保存两路当前 PTS、frame index、标签和备注到浏览器本地，并可下载现有 `calibrate_dual_camera_sync.py` 接受的 JSON。页面不拟合 offset/rate、不写 `sync_calibration.json`、不修改 `quality`，下载后的文件仍由既有 CLI 和 authority resolver 判定。

## Risks / Trade-offs

- [人工锚点选错或过少] → 要求跨时段至少 3 个锚点，保存原始 anchors、拟合 residual 和 valid interval；不满足阈值就停止。
- [历史 CaptureTrack metadata 与 manifest 冲突] → 只允许明确一致的 registered video id 自动修复，冲突进入结构化 preflight failure。
- [sidecar 生成耗时或 ffprobe 失败] → 采用幂等缓存、临时文件和逐路失败诊断；不删除或覆盖原始媒体。
- [debug trace 增大磁盘和 IO] → 默认关闭，只在验收任务开启，并按 job config signature 隔离缓存。
- [trace 字段不足以重放某个 tick] → 将 source frame decision、availability/status 和 runtime provenance 作为必填字段；renderer 对字段缺失做 schema validation。
- [真实视频没有自然 recovery opportunity] → 诚实输出零 opportunity；controlled dropout 留到另一个明确的实验 Change。

## Migration Plan

1. 实现 sidecar materialization/validation 和人工 anchor calibration preparation，先以 `ct_6949bef776a5` 做 dry-run。
2. 修复或确认 CaptureTrack registered video index，并运行完整 preflight；失败时只记录 diagnostics，不创建 authoritative Parent。
3. 用 resolver 验证两路 `source_pts`、`good` 和 authoritative eligibility；若为 degraded，保留准备产物但停止本验收任务。
4. 成功后以 `debug_trace_enabled=true` 运行一次真实 `joint_tracking_v2`，保存 F0/v2 artifact 和 recovery diagnostics。
5. 实现 renderer、summary 与相关测试；默认关闭 trace，验证 `late_fusion_v1` 和非 debug joint 路径无新增 IO。
6. 回滚时关闭 debug trace 或删除该 JointRun 的 debug 目录；不删除 sidecar、sync calibration、原始视频或既有业务 artifact。若输入准备失败，任务保持未创建或进入明确 fallback，不修改算法。

## Open Questions

- 真实 take 的两路 calibration artifact 是否已经存在且能与 camera 175/174 绑定；若不存在，本 Change 只能完成 timing/sync preparation，不能启动 joint run。
- CaptureTrack metadata 修复是否应复用现有 capture finalizer 的 registration helper，还是新增一个专用 idempotent repair service；实现时应优先复用已有 service ownership。
- debug MP4 的输出编码器和默认帧率是否沿用现有 overlay writer；第一版只要求本地可播放和像素内容正确，不冻结产品发布编码参数。
