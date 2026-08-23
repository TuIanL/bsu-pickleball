## Context

当前系统有两条相互脱节的球路路径：单摄 `AnalysisPipeline` 会生成 raw/cleaned ball trajectory 和 bounce artifacts；`joint_tracking_v2` 则在球员协同结果写入后，通过 `_run_joint_ball_post_stage` 重新打开两路视频，生成 `multiview_ball_stereo_evidence.v1` 与 `reconstructed_ball_trajectory.v3`。后者不进入 Parent 的 `AnalysisPipelineResult.artifacts`，因此 `/result`、视觉分析页和比赛库球路页无法建立稳定的数据依赖。

现有球立体设计已经定义了 `BallViewCandidate`、跨视角 association、`BallStereoMeasurement`、canonical timing 和分层可用状态；现有 `BallTrajectoryPage` 也能理解 v3 产物。缺口主要在生产接线和确定性正确性：真实 runner 仍使用独立时间轴与宽松近邻匹配，部分时间单位/采样/样条端点逻辑不可靠，结果发布顺序又早于球路产物。

本 Change 只收口“真实双摄球链 → Parent artifact/API → 页面展示”这条链路。它依赖现有球场 Homography/virtual camera 和 v3 重建算法，但不在本 Change 内升级相机模型或重新设计物理模型。

## Goals / Non-Goals

**Goals:**

- 修复会直接破坏真实双摄球路结果的确定性错误，并为时间、坐标和质量字段建立一致单位语义。
- 让 joint 球检测、候选证据、Stereo association 和本地 tracker 使用同一个 `CanonicalAnalysisClock`/`SynchronizedFrameBundle` 决策。
- 让球路阶段纳入 Parent 的运行状态和完成顺序；球路可用、部分可用、不可用、失败都必须可解释。
- 在 Parent `AnalysisPipelineResult.artifacts` 中发布 v3 trajectory 和 stereo evidence 的 URL/status/detail，使前端不需要猜路径或扫描磁盘。
- 复用现有球路页面展示 v3 的估算三维、落点、覆盖率、质量和条件性球速，并保持单摄 v1/v2 兼容。
- 用真实双摄任务验证从 job 状态、result API、artifact API 到比赛库页面的闭环。

**Non-Goals:**

- 不在本 Change 内实现 TVCalib/PnLCalib 风格的完整相机自标定。
- 不加入球网非共面标定点、相机机位优化、镜头畸变联合优化或复杂 drag/Magnus 物理模型。
- 不把 v3 球场坐标直接转换成 A/B 视频像素 overlay；视频内双摄球点 overlay 需要单独的 projection artifact 和后续 Change。
- 不改变单摄 `BallTracker.update(frame)` 的既有行为和历史 v1/v2 产物语义。
- 不把球路不可用升级为整个球员分析任务失败。

## Decisions

### 1. 生产球链使用 canonical tick，而不是继续扩展 smoke runner

正式 joint 运行在现有 `CanonicalAnalysisClock` 生成的 `SynchronizedFrameBundle` 上处理球。每个 view 只在 `frame_status == available` 时消费真实帧，直接使用 bundle 的 source frame、source timestamp、mapped take timestamp、selection error、timing authority 和 sync quality。

每个 canonical tick 的顺序固定为：

```text
decode shared frame bundle
        ↓
ball detect/filter once per view
        ↓
snapshot local tracker predictor
        ↓
cross-view stereo association
        ↓
local BallTracker.update_from_candidates
        ↓
append immutable evidence / tracker sample
```

`real_data_runner` 保留为离线调试/回放入口，但不再作为正式 Parent 结果的唯一生产桥接。这样可以避免球链重新打开视频后丢失主分析已经确定的 PTS 与 source-frame decision。

备选方案是只修复 `real_data_runner` 并继续在 joint 结束后运行；该方案实现成本低，但会继续产生两个独立时间轴、重复解码和结果发布竞态，因此不采用。

### 2. 内部时间统一使用 seconds，证据字段保留明确的 milliseconds

内部 `Observation.t_sec`、段 duration、样条采样和速度计算统一使用 seconds。跨视角证据中的 `take_timestamp_ms`、`source_timestamp_ms`、`sync_error_ms` 保留 milliseconds，但字段名必须明确表达单位。所有转换只在边界处发生一次。

这同时修复 `frame_stride` 的语义：stride 表示要处理的真实 source frame 间隔，解码器必须实际跳过对应帧或按帧号 seek，不能只递增逻辑索引。Cam2 配对采用 source timestamp 的一对一关联，并受球侧独立时间门约束，不再把 ±200ms 作为无条件正式配对窗口。

### 3. 修复 spline 和质量指标后再发布 v3

球路重建继续使用现有 segment-level 低维曲线，但 clamped knot vector 和 `t=1.0` endpoint 必须满足标准 B-Spline 端点性质。重建单元测试锁定 `t=0`、`t=1`、partition of unity、endpoint anchor 和 bounce anchor。

速度计算明确使用 `ft → m → km/h` 的转换；v3 payload 同时保留 `reprojection_error_px`、`stereo_coverage`、`prediction_ratio`、`average_speed_validity` 等质量字段。质量门不满足时输出 `PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE`，不得用默认弧线或伪造球速填充。

### 4. 球路阶段先完成，再生成最终 Parent result

对于 `joint_tracking_v2`，顶层阶段扩展为：

