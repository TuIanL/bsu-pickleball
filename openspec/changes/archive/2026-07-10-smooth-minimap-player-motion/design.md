## Context

分析视频右上角小地图使用 `OverlayVideoWriter` 配合 `MinimapVisualizer` 渲染，消费 `player_trajectory.json` 中的坐标点。当前管线存在三个核心问题：

1. **`CourtPositionSmoother` 将正常抽帧间隔误判为 gap** — `frame_stride=5` 时每帧都进入 `gap_hold`，位置冻结在每个抽样帧上
2. **缺乏逐帧位置生成** — `PlayerIdentityManager` 虽有线性插值，但插值在 smoother 冻结后的端点之间进行，补出来的仍是一串相同位置
3. **双重平滑与因果滤波的延迟叠加** — EWMA (`alpha=0.45`) + 滑动窗口均值 (`smoothing_window`) 引入 200ms+ 相位滞后

现有指标链路 (`player_metric_tracks`, `player_trajectory.json`, metrics, heatmaps, scatter plots) 不应被修改。

### Current Data Flow

```
frame_positions
    │
    ▼
CourtPositionSmoother.update()  ← EWMA + gap_hold + outlier_clamp
    │  pos.court_position 被覆盖
    ▼
PlayerIdentityManager  ← 在冻结端点上线性插值
    │
    ├──▶ player_metric_tracks  (指标)
    ├──▶ player_trajectory.json  (→ 热力图/散点图/Overlay)
    └──▶ diagnostics / lock_update
                │
                ▼
        OverlayVideoWriter ← _points_until_time 逐帧扫描
                │
                ▼
            analysis_overlay.mp4  ← 冻结+跳变
```

### Limitation of Current IdentityManager Interpolation

IdentityManager 已经在做帧间线性插值（插值缓冲默认 90 帧），但这不能解决小地图卡顿。因为：

1. 插值在 `CourtPositionSmoother` 冻结过的端点上进行
2. 当端点位置相同时，插值输出一串相同位置
3. 平滑器在 stride>1 时几乎每个观测都进入 `gap_hold`，使端点持续冻结

因此"已有插值"和"小地图卡顿"可以同时成立——插值了，但插的是冻结值。

## Goals / Non-Goals

**Goals:**
- 小地图球员标记按视频帧率连续移动，不再出现规律性冻结-跳变
- 现有指标输出 (`player_metric_tracks`, `player_trajectory.json`, metrics, heatmaps, scatter plots) 完全不变
- 新增渲染轨迹作为独立 artifact，不污染现有数据结构
- 分段状态通过显式数据结构传递，PostProcessor 不直接读取 Manager
- 在 Overlay 渲染路径中规范化 player_id 大小写（不影响 IdentityManager 和 LockManager）

**Non-Goals:**
- 不修改 `CourtPositionSmoother` 的行为
- 不修改 `PlayerIdentityManager` 的行为
- 不修改 `PlayerLockManager` 的 player_id 格式
- 不在第一批引入 Kalman/RTS
- 不修改前端 `StandardCourtPlan` 的 96 点采样限制
- 不承诺完全消除原始投影噪声——仅消除规律性冻结-跳变

## Decisions

### D1: Overlay 旁路架构 — 新增 CourtTrackPostProcessor

**Decision:** 在 smoother 之前保存原始坐标，在 IdentityManager 之后收集身份映射，组合成 `CourtTrackObservation[]` 输入 PostProcessor，在 `_run_tracking` 末尾调用，生成渲染轨迹供后续消费。

**Rationale:**
- 指标链路完全不感知新模块，回归风险为零
- 原始坐标未经 smoother 修改，不会带有 gap_hold/ewma 的冻结和延迟
- `player_id` 使用 IdentityManager 分配的稳定身份，保证跨帧一致性
- PostProcessor 在 `_run_tracking` 末尾调用时数据完整在内存中，不需要跨阶段传递大量对象

**Target Data Flow (第一批):**

