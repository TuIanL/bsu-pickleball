## Why

当前 `joint_tracking_v2` 已能生成双摄球立体证据和 `reconstructed_ball_trajectory.v3`，但球路仍通过结果写盘后的非阻塞 post-stage 旁路生成，未稳定进入 Parent 的 `AnalysisPipelineResult.artifacts`。前端虽然已有 v3 球路页面，却因缺少 artifact URL/status 无法可靠加载；同时真实球链仍存在时间单位、采样步长、配对和 Production timing authority 未统一等问题，直接展示会把“已生成文件”误解为“可用球路结论”。

本 Change 将双摄球路从实验性旁路收敛为可审计、可展示、状态诚实的端到端能力：先修正真实数据链路的确定性错误，再使用现有 canonical timing/evidence 契约，最后把 v3 结果发布到 Parent 并接入前端球路页面和状态展示。

## What Changes

- 修正双摄球路真实数据路径中的确定性问题：`frame_stride` 与实际解帧不一致、毫秒/秒混用、最佳 Cam2 配对变量泄漏、B-Spline clamped endpoint、英尺到 km/h 的单位换算和真实视频尺寸读取。
- 将 `joint_tracking_v2` 的球检测与 Stereo Layer 接入现有 `CanonicalAnalysisClock`/`SynchronizedFrameBundle`，只消费 `available` 源帧，复用同一 source-frame decision、PTS、selection error 和 sync quality；移除生产路径对独立 `real_data_runner` smoke bridge 的依赖。
- 保留现有“候选集合 → stereo association → local tracker”的三级证据语义，确保 detector 每视角每 canonical tick 只运行一次，Stereo 不反向修改本地 tracker 状态。
- 为 Parent 增加可解释的球路阶段/状态遥测，使球路 artifact 完成或明确降级后，任务才进入最终完成态；球路失败不得伪装为 available，也不得覆盖已经有效的球员结果。
- 统一发布 `reconstructed_ball_trajectory.v3` 和 `multiview_ball_stereo_evidence.v1` 的 Parent-owned artifact URL、status、detail 和质量摘要；结果写盘顺序改为“球路阶段完成/降级 → 结果发布 → 任务完成”。
- 打通比赛库“球路”页和双摄分析结果：加载 v3 估算三维球路、落点、覆盖率、重投影质量和条件性平均球速；对 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY`、`UNAVAILABLE` 分层展示，不静默降级成假 2.5D。
- 在视觉分析/技术详情中增加球路能力状态和入口；第一版不把 v3 的球场坐标直接当成视频像素 overlay，双摄视频内球点投影另作为后续能力。
- 增加从单元测试、artifact/API 测试到真实双摄任务的验收门：至少覆盖 available、partial、unavailable/failed、历史单摄兼容和结果发布时序。

## Capabilities

### New Capabilities

- `multiview-ball-analysis-display`: 定义双摄球路从分析结果发布到比赛库、球路页面、视觉分析状态和技术质量信息的完整展示契约。

### Modified Capabilities

- `analysis-artifacts`: 增加双摄球立体 evidence/v3 trajectory 的 Parent artifact 引用、状态、质量摘要和兼容读取要求。
- `multiview-analysis-orchestration`: 将球路分析纳入 `joint_tracking_v2` 的可解释阶段顺序和终态语义，避免结果先完成、球路后写盘。
- `multiview-analysis-result-composer`: 要求 joint Composer 发布 Parent-owned 球立体 evidence 与 v3 trajectory，并在结果中补齐前端消费所需 URL/status/detail。
- `multiview-ball-stereo-evidence`: 要求生产双摄球链真正消费 canonical timing 和候选证据，不再以独立时间轴 smoke runner 作为正式入口。
- `ball-trajectory-visualization`: 补充 `multiview_estimated_3d` 的质量分层、状态展示和不可用语义，保持旧单摄 v1/v2 兼容。

## Impact

- 后端视觉链：`real_data_runner.py`、`real_data_analyze.py`、`segment_reconstruction.py`、`multiview_joint_executor.py`、`JointViewRuntime`/`CanonicalAnalysisClock`、Stereo association 与 artifact builders。
- 后端契约：`AnalysisArtifacts`、`AnalysisPipelineResult`、任务阶段遥测、Parent result composer、artifact API 和历史结果兼容读取。
- 前端：`analysisClient.ts`、`report.ts`、`BallTrajectoryPage.tsx`、`VisionPage.tsx`、`LibraryItemWorkspace`、双摄技术详情及相关测试。
- 运行行为：双摄任务完成时间会包含球路阶段；球路失败仍保留球员分析结果，但必须在任务和页面中明确显示降级原因。
- 不包含：TVCalib/PnLCalib 相机模型升级、球网非共面标定、相机机位优化、复杂空气动力学、双摄 v3 球路到 A/B 视频像素 overlay 的投影链。