```text
multiview-input-check
    → multiview-joint
    → multiview-ball-analysis
    → multiview-metrics
    → multiview-visualization
    → multiview-report
```

球员协同结果可以作为中间内存对象存在，但最终 `result.json` 必须在球路阶段完成或明确降级后写入。球路 post-processing 失败时，Parent 仍生成成功的球员结果，同时在球路 artifact 中写 `failed` 或 `unavailable`，并在阶段 detail 中说明原因。

如果当前 `multiview-progress-state-machine` 尚未归档，本 Change 需要将该阶段合并进同一阶段图；前端不得自行追加球路阶段。

### 5. Parent artifact 是唯一前端出口

Composer 负责把球路产物发布到 Parent namespace，并填充：

```text
reconstructed_ball_trajectory_json_path
reconstructed_ball_trajectory_url
reconstructed_ball_trajectory_status
reconstructed_ball_trajectory_detail

multiview_ball_stereo_evidence_json_path
multiview_ball_stereo_evidence_url
multiview_ball_stereo_evidence_status
multiview_ball_stereo_evidence_detail
```

已有历史任务可缺少新增字段；前端先读取 v3，若没有 v3 URL 再按既有规则读取单摄 v1/v2。artifact URL 必须指向 `/api/analysis/jobs/{parent_id}/artifacts/...`，不得把 JointRun 目录或 child job 暴露给产品页面。

### 6. 页面按“球路视图”和“视频 overlay”区分数据语义

第一版页面分工如下：

- `BallTrajectoryPage`：消费 `reconstructed_ball_trajectory.v3`，展示 estimated 3D 球路、落点、segment 质量、覆盖率和条件性球速。
- `VisionPage`：展示球路层的 available/partial/unavailable/failed 状态，并提供进入球路页的入口；不把 v3 的 court XYZ 当成 image pixel overlay。
- 双摄技术详情：可选展示 stereo evidence 的观测数、时间误差、回投误差和降级原因。

真正的 A/B 视频内球点需要另建 `multiview-ball-overlay` projection contract，使用相机 geometry 把 v3/证据重新投影到每个 view；本 Change 只保留现有单摄 ball overlay 行为。

### 7. 用分层测试和真实素材验收

测试顺序固定为：

```text
数学/单位单测
    → canonical tick 球链单测
    → composer/result/artifact API 测试
    → 前端 v3/状态渲染测试
    → 真实双摄端到端验收
```

真实验收至少需要一个可用或部分可用 v3 片段，以及一个明确不可用的片段。验收检查“任务完成后 result URL 可读、artifact 可读、页面可显示状态和返回导航”，而不是只检查 JSON 文件是否存在。

## Risks / Trade-offs

- **[Risk]** 将球路阶段纳入任务完成顺序会增加双摄任务耗时。→ **Mitigation:** 保留 `available/partial/unavailable/failed` 分层，阶段内记录进度和窗口范围；不因球路失败重跑球员链。
- **[Risk]** canonical tick 集成需要把 detector 输入接入现有 runtime，可能暴露视频帧尺寸或 detector 生命周期差异。→ **Mitigation:** 复用已有 per-view runtime 和 `BallTracker.update_from_candidates`，先用 candidate/evidence 测试锁定执行顺序。
- **[Risk]** 真实相机几何仍可能导致 v3 `UNAVAILABLE` 或高度不稳定。→ **Mitigation:** 页面显示覆盖率、回投误差和 validity；本 Change 不宣称 metric 3D 精度，并保留后续 Camera V2 Change 的边界。
- **[Risk]** 历史任务 result 没有新增 artifact 字段。→ **Mitigation:** 所有字段可选，前端按 v3 → v1/v2 → 空态顺序兼容读取。
- **[Risk]** 将 v3 误接入现有视频 overlay 会产生坐标语义错误。→ **Mitigation:** 首版显式分离球路地图与视频 overlay；没有 projection artifact 时禁止渲染 v3 视频球点。

## Migration Plan

1. 先完成单位、stride、配对、Spline endpoint 和速度换算修复，并补齐纯单测；不改变旧单摄产物。
2. 将 joint 球候选与 Stereo Layer 接入 canonical tick，保留旧 `real_data_runner` 作为离线工具和回滚路径。
3. 扩展 Parent 阶段图与 `AnalysisArtifacts`，让球路阶段完成/降级后再写最终 result，并发布 Parent-owned v3/evidence URL。
4. 更新前端 loader、类型、球路页、视觉分析状态和技术详情，补充 v3 质量分层与不可用提示。
5. 使用历史单摄、历史双摄、真实双摄 available/partial/unavailable 样本做兼容验收；确认失败时仍能查看球员结果。
6. 真实双摄验收通过后，才考虑移除正式路径对 smoke bridge 的依赖；若 canonical 集成暂时不稳定，保留 runner 仅用于诊断，不得把诊断产物标为正式 authoritative result。

## Open Questions

- `multiview-ball-analysis` 阶段是否需要在前端展开 Cam1/Cam2 子进度，还是只显示球路总进度与质量摘要？首版建议只显示总进度，技术详情显示两路计数。
- v3 `UNAVAILABLE` 时，球路页是否同时提供 raw candidate 调试入口？首版建议只提供明确原因和返回视觉分析入口，避免把诊断数据误当正式球路。
- 真实双摄任务的球路 post-processing 是否需要独立取消检查点？若单个 clip 超过 60 秒，建议沿用现有 cancellation token 并按窗口分段发布进度。
