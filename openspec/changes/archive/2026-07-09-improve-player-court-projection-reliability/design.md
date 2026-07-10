## Context

已有 change（`fix-player-court-projection-and-minimap-bounds`）已完成 Phase 1-3 的核心改造：

1. `CourtGeometry` 新增 `tracking_bounds`（x=-4~24, y=-8~52），与 `court_bounds`（x=0~20, y=0~44）共存
2. `PlayerProjector` 输出扩展字段（`projection_status`, `footpoint_method`, `projection_confidence`）
3. `FootpointEstimator` 已支持 hybrid 模式（pose_ankle > bbox fallback）
4. `CourtPositionSmoother` 已实现 EMA + outlier + gap_hold
5. `MinimapVisualizer` 已使用 `court_to_pixel(bounds="tracking")` 渲染界外点
6. `VisualizationDataBuilder` 已通过 `_split_points()` 区分 minimap / heatmap 数据

但这些改造完成后，真实视频中仍然出现「底线球员投影到厨房区」的问题。根因是：

```
bbox_bottom_center 当 bbox 被画面底部裁切时
→ footpoint_y 远高于真实脚底（可能在膝盖或腰部高度）
→ homography 将空中点按地平面投影
→ court_y 产生 10-15 ft 的系统偏移
→ 球员从底线 (y≈2) 偏移到厨房区 (y≈15)
```

同时，缺少端到端的诊断工具，无法快速区分「脚点错」「单应性错」「标定错」「渲染错」。

## Goals / Non-Goals

**Goals:**
- 新增 projection debug overlay 视频与 JSONL 诊断日志，逐帧可追溯投影全链路
- FootpointEstimator 增加近端裁切感知，防止裁切 bbox 产生高置信度错误投影
- 新增标定质量诊断模块，对每次分析输出重投影误差、比例偏差等指标
- 统一前后端 SVG / minimap 的坐标边界与 viewBox

**Non-Goals:**
- 不做 PnP 三维重建
- 不做 camera intrinsic calibration（畸变校正）
- 不重写 YOLO / RTMPose / homography 计算核心
- 不改变热力图、移动距离、速度的统计逻辑
- 不修改 AnalysisPipeline 主流程结构

## Decisions

### Decision 1: 投影诊断独立于主 Overlay 视频

**选择**：新增独立的 `projection_debug_overlay.mp4` 和 `projection_debug.jsonl`，与现有 `analysis_overlay.mp4` 并行生成。

**理由**：
- Debug overlay 信息密度高（bbox + 脚点 + 投影坐标 + 球场网格回投），不适合混入面向用户的 analysis_overlay
- JSONL 格式便于 grep/awk 快速查询特定帧或 track 的投影链路
- 可通过配置开关控制是否生成，默认关闭以避免额外计算开销

**替代方案**：修改 analysis_overlay.mp4 增加 debug 信息 → 拒绝，用户看到的视频应该清爽

### Decision 2: 近端裁切检测——标记而非断言

**选择**：当 `bbox y2 > frame_height * 0.94` 且 footpoint_method 为 `bbox_bottom_center` 时，标记 `near_frame_bottom: true` + `bbox_clip_suspected: true`，projection_confidence 上限降至 0.35（正常 bbox default 为 0.7）。debug 字段命名使用 `near_frame_bottom` 和 `bbox_clip_suspected` 而非 `bbox_clipped`，因为系统无法绝对确定 bbox 真的被裁切（球员可能确实站得很近、脚在画面内）。

**理由**：
- `bbox_clipped` 是断言性命名，可能误导后续分析。`bbox_clip_suspected` 更诚实
- 不同视频分辨率下，裁切发生在画面底部固定比例区域（通常底部 5-6% 是视频播放器的进度条/边框区域）
- 绝对像素阈值在 1080p vs 4K 视频上不通用
- 置信度降级（而非直接丢弃）保留 bbox 作为最后手段的地位

### Decision 3: 不自动纠正坐标，只标记可疑点

**选择**：对于「投影位置与回合语义矛盾」（如发球方出现在厨房区、非厨房区内球员长时间静止等），只设置 `projection_status = "semantic_suspect"` 并降级 confidence，不做 bias correction 把点拉回预期位置。

**理由**：
- 回合状态判断（发球中 / 回合中 / 得分后）本身依赖投影坐标，存在鸡生蛋风险
- 自动纠正可能把真实异常站位（如球员真在厨房区违例）也改掉
- 标记可疑点 → 教练/分析人员可人工判断 → 后续版本可基于确认数据做 ML 纠正

### Decision 4: 标定诊断在 Pipeline 末尾独立运行

**选择**：`CalibrationDiagnostics` 在 `_run_calibration()` 完成后、`_run_tracking()` 开始前计算诊断指标，结果写入 `calibration_diagnostics.json` artifact。

