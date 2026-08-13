## 1. 历史素材输入准备

- [x] 1.1 实现 registered video PTS sidecar materializer，复用 `write_frame_timing_sidecar()`，以 `<registered_video_path>.pts.jsonl` 为固定输出，支持有效 sidecar 复用、临时文件写入和原子替换
- [x] 1.2 为 sidecar 增加与 registered video 绑定的校验和 provenance 摘要，检查 JSONL、frame index、PTS 单调性、有限性、frame count 及首尾时间，明确禁止 nominal FPS fallback
- [x] 1.3 增加面向历史 CaptureTake 的输入准备命令或 service，输出每一路视频、sidecar、读取统计和失败原因，并支持 `ct_6949bef776a5` 的两路 dry-run

## 2. 多锚点同步校准

- [x] 2.1 明确人工共同事件锚点输入格式，要求至少 3 组、推荐 4-6 组并覆盖视频前中后段，保存 reference camera、camera identity 和原始 camera-local PTS
- [x] 2.2 扩展现有 `calibrate_dual_camera_sync.py` 的校准输出与读取校验，生成 `dual_camera_sync_calibration.v1`，包含 offset、rate、drift、anchor count、residual、quality 和 valid interval
- [x] 2.3 将 residual、锚点数量、覆盖范围、rate、identity 和 valid interval 校验统一接入 authority 判定；自动 segment timing 推导结果固定为 `degraded`，不得手工升级为 `good`
- [x] 2.4 为 sidecar materialization、人工校准、非法 identity/interval、锚点不足和 degraded 阻断补充单元测试及结构化 diagnostics 断言
- [x] 2.5 实现 opt-in calibration workbench：双路 registered video、source PTS timing API、逐帧选择、锚点本地保存与 calibration CLI JSON 导出；不得直接写入 authoritative calibration

## 3. CaptureTrack 与 joint 输入索引

- [x] 3.1 实现历史 CaptureTake 的 idempotent registered video index repair，核对 CaptureTrack、session metadata、manifest、VideoService metadata、camera identity、slot 和 take directory
- [x] 3.2 在 repair 成功后回写 `video_id`、sidecar path、timing authority 及必要 provenance；对冲突、缺文件和多候选情况返回明确错误，不按 slot 猜测
- [x] 3.3 实现 `jointViewInputs` preflight，验证两路 registered video、source timing、sync calibration、court orientation、canonical frame reference 和 identity mapping 的完整性，并让 Parent 可仅凭持久化输入重建
- [x] 3.4 将 `resolve_sync_authority()` 作为创建和执行 authoritative joint run 的唯一 gate，只有 `joint_authoritative / good / true` 才允许 acceptance run，失败时持久化 sidecar/sync/input diagnostics

## 4. Joint debug trace 契约

- [x] 4.1 定义并实现 `joint_debug_trace.v1.json` 的 schema、writer 和 JointRun diagnostic artifact manifest，覆盖 canonical tick、两路 source frame/timestamp/status/selection error、bbox/footpoint、local/global identity、binding、prediction、guidance、detection origin、pre-gate、lock/tracking、canonical observation、fused position 和 recovery event
- [x] 4.2 在 `MultiViewJointRun` 的既有 canonical tick 上下文采集 trace，显式记录 unavailable/missing 状态，保证 trace 不影响 tracking、association、guidance、recovery 或 fusion 分支
- [x] 4.3 增加 `debug_trace_enabled` 配置并纳入 input/config signature，默认关闭；开启时仅当前 `joint_tracking_v2` JointRun 写 trace，`late_fusion_v1` 保持无 trace
- [x] 4.4 为默认关闭、显式开启、source frame unavailable、formal observation missing 和 late fusion 隔离场景补充测试，并验证现有 `fused_player_trajectory.v2` 与 recovery diagnostics 内容不变

## 5. Debug MP4 与 summary renderer

- [x] 5.1 实现独立 debug renderer，读取原视频、trace、`fused_player_trajectory.v2`、recovery diagnostics、canonical frame 和 timing mapping，按 trace 的 source frame decision 解码双路画面
- [x] 5.2 输出可播放的 debug MP4 与 summary JSON，展示双路画面、canonical court panel、timeline/status panel、authority 状态及 recovery funnel
- [x] 5.3 renderer 对缺失 trace、视频、timing mapping 或业务 artifact 返回具体 schema/input error，禁止重新运行 tracker、detector 或 source frame selection
- [x] 5.4 增加 renderer 的 source-frame 对齐、缺输入失败、diagnostic deletion isolation 和 summary zero-opportunity 测试

## 6. 真实 authoritative acceptance run

- [x] 6.1 对 take `ct_6949bef776a5` 的 `175_merged.mp4` 和 `174_merged.mp4` 物化并验证两份 PTS sidecar，确认两路 `FrameTimingProvider.authority == source_pts`
- [x] 6.2 使用人工提供的跨时段共同事件锚点生成 `timeline/sync_calibration.json`，记录原始 anchors、拟合参数、residual 和 quality；3 个锚点覆盖前、中、后段，`Cam175 residual RMS=8.684 ms`、`drift=-56.075 ppm`、`quality=good`
- [x] 6.3 修复并核验 take `ct_6949bef776a5` 的 CaptureTrack registered video index，运行完整 input preflight 和 `resolve_sync_authority()`，确认 `execution_mode=joint_authoritative`、`sync_quality=good`、`authoritative_joint_eligible=true`
- [x] 6.4 在 gate 通过后以 `debug_trace_enabled=true` 运行一次自然 `joint_tracking_v2`，保留原有 v2 trajectory、recovery diagnostics、debug trace、debug MP4 和 summary JSON，不注入 controlled dropout；本次为 `3.4s–60s` 的 online-only acceptance，未执行 F1 offline refinement
- [x] 6.5 报告真实运行中的 `recovery_opportunity=7705`、`guidance_generated=2477`、`guided_roi_invocation=2477`、`guided_recovery_success=4`、`base_recovered=14`，自然 recovery opportunity 非零且无解码错误

## 7. 回归与交付验证

- [x] 7.1 运行 timing、sync、multiview joint core、orchestration、artifact 和 renderer 测试，确认现有 `late_fusion_v1` 路径及非 debug joint 路径无新增逐 tick IO
- [x] 7.2 校验 debug artifacts 与业务 truth artifacts 的目录和 manifest 隔离，删除或重生成 debug 目录后原视频、trajectory、recovery diagnostics 和单视角 artifacts 保持不变
- [x] 7.3 为 authoritative preflight、sidecar provenance、calibration quality 和 trace schema 生成一份可审计的 acceptance summary，记录命令、输入路径、artifact 路径和最终 gate 结果
