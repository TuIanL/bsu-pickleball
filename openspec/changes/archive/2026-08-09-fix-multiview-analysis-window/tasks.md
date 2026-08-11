## 1. 窗口契约与编排

- [x] 1.1 增加统一的分析窗口解析/校验工具，规范 `[start_ms, end_ms)`、视频边界裁剪、pre-roll/post-roll 和 requested/decoded range 结构。
- [x] 1.2 调整 `MultiViewAnalysisCoordinator`，确保 Parent、late fusion child 和 joint Parent 都持久化窗口；secondary child 继续通过权威 sync mapping 换算实际媒体范围。
- [x] 1.3 补齐窗口非法、窗口超出视频边界和缺少 sync mapping 时的结构化诊断，禁止静默退化为全视频分析。
- [x] 1.4 修正窗口任务的 progress 分母和范围元数据，区分窗口内计划帧数、实际处理帧数和源视频总帧数。

## 2. late fusion 与 Pipeline

- [x] 2.1 核对并补强 `SingleViewAnalysisExecutor` 到 `AnalysisPipeline` 的窗口传递，确保两个 child 使用各自正确的媒体时间轴范围。
- [x] 2.2 让 Pipeline 的 tracking、轨迹后处理、指标计算和位置可视化统一使用 requested clip；预热帧只用于状态初始化，不进入正式统计。
- [x] 2.3 在 Pipeline 结果和 artifact manifest 中写入 `requested_clip`、`decoded_range`、`processed_frame_count`、`source_frame_count` 等诊断字段。

## 3. 分析叠加视频

- [x] 3.1 为 `OverlayVideoWriter.write()` 增加窗口/帧范围参数，窗口启用时从有效起始帧 seek，并在结束帧停止读取。
- [x] 3.2 使叠加视频只输出 requested clip，记录 `output_time_origin_ms` 和实际首尾源帧，保持与源视频时间轴可追溯。
- [x] 3.3 保证未携带窗口时叠加视频仍完整读取源视频，并覆盖边界 seek、空窗口和短视频场景。

## 4. joint tracking

- [x] 4.1 扩展 `MultiViewJointExecutor`，将 Parent 窗口转换为 reference frame 的 requested/decode 边界，并保留 pre-roll/post-roll 语义。
- [x] 4.2 扩展 `MultiViewJointRun.run()`，只遍历窗口内 canonical ticks；无窗口时保持现有从第 0 帧到末尾的行为。
- [x] 4.3 确保 joint 的预热 tick 可以更新 tracker 状态但不进入正式融合 sample、指标分母或用户可见轨迹统计。
- [x] 4.4 确保 secondary frame 仍由 `CanonicalAnalysisClock` 使用既有 sync mapping 配对，并记录窗口内映射诊断。

## 5. 前端与结果展示

- [x] 5.1 为 `MultiViewAnalysisSetupPage` 和 `analysisClient` 增加窗口请求回归测试：勾选时发送毫秒范围，未勾选时不发送残留范围。
- [x] 5.2 在分析任务/详情结果中展示用户请求窗口，并在诊断信息中区分实际解码范围与源视频总时长。
- [x] 5.3 确认窗口叠加视频的 `output_time_origin_ms` 被前端正确解释，不把短 artifact 当作从源视频 0 秒开始的完整视频。

## 6. 测试与验证

- [x] 6.1 增加 Coordinator 的 Parent/child 窗口持久化、secondary sync offset 映射和边界校验测试。
- [x] 6.2 增加 Pipeline/Overlay 的合成短视频测试，断言窗口外帧不会被跟踪或写入叠加视频。
- [x] 6.3 增加 `MultiViewJointRun` 的窗口 tick 边界、预热排除和无窗口兼容测试。
- [x] 6.4 运行相关 Python/TypeScript 测试、前端构建，并检查一次真实双摄短窗口任务的 Parent/child/result metadata。

> 验证备注：自动化测试和前端构建已完成；当前工作区没有可安全执行的、同时具备双路视频、标定和有效同步 authority 的真实 CaptureTake，因此真实双摄短窗口任务的运行时检查留待接入该素材后执行。
