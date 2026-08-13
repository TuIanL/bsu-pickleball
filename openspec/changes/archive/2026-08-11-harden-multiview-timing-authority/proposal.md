## Why

当前多视角执行器只验证同步 artifact 的结构合法性，尚未真正消费 `good / degraded / unknown` 的质量 gate；同时，视频缺少 PTS sidecar 时会回退到 nominal FPS，导致一个“可以运行”的结果被误认为“具有 authoritative joint timing”。P1 recovery 依赖可靠的 canonical tick，因此必须先把时间 authority、帧选择有效区间和 provenance 收敛成可执行契约。

## What Changes

- 新增多视角 timing authority 契约，区分 structural validation、quality gate 和 authoritative joint eligibility。
- 为最终注册分析视频物化并校验 PTS sidecar；保留 legacy nominal FPS fallback，但明确其只能用于兼容或降级路径。
- 让 `good / degraded / unknown / unavailable` 真实影响 joint execution mode、cross-view eligibility 和 diagnostics。
- 在 frame selection 中执行 `valid_start_seconds / valid_end_seconds` 校验，并区分无同步、超出校准区间、媒体越界、选择误差超限和 `no_new_frame`。
- 将 `source_timestamp_ms`、`mapped_take_timestamp_ms`、`selection_error_ms`、timing authority 与 sync quality 从 canonical clock 传递到 joint observation 和 v2 artifact。
- **BREAKING**：`joint_tracking_v2` 不再把 nominal FPS 或缺失同步映射的运行结果声明为 authoritative synchronized analysis。
- 不改变原始 TS 保留、录制终态和 MP4 合并失败恢复语义；不实现 P1 cross-view recovery 本身。

## Capabilities

### New Capabilities

- `multiview-timing-authority`: 定义多视角分析的 timing authority 来源、质量 gate、authoritative eligibility、PTS provenance 和诊断契约。

### Modified Capabilities

- `dual-camera-timestamp-alignment`: 补充最终注册视频的 PTS sidecar 物化、缺失/损坏时的 authority 状态，以及有效区间参与 frame selection 的要求。
- `multiview-synchronized-analysis-clock`: 要求 canonical clock 保留每路 source timing、映射误差和细分后的 frame status。
- `multiview-analysis-reliability`: 要求执行器实际组合 structural authority 与 quality gate，并将 quality 结果反映为 joint、degraded 或 single-view fallback。

## Impact

- 后端：`FrameTimingProvider`、`dual_camera_sync`、`CanonicalAnalysisClock`、`MultiViewJointExecutor`、joint observation/artifact adapters 和相关 storage/capture finalization 接线。
- 分析任务：新增 timing authority、sync gate、每 tick frame selection 和 fallback reason 诊断；历史单摄任务继续兼容 nominal FPS。
- 产物：扩展 `fused_player_trajectory.v2` 的 `view_observations` timing provenance；不覆盖既有原始 TS 或历史 artifact。
- 测试：增加 sidecar materialization、authority matrix、valid interval、selection status、source timing propagation 和 joint fallback 的单元/集成测试。
- 下游：P1 recovery Change 将把本 Change 输出的可信 `FrameSample` 作为输入；本 Change 不负责 guidance、identity recovery 或 recovery KPI。
