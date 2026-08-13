## Context

joint_tracking_v2 双摄分析（实测 job-3b411aefe6 / mvr_109696ea4110）暴露一条完整结果链路缺陷，根因均已用 trace 定量与最小实验证实：

1. **解帧语义错误**：`joint_view_runtime.py:48` 的 `cap.set(0, source_frame_index)` 把帧号当毫秒（`0 = CAP_PROP_POS_MSEC`）传给 OpenCV。实测 `set(0, 400)` 实际解码到 ≈帧 25；每 tick 仅前进 ~0.12 帧 → 检测框每 ~5-8 tick 才更新（trace 中 86% 相邻 tick bbox 完全不变），且整个 joint 分析检测跑在视频开头错误帧上。
2. **fused 轨迹缺时间戳**：fused trajectory v2 样本只有 `take_timestamp_ms`，无 `timestamp_seconds`。composer `fused_to_projected_tracks` 读 `timestamp_seconds` 默认 0.0 → 7739 条 tracks 时间戳全 0 → 速度/厨房停留指标全 0；前端 `videoOverlayHud.ts:176` 按时间窗口过滤（`ts > currentTime || ts < currentTime-3s`）→ 播放超 3 秒所有点被丢弃 → 小地图不渲染。
3. **joint compose 产物缺失**：`compose_joint_result` 产出的 `AnalysisArtifacts` 全空（无 child 可继承、未生成视觉层产物）→ 前端 `VisionPage` 的 tracking/pose/heatmaps 全部 unavailable。
4. **stage 误报**：`_build_aggregate_stages` 读 `viewRuns`（joint 模式创建后停 queued）判 A/B → 显示 failed。
5. **副摄窗口开头无映射**：sync 校准 `valid_start_seconds=3.4s`，clipStart=0 时前 3.4s cam_2 无有效映射 → debug replay 前段 UNAVAILABLE。

约束：不改前端展示链路（产物恢复后自动可用）；不破坏 late_fusion_v1；保持 debug renderer"不伪造帧"原则。

## Goals / Non-Goals

**Goals:**
- 修复 joint 解帧语义，使检测/跟踪运行在正确源帧上、检测框逐 tick 更新。
- 恢复 fused 轨迹时间戳，速度/停留指标与小地图正确。
- joint 结果产出/继承前端视觉层产物，框架/骨架/热力图可用。
- 聚合 stage 不再误报 A/B failed。
- 窗口开头副摄帧选择提供回退策略，debug replay 前段不黑屏。

**Non-Goals:**
- 不接入 RTMPose 骨架推理（joint 模式骨架产物仅显式标注不可用原因，接入属后续 change）。
- 不改动 `late_fusion_v1` composer 行为与产物。
- 不重构 debug renderer 的就近补帧策略（仅按 trace 的 fallback 标记渲染）。
- 不迁移历史已完成任务的产物（仅兼容读取）。

## Decisions

### 决策 1：解帧改为 `CAP_PROP_POS_FRAMES`（核心修复）

`JointViewRuntime.get_frame` 的 seek 参数由 `cap.set(0, ...)` 改为 `cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)`。

- **备选**：用游标连续读取（参考 debug renderer 的 `frame_cursors`）。被否决：连续读取要求 runtime 内部维护解码位置状态，而 runtime 可能被任意顺序 seek（recovery/refinement 复用 `get_frame`），显式帧号 seek 语义更稳、改动最小。
- **备选**：用 PTS 时间定位（`POS_MSEC` + 时间戳）。被否决：`source_frame_index` 是唯一权威帧标识，且与 trace/debug renderer 的帧号语义一致。
- 影响面：仅 `joint_view_runtime.py` 一行；修复后检测逐 tick 对齐，fused 轨迹坐标也随之正确（fused 轨迹坐标来自 frame_positions，但此前受错误帧污染）。

### 决策 2：fused v2 样本写入 `timestamp_seconds`

- `joint_artifact.write_fused_v2`（及 F0 轨迹构造处）为每个样本写 `timestamp_seconds = take_timestamp_ms / 1000.0`。
- composer `fused_to_projected_tracks` 读取优先级：`timestamp_seconds` → 缺失时回退 `take_timestamp_ms / 1000.0` → 仍缺失才 0.0（兼容历史产物，不迁移）。
- **备选**：仅在 composer 换算、不动 schema。被否决：前端及未来消费者拿到的 tracks 仍无时间戳语义；schema 加可选字段向后兼容，成本低。
- `timestamp_seconds` 为新增可选字段，不破坏 v2 schema 兼容（reader 归一化保持）。