**理由**：
- 标定是第一道门，标定错了后面全错
- 独立运行意味着诊断不影响 pipeline 主流程
- 诊断结论（good / suspect / bad）可供下游（footpoint、smoother）自适应调整阈值

### Decision 5: 诊断配置拆分为两个独立开关

**选择**：JSONL 诊断日志和 Debug Overlay 视频使用两个独立配置项：
- `enable_projection_debug_jsonl`（默认 `False`）：控制 `projection_debug.jsonl` 生成
- `enable_projection_debug_overlay`（默认 `False`）：控制 `projection_debug_overlay.mp4` 生成

**理由**：JSONL 成本低（每帧 ~300 bytes）、对排查很有用；overlay 视频需逐帧渲染（每帧 ~2ms 额外开销）。开发者经常只想开 JSONL，不想生成 debug 视频。

### Decision 6: JSONL 写入采用 line-buffered + 周期性 flush

**选择**：`ProjectionDebugWriter` 默认使用 line-buffered 模式写 JSONL，每 `flush_interval_frames`（默认 30）帧执行一次 `flush()`，异常/结束时强制 flush。

**理由**：逐帧 `flush()` 在长视频（10000+ 帧）上 I/O 压力大；纯内存缓存可能因异常丢失全部日志。30 帧间隔（约 1 秒 @ 30fps）在性能和数据安全间平衡。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 近端裁切阈值 0.94 在特殊画幅比（如竖屏）上可能误触发 | 阈值可配置，默认 0.94 针对 16:9 横屏；竖屏视频预计后续单独处理 |
| 标定诊断误报（标定实际可用但诊断标记为 bad） | 诊断只降级 confidence 和发起 warning，不阻断 pipeline |
| 四点标定重投影误差低但标定方向错误（near/far 颠倒） | 除角点重投影外，增加派生球场线点（网线两端、厨房线交点等）的投影校验和基线方向独立检测 |
| Debug overlay 增加 GPU 内存压力（额外渲染通道） | 独立配置开关，默认关闭，开启时复用已有 homography 和轨迹数据 |
| `semantic_suspect` 标记过于激进导致大量误报 | 第一版只标记最明显的矛盾（发球时 y 在厨房区），后续迭代逐步扩展 |
| 前端 SVG viewBox 修改可能破坏现有布局 | `trackingToSvg` 函数已存在，只需在 StructuredScatterPlot 中切换调用 |
| JSONL line-buffered 模式在进程 crash 时可能丢失最后 N 帧 | 异常处理中强制 flush，丢失量 ≤ flush_interval_frames（默认 30 帧，约 1 秒） |

## 数据流变化

```
现状（Phase 1-3 已完成后）:
Camera Frame → YOLO/Pose → FootpointEstimator(hybrid) → PlayerProjector → Smoother
  → Artifacts → VisualizationDataBuilder → MinimapVisualizer / PositionVisualizer
  → OverlayVideoWriter._draw_minimap() → analysis_overlay.mp4

本次 Phase 0-4 新增:
Camera Frame → YOLO/Pose → FootpointEstimator(near_clip_aware)
  → PlayerProjector(透传诊断字段)
  → Smoother(不变)
  → Artifacts(不变)
  → CalibrationDiagnostics(全新) → calibration_diagnostics.json
  → ProjectionDebugWriter(全新) → projection_debug_overlay.mp4 + projection_debug.jsonl
  → VisualizationDataBuilder(不变)
  → MinimapVisualizer(不变)
  → OverlayVideoWriter(不变)
  → Frontend SVG(切换到 trackingToSvg)
```

## Migration Plan

1. 新增 `projection_debug_writer.py` 和 `calibration_diagnostics.py` 为纯增量文件，不影响现有代码路径
2. `footpoint_estimator.py` 修改 `estimate()` 方法签名增加可选的 `frame_shape` 参数（向后兼容：缺省时不启用裁切检测）
3. 前端 `courtGeometry.ts` 已在上一 change 中添加 `trackingToSvg`，只需在 `StructuredScatterPlot.tsx` / `App.tsx` 确认调用
4. 配置项 `enable_projection_debug_overlay` 默认 False，零影响现有用户
5. 无需数据库迁移、无需 API 变更

## Open Questions

- 近端裁切阈值 0.94 是否需要在不同拍摄角度下动态调整？（当前：固定值 + 可配置）
- JSONL 诊断日志的文件大小——10000 帧 × 4 球员 ≈ 40000 行，约 20MB，是否可接受？（当前：可接受，后续可加采样参数）
- 标定诊断的「bad」阈值如何设定？重投影误差 > 5px？比例偏差 > 10%？（当前：第一版用经验阈值，后续基于多视频统计校准）