```
frame_positions
    │
    ├── raw_court_positions  (smoother 前保存)
    │       │
    │       ▼
    │   CourtPositionSmoother  ── 行为不变
    │       │
    │       ▼
    │   PlayerIdentityManager  ── 行为不变
    │       │
    │       ├──▶ player_metric_tracks  (指标不变)
    │       ├──▶ player_trajectory.json  (→ 热力图/散点图不变)
    │       └──▶ player_by_track + diagnostics (身份信息)
    │
    └── raw_x/ft + player_id + diagnostics → CourtTrackObservation[]
                                                    │
                                                    ▼
                                            CourtTrackPostProcessor
                                              (在 _run_tracking 末尾调用)
                                              linear_render_v1
                                                    │
                                                    ▼
                                          player_render_trajectory.json
                                                    │
                                                    ▼
                                          OverlayVideoWriter (逐帧索引读取)
                                                    │
                                                    ▼
                                                analysis_overlay.mp4
```

### D2: 数据结构 — CourtTrackObservation + CourtTrackEvent

**Decision:** 新增两类显式数据结构，不扩展 `ProjectedTrackPoint`，不让 PostProcessor 读取 Manager。

```python
@dataclass(frozen=True)
class CourtTrackObservation:
    frame_index: int
    timestamp_seconds: float
    player_id: str
    identity_epoch: int           # 身份纪元，用于分段
    track_id: int | None
    raw_x_ft: float               # smoother 前的原始坐标
    raw_y_ft: float
    confidence: float
    projection_status: str
    projection_confidence: float | None
    footpoint_method: str | None
    lock_state: str | None
    tracking_status: str          # detected / interpolated / predicted / rejected
```

```python
@dataclass(frozen=True)
class CourtTrackEvent:
    frame_index: int
    timestamp_seconds: float
    player_id: str
    event_type: str               # identity_created / identity_reconnected /
                                  # lock_acquired / lock_lost / lock_reconnected /
                                  # identity_reset
    previous_track_id: int | None
    current_track_id: int | None
    reason: str | None
```

**Rationale:**
- `ProjectedTrackPoint` 是轻量指标契约，塞入内部状态会耦合前后端
- PostProcessor 直接读 Manager 会导致单元测试必须构造整套有状态管线
- Observation + Event 可以在 pipeline 中逐帧收集，序列化后独立重放

### D3: 身份纪元适配器 — 使用 Pipeline 侧 cursor，不调用不存在的 Manager API

**Decision:** 不在 `PlayerIdentityManager` 上新增 `get_epoch()` 或 `last_frame_events` 方法。改为在 `_run_tracking()` 中维护只读适配器。

```python
identity_diagnostic_cursor = 0
identity_epoch_by_player: dict[str, int] = defaultdict(int)

# 每帧 IdentityManager 更新后：
new_diagnostics = identity_manager.diagnostics[identity_diagnostic_cursor:]
identity_diagnostic_cursor = len(identity_manager.diagnostics)

for diag in new_diagnostics:
    event_type = EVENT_MAPPING.get(diag.event_type)
    if event_type:
        events.append(CourtTrackEvent(
            frame_index=frame_index,
            timestamp_seconds=timestamp,
            player_id=diag.player_id,
            event_type=event_type,
            reason=diag.reason,
            ...
        ))
    if diag.event_type == "player_reset_after_prolonged_loss":
        identity_epoch_by_player[diag.player_id] += 1
```

**Event mapping (第一批):**

| IdentityManager diagnostics | CourtTrackEvent |
|--------------------------|-----------------|
| `created` | `identity_created` |
| `reconnected` | `identity_reconnected` |
| `player_locked` (lock) | `lock_acquired` |
| `player_reconnected_from_lost` (lock) | `lock_reconnected` |
| `player_reset_after_prolonged_loss` (lock) | `identity_reset` |

`identity_reassigned` 暂不纳入第一批——当前 diagnostics 中尚无该事件类型。

**Epoch 仅在 `player_reset_after_prolonged_loss` 时递增。**

**Rationale:**
- 不修改 IdentityManager 接口，零回归风险
- diagnostics 数组在 `_run_tracking` 执行期间持续累积，cursor 方式安全
- LockManager 已在 `lock_update` 中输出事件类型，直接读取即可
- 序列化到 artifact 后 PostProcessor 可在独立进程中重放，不依赖 Manager 实例

### D4: 渲染轨迹 artifact 独立存储

**Decision:** 新增 `player_render_trajectory.json` 作为独立 artifact，在 `_run_tracking` 末尾由 PostProcessor 生成，在 `AnalysisPipeline.run()` 中写出。Overlay 优先读取，不存在时回退到旧 `player_trajectory.json`。

