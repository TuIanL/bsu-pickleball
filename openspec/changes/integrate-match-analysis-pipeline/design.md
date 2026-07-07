## Context

当前 `AnalysisPipeline` 中球轨迹与弹跳检测逻辑已半嵌入式运行：

- **`_run_tracking()`** 内同时承担人体检测/跟踪/投影/身份管理/姿态估计（~330 行）和球检测/轨迹累积/后处理（~100 行），方法总行数超过 400
- **`_finalize_ball_analysis()`** 已统一处理三条路径（有视频+标定、有视频无标定、无视频）下的 artifact 写入和阶段记录，但创建的三个阶段中包含面向内部的 `ball-detection`，且未调用 `_notify_progress()`
- **Artifact 槽位**（`StorageService` 路径、`AnalysisArtifacts` 字段、`routes_analysis.py` 路由）已完整预留，但 `ball_overlay.json` 从未被写入
- **失败行为**：球检测运行时异常会静默禁用后续帧的球检测（`ball_tracker = None`），但缺少可配置的 strict mode 来控制是否升级为 pipeline 失败
- **配置**：`enable_ball_detection` 和 `enable_bounce_detection` 已存在，但无 `ball_analysis_strict`

本次变更的目标不是"从零接入"，而是**收敛**：将已嵌入的逻辑模块化、补齐缺失产物、让球/弹跳阶段对前端和调试者可观测。

## Goals / Non-Goals

**Goals:**
- 补齐 `ball_overlay.json` 产物（帧级球检测叠加数据）的写入与 API 读取
- 将 pipeline stages 从三个（含 `ball-detection`）收敛为两个用户可见阶段（`ball-trajectory` + `bounce-detection`）
- 为两个新增阶段增加完整的 counters 和 `_notify_progress()` 回调
- 新增 `PICKLEBALL_BALL_ANALYSIS_STRICT` 配置（默认 `false`），控制球分析异常是否拖垮 pipeline
- 从 `_run_tracking()` 中提取 `_process_ball_frame()` 和 `_run_bounce_detection()`，引入局部 `_BallRunContext`
- 新建 `app/schemas/ball.py` 提供球分析产物的 Pydantic 模型
- 在 metrics summary 中增加球轨迹与弹跳点摘要字段
- 保持现有人体 tracking / pose / serve 流程不受影响

**Non-Goals:**
- 不创建独立的 `_run_ball_tracking()` 视频循环（保留单视频读取 pass）
- 不重新实现球检测算法、轨迹清洗算法或弹跳检测算法
- 不生成 `analysis_overlay.mp4` 标注视频、小地图、热力图或散点图
- 不修改 `detections.jsonl`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json` 的 schema
- 不引入 Good-Pickleball 的 upper/lower player identity 体系
- 不重新设计 `AnalysisArtifacts` 或 `StorageService` 的接口

## Decisions

### D1: `ball_overlay.json` 只包含有球分析记录的抽样帧（方法 A）

**决策**: `ball_overlay.json` 的 `frames` 数组只包含球检测实际运行且有候选/缺失记录的抽样帧，不强制补全每个 `frame_index`。

**理由**:
- 与 `tracking_overlay.json` 的现有风格一致（只记录可绘制对象）
- `ball_overlay.json` 主要用途是画叠加层，不是做逐帧时间轴索引
- 缺失帧信息已由 `ball_trajectory.json` 的逐帧 sample 和 counters 表达
- 避免大文件膨胀（60fps × 10 分钟 = 36,000 条 null 记录）

**补充**: 顶层增加 `source` 和 `coverage` 元数据字段，弥补可索引性问题：
```json
{
  "source": { "frame_stride": 2, "processed_frame_count": 500, "fps": 60.0, "width": 1920, "height": 1080 },
  "coverage": { "overlay_frame_count": 318, "missing_frame_count": 182, "detection_rate": 0.636 }
}
```

**Schema 位置**: 新建 `app/schemas/ball.py`，与内部算法 schema（`pickleball_game_analysis/schemas.py`）分离。前者是 API artifact 稳定契约，后者是内部算法数据结构。

**Payload builder 位置**: 在 `detection_writer.py` 中新增 `build_ball_overlay_payload()`，与已有的 `build_raw_trajectory_payload()`、`build_cleaned_trajectory_payload()`、`build_bounce_events_payload()` 保持一致。

---

### D2: 阶段收敛为 `ball-trajectory` + `bounce-detection`（选项 1）

**决策**: 用户可见 stages 只保留两个：

| Stage | 职责 |
|-------|------|
| `ball-trajectory` | 球检测、候选筛选、轨迹采样、raw trajectory 写入、ball_overlay 写入、detections.jsonl 写入 |
| `bounce-detection` | 轨迹清洗、短缺失插值、弹跳点检测、cleaned_ball_trajectory 写入、bounce_events 写入 |

移除独立的 `ball-detection` 阶段（当前 `_finalize_ball_analysis()` 中创建）。

**理由**:
- `ball-detection` 是 `ball-trajectory` 的内部步骤，用户关心的是"有没有生成球轨迹"，不是"YOLO 每帧有没有跑"
- `trajectory-cleaning` 也是内部步骤，虽然 `cleaned_ball_trajectory.json` 是 artifact，但不是每个 artifact 都必须对应一个 stage
- 前端阶段数量不会膨胀，调试信息通过 counters 保留

**替代方案考虑**:
- 选项 2（三个阶段含 `trajectory-cleaning`）：过于琐碎，反应用户不关心的内部实现细节
- 选项 3（保留原三阶段）：`ball-detection` 名称暴露了具体技术实现

---

### D3: 单一 `PICKLEBALL_BALL_ANALYSIS_STRICT` 开关

**决策**: 使用一个配置项控制球分析链路的失败升级行为，不拆分为独立的 `ball_detection_strict` 和 `bounce_detection_strict`。

**理由**:
- 弹跳检测依赖球轨迹，若球轨迹失败则弹跳检测自动 skipped —— `bounce_detection_strict` 仅在自己独立异常时触发，而这种情况（纯算法崩溃）极其罕见
- 单一开关表面更小、概念更清晰
- 如果未来需要调试弹跳检测器本身的独立 strict 行为，可以再扩展

**失败行为矩阵**:

| 情况 | 默认 (`false`) | strict=`true` |
|------|----------------|----------------|
| 球模型缺失 | ball-trajectory skipped, bounce-detection skipped | pipeline failed |
| 球模型加载失败 | ball-trajectory unavailable, bounce-detection skipped | pipeline failed |
| 球检测中途异常 | ball-trajectory partial/unavailable, bounce-detection skipped | pipeline failed |
| 弹跳检测异常 | ball-trajectory available, bounce-detection unavailable | pipeline failed |
| `no_candidates` | bounce-detection done (no_candidates) | 不失败（永远不算异常） |
| 视频读取失败 | pipeline failed | pipeline failed（不受 strict 影响） |
| tracking 主流程失败 | pipeline failed | pipeline failed（不受 strict 影响） |

---

### D4: 保留单视频循环，提取 `_process_ball_frame()` + `_run_bounce_detection()`

**决策**: 不从 `_run_tracking()` 中创建完全独立的 `_run_ball_tracking()` 视频读取循环。而是提取逐帧球处理逻辑为 `_process_ball_frame()`，提取后处理逻辑为 `_run_bounce_detection()`，保留单视频读取 pass。

**理由**:
- 完全独立的 `_run_ball_tracking()` 需要重新打开视频、重复 court-view gate / ROI / timestamp / stride 逻辑，带来同步风险
- 长视频双 pass 增加 IO 和推理开销
- 当前阶段的目标是"模块化"而非"独立化"——后续做 overlay video 时如果有独立重跑需求，再拆分也不迟

**具体形态**:
```python
_run_tracking()
├── 统一负责视频帧读取（cv2.VideoCapture）
├── 每帧调用 _process_player_frame()  （现有逻辑）
├── 每帧调用 _process_ball_frame(ctx) （提取后）
└── 返回 _TrackingRunOutput + ball_samples