### 决策 3：joint compose 视觉层产物

joint 模式无 child 单摄产物可继承，需从 joint run 自身产出：

- **tracking_overlay（框架）**：从 joint run 的 debug trace（`joint_debug_trace.v1.json`，每 tick 含 detections bbox / footpoint / player_id）聚合生成 tracking_overlay artifact，对齐单摄 `tracking_overlay.json` 契约。若无 debug trace（`debugTraceEnabled=false`），标记 unavailable 并注明原因。
- **heatmaps / scatter**：由 fused 轨迹直接生成（composer 已具备 `generate_heatmap` 能力，无额外依赖）。
- **player_render_trajectory（小地图）**：由 tracks 生成（现有单摄 render 逻辑可复用）。
- **pose_overlay（骨架）**：joint 模式未运行 RTMPose，无法生成真实骨架。MVP 行为：显式 unavailable + 结构化 reason（"joint_tracking_v2 未接入姿态推理"），前端展示"不可用"而非静默缺失。
- **备选**：joint run 运行时直接把 per-view overlay 写入 session（侵入跟踪主循环）。被否决：增加运行期负担与耦合；trace 已持久化全部 detections，事后聚合零侵入。

### 决策 4：聚合 stage 状态来源

`compose_joint_result` 构建 stage 时，joint 模式下 A/B 状态直接取 joint run 完成结论（`succeeded`），不再读 `viewRuns`。`late_fusion_v1` 路径保持读 viewRuns 不变。实现上给 `_build_aggregate_stages` 增加 joint 模式参数或在 joint 路径传入显式状态。

### 决策 5：窗口开头副摄回退

- **首选**：`CanonicalAnalysisClock` 在 canonical 时间早于 `valid_start_seconds` 时，用最近有效映射（offset/rate）外推 secondary 帧，`FrameSample.status=fallback` 并携带 reason。外推帧供分析使用，trace/渲染按 fallback 标记显示。
- **兜底**：外推帧解码失败或超出媒体范围时保持细分不可用（`unavailable_outside_valid_interval`），渲染器显示 UNAVAILABLE 面板与结构化原因。
- **备选**：保持现状 unavailable + 仅优化渲染提示。被否决：对"仅分析前 60s"的高频场景，前 3.4s 副摄数据丢失影响融合覆盖（实测该段 102 tick 全走 single_view_fallback）。
- 风险控制：外推帧内容若与 reference 明显错位（片头/黑屏），实现时需验证；若实测质量差，可退回兜底方案（该决策在 Open Questions 中标注验证点）。

## Risks / Trade-offs

- [解帧修复后帧对齐变化，历史结论不可比] → 解帧修复是正确性修复，A/B 对比需用修复后版本重新跑；文档中说明历史 joint 产物帧对齐不可信。
- [tracking_overlay 从 trace 聚合的格式与单摄契约差异] → 实现时对齐单摄 `tracking_overlay.json` 字段（bbox/footpoint/player_id/timestamp），前端消费无需改动。
- [外推帧内容错位（片头/黑屏）] → 实现后先用本 take 验证外推段；质量差则退回兜底 unavailable（决策 5 的验证点）。
- [`timestamp_seconds` 与既有 reader 的兼容] → 新增可选字段 + composer 双读回退，历史产物无需迁移。
- [stage 状态修正只影响 joint 路径] → 分支隔离，late_fusion 行为不变。

## Migration Plan

1. 部署后端修复（解帧 + composer + clock 回退）。
2. 历史 joint 产物无需迁移：composer 双读回退时间戳；缺视觉层产物的历史任务前端仍显示 unavailable（不造假）。
3. 回归验证：用本 take（job-3b411aefe6 同源双摄素材）重跑 joint 任务，核对：trace 检测框逐 tick 变化、速度非 0、小地图有轨迹、框架可用、stage 无 failed、debug replay 前段无黑屏。

## Open Questions

1. **窗口开头回退采用外推还是保持 unavailable？** 默认按决策 5 实现外推 + fallback 标记，但需在实现后用真实 take 验证外推帧质量（cam_2 前 3.4s 是否有有效画面）；若错位严重，回退兜底方案。
2. **tracking_overlay 的聚合源**：优先从 debug trace 聚合（零侵入）；若 trace 未开启（`debugTraceEnabled=false`），是否需要在 joint run 运行期顺带写 tracking_overlay（增加少量运行期产物）？倾向：仅 trace 开启时提供框架层，否则 unavailable + reason。
3. **pose_overlay**：本 change 只标注不可用原因；是否单独立 change 接入 RTMPose 骨架推理，由产品排期决定。