```
outputs/<job_id>/player_render_trajectory.json
outputs/<job_id>/player_trajectory.json           ← 完全不变
```

新增 Artifact API 路由：

```
GET /api/analysis/jobs/{job_id}/artifacts/player-render-trajectories
```

渲染轨迹格式：

```json
{
  "schema_version": "1.0",
  "job_id": "...",
  "status": "available",
  "detail": "已生成 4 条球员渲染轨迹，共 3600 帧",
  "fps": 30,
  "total_frames": 3600,
  "players": {
    "Player_1": [
      {
        "frame_index": 0,
        "timestamp_seconds": 0.0,
        "x_ft": 7.34,
        "y_ft": 31.82,
        "source": "observed",
        "confidence": 0.87
      },
      {
        "frame_index": 1,
        "timestamp_seconds": 0.033,
        "x_ft": 7.41,
        "y_ft": 31.75,
        "source": "interpolated",
        "confidence": 0.85
      }
    ]
  }
}
```

**source 字段值（第一批）：**

| 值 | 含义 |
|---|------|
| `observed` | 真实检测+投影得到的坐标 |
| `interpolated` | 两个 observed 之间线性插值 |

### D5: 第一批使用线性插值 + 基础异常点过滤，不引入 Kalman

**Decision:** 第一批 PostProcessor 实现 `linear_render_v1` 模式。在插值前做基础异常点过滤，然后在已确认的 observed 点之间做线性插值。第二批再引入 Kalman + RTS。

**Rationale:**
- IdentityManager 已在做线性插值，但受 smoother 冻结影响。PostProcessor 使用原始坐标做同样的事，效果即可恢复
- 无状态线性插值实现简单，零回归风险
- 增加基础异常点过滤，避免原始投影中的孤立跳点被线性插值变为"平滑地跳到错误位置"

**基础异常点过滤（三点孤立尖峰检测）：**

```python
def reject_spike(prev, current, next, max_displacement_ft=6.0):
    d_prev_current = distance(prev, current)
    d_current_next = distance(current, next)
    d_prev_next = distance(prev, next)
    # 当前点离两边都远，但两边离得近 → 孤立跳点
    return (d_prev_current > max_displacement_ft
            and d_current_next > max_displacement_ft
            and d_prev_next < max_displacement_ft)
```

被拒绝的观测不进入插值，但不冻结——跳过该点，用前后 observed 直接连线。

**插值规则：**

```python
max_interpolation_gap_seconds = 0.35  # 最多插值 ~10 帧 (30fps)
max_visible_gap_seconds = 0.60        # 超过此值直接切断

# 间隔 ≤ 0.35s: 线性插值
# 0.35s < 间隔 ≤ 0.60s: 线性插值但 confidence 衰减
# 间隔 > 0.60s: 不连接，切段
```

**第一批目标措辞：** 消除由 frame_stride 导致的规律性冻结与跳变；不承诺完全消除原始投影噪声。

### D6: 球员拖尾按时间定义，保留 ball trail_length

**Decision:** 不替换 `trail_length`。新增 `VisualizationConfig.minimap_player_trail_seconds: float = 2.5`。Overlay 中按时间窗口过滤球员点，球轨迹仍使用原有的 `trail_length` 点数逻辑。

```python
@dataclass(frozen=True)
class VisualizationConfig:
    trail_length: int = 20                    # 不变，用于球轨迹
    minimap_player_trail_seconds: float = 2.5 # 新增，用于球员拖尾
```

Overlay 渲染时：

```python
trail_frames = round(trail_seconds * fps)
player_trails: dict[str, deque[VisualizationPoint]]

# 逐帧处理
current = frame_table.get(frame_index, {})
for player_id, point in current.items():
    player_trails[player_id].append(point)

for trail in player_trails.values():
    while trail and trail[0].frame_index < frame_index - trail_frames:
        trail.popleft()
```

**Rationale:**
- `trail_length` 被 `MinimapVisualizer.render()` 和 `_draw_trails()` 同时用于球员和球轨迹，直接替换会破坏球轨迹行为
- 回退路径要求"删除渲染 artifact 后行为完全一致"，替换语义会导致回退失败
- 球员和球的运动特性不同：球速快、轨迹短，适合固定点数；球员移动平滑，适合固定时间