# 后处理（在 _run_tracking 返回后、_finalize_ball_analysis 之前）
_run_bounce_detection(ball_samples) → _BounceRunOutput
_finalize_ball_analysis(ball_run_output, bounce_run_output) → 写入所有 artifact + 创建 stages
```

**替代方案考虑**:
- 完全独立的 `_run_ball_tracking()` 双视频 pass：更干净的职责分离，但增加 IO 开销和同步复杂性，不适合当前阶段
- 继续把球逻辑全部塞在 `_run_tracking()` 中：代码行数继续膨胀，不可测试，不可独立跳过

---

### D5: 引入局部 `_BallRunContext` 替代实例状态

**决策**: 用局部 dataclass `_BallRunContext` 封装逐帧球检测的运行时状态（tracker、samples、detections、error），而不是将 `self._ball_tracker`、`self._ball_run_error` 挂在 `AnalysisPipeline` 实例上。

**理由**:
- `AnalysisPipeline` 实例理论上可能被复用，run-level 状态挂实例容易引入隐性跨任务污染
- 局部 context 在 `_run_tracking()` 内创建、在方法结束时销毁，生命周期明确
- 提取 `_process_ball_frame(context, ...)` 后，context 作为显式参数传入，函数无副作用地修改 context 字段，便于测试

```python
@dataclass
class _BallRunContext:
    tracker: BallTracker | None
    samples: list[BallFrameSample] = field(default_factory=list)
    detections: list[MultiTargetDetection] = field(default_factory=list)
    error: str | None = None
    disabled_reason: str | None = None
```

---

## Risks / Trade-offs

**[R1] `ball_overlay.json` 不包含每一帧 → 前端需要按 frame_index 查找最近的 overlay frame**
- 缓解：顶层 `source.frame_stride` 和 `coverage` 元数据让前端知道采样粒度；叠加层渲染通常是"找最近的 overlay frame"，不需要逐帧索引

**[R2] 单视频循环意味着球处理逻辑仍与视频读取耦合**
- 缓解：`_process_ball_frame()` 是纯函数式提取（输入 frame + context，输出 None），未来如需独立 pass 可直接复用
- 后续 Change 4 做 overlay video 时再评估是否需要完全独立的球视频循环

**[R3] 单一 strict 开关可能在调试弹跳检测器时粒度不够**
- 缓解：如果后续需要独立调试弹跳检测器，可以再扩展 `PICKLEBALL_BOUNCE_DETECTION_STRICT` —— 但现在不预埋，避免配置矩阵膨胀

**[R4] 新建 `app/schemas/ball.py` 可能与 `pickleball_game_analysis/schemas.py` 产生概念重复**
- 缓解：两个文件职责明确不同 —— 前者是 API artifact 契约（Pydantic，面向前端），后者是内部算法数据结构（dataclass，面向 engine）。通过转换函数桥接，不完全共用同一个 class
- 长期可在 refactor 中统一，但 Change 3 不做

## Open Questions

无。所有关键设计决策已在探索阶段达成一致。