### D7: player_id 规范化 — 不在 Manager 层面修改

**Decision:** 不修改 `PlayerLockManager` 和 `PlayerIdentityManager` 的 player_id 格式。仅在渲染事件适配器中使用 `canonical_player_id()` 函数规范化。

```python
def canonical_player_id(value: str) -> str:
    if value.startswith("player_"):
        return "Player_" + value.removeprefix("player_")
    return value
```

**适用范围：**
- `CourtTrackEvent.player_id`
- lock_state 快照
- render trajectory 分组

**不适用范围：**
- 不回写 `PlayerLockManager`
- 不传回 `PlayerIdentityManager`
- 不进入 `track_identity_hints`

**Rationale:** 修复 LockManager 的 ID 格式会改变 `track_identity_hints` 的匹配行为，进而影响身份分配和指标轨迹。这是一个独立的 fix，不应放在"零回归"的 Change 中。

### D8: Overlay 逐帧索引读取 + 按球员维护 deque

**Decision:** OverlayVideoWriter 预构建帧索引表 `dict[int, dict[str, Point]]`，同时在视频循环中维护每个球员的 deque 用于拖尾。

```python
# 写入前构建帧索引表
frame_table: dict[int, dict[str, RenderPoint]] = {}
for point in dense_render_tracks:
    frame_table.setdefault(point.frame_index, {})[point.player_id] = point

# 视频循环中
player_trails: dict[str, deque[RenderPoint]] = defaultdict(deque)
trail_frames = round(trail_seconds * fps)

for frame_index in range(total_frames):
    current_players = frame_table.get(frame_index, {})
    for player_id, point in current_players.items():
        player_trails[player_id].append(point)

    for player_id in list(player_trails):
        while player_trails[player_id] and player_trails[player_id][0].frame_index < frame_index - trail_frames:
            player_trails[player_id].popleft()

    trail_points = [p for trail in player_trails.values() for p in trail]
    self.minimap.render(player_points=trail_points, ...)
    writer.write(frame)
```

不再使用 `_points_until_time()` 在稀疏列表中每帧全量扫描。

### D9: metric_player_points 与 render_player_points 分离（在 _run_visualization 中）

**Decision:** `_run_visualization()` 中的 `player_points` 拆分为两个变量。

```python
metric_player_points = player_points_from_artifact(
    inputs.get("players_trajectory") or {}
)

render_player_points = (
    player_render_points_from_artifact(
        inputs.get("player_render_trajectory") or {}
    )
    or metric_player_points  # 回退
)
```

消费关系固定为：

| 消费者 | 数据源 |
|--------|--------|
| `PositionVisualizationDataBuilder` | `metric_player_points` |
| `PositionVisualizer` (热力图/散点图) | `metric_player_points` |
| `OverlayVideoWriter` | `render_player_points` |

**Rationale:** 不拆分的话，Overlay 切换到渲染轨迹的同时热力图和散点图也会跟着变，破坏"现有结果不变"的承诺。

### D10: 配置项（第一批暴露）

```python
player_render_trajectory:
  enabled: true
  max_interpolation_gap_seconds: 0.35
  max_visible_gap_seconds: 0.60
  minimap_player_trail_seconds: 2.5
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 原始坐标未经 smoother 过滤，投影噪声可能使渲染轨迹抖动 | 增加三点孤立尖峰检测过滤明显跳点；线性插值对连续噪声有均值效应；第二批 Kalman 进一步处理 |
| Diagnostics cursor 方式可能遗漏事件 | IdentityManager.diagnostics 只增不删，cursor 单调递增，不丢失事件 |
| `canonical_player_id()` 在 LockManager 修复前 mask 了格式不统一问题 | 仅影响渲染路径；指标路径不变。后续独立 Change 修复 Manager 后移除该函数 |
| 新增 artifact 和 API 路由增加维护成本 | Artifact 模式与现有 `player_trajectory` 完全一致，路由注册模式相同，无新范式 |
| 第一批线性插值无法处理急停、急转等非线性运动 | 这是第一批的已知局限。第一批验收标准仅为"消除由 frame_stride 导致的规律性冻结与跳变" |
| 批量新增 deques 在长视频中可能堆积 | trail_frames 限制最大长度（2.5 秒），deque 自动裁剪，不会无限增长 |
