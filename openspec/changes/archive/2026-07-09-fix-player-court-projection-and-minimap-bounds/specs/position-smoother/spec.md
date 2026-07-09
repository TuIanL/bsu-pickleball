# Position Smoother

## Purpose

对球员投影坐标做时间平滑，降低帧间抖动和异常跳变，提高小地图显示稳定性。平滑后的坐标有 `smoothing_status` 标记，下游按状态决定是否能用于指标计算。

## Algorithm

EMA（Exponential Moving Average）：

```
smooth_x_t = alpha * raw_x_t + (1 - alpha) * smooth_x_{t-1}
smooth_y_t = alpha * raw_y_t + (1 - alpha) * smooth_y_{t-1}
```

## Configuration

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alpha` | 0.45 | 平滑系数（越低越平滑，响应越慢） |
| `max_speed_ft_s` | 30.0 | 最大合理速度 ft/s（约 9m/s，超过视为 outlier） |
| `max_gap_frames` | 10 | track 中断后保持平滑值的最大帧数 |

## Outlier Detection

```python
speed = sqrt(dx^2 + dy^2) / dt  # ft/s
if speed > max_speed_ft_s:
    # 不更新平滑值，返回上一次平滑值
    return state.smoothed, "outlier_clamped"
```

## Gap Handling

```python
if frame_index - state.last_frame > max_gap_frames:
    reset(state)  # 超时重置
    return raw, "gap_reset"
elif gap_frames > 0:
    # 短 gap 保持最后已知位置
    return state.smoothed, "gap_hold"
```

## State Management

```python
@dataclass
class SmoothState:
    track_id: int
    smoothed_x: float
    smoothed_y: float
    last_frame: int
    last_timestamp: float
    gap_frames: int = 0
    outlier_count: int = 0
    active: bool = True

    def reset(self):
        self.smoothed_x = 0.0
        self.smoothed_y = 0.0
        self.gap_frames = 0
        self.active = False
```

## Result Type

```python
@dataclass
class CourtPositionResult:
    x: float           # 输出的 x 坐标（平滑后 / hold / raw）
    y: float           # 输出的 y 坐标
    smoothing_status: str  # "smoothed" | "outlier_clamped" | "gap_hold" | "reset_after_gap"
    raw_x: float       # 原始投影 x
    raw_y: float       # 原始投影 y
```

## Downstream Constraints

`smoothing_status` 决定该点能否进入指标计算：

| smoothing_status | minimap | heatmap | 移动距离 | 速度 | 区域占比 |
|-----------------|---------|---------|---------|------|---------|
| smoothed | ✅显示 | ✅纳入 | ✅计算 | ✅计算 | ✅统计 |
| outlier_clamped | ✅显示（半透明） | ❌不纳入 | ❌不计算 | ❌不计算 | ❌不统计 |
| gap_hold | ✅显示（虚线） | ❌不纳入 | ❌不计算 | ❌不计算 | ❌不统计 |
| reset_after_gap | ✅显示 | ✅纳入 | ✅计算 | ✅计算 | ✅统计 |

## Integration Point

AnalysisPipeline 中 `PlayerProjector.project()` 之后、`write_player_trajectories()` 之前：

```python
class AnalysisPipeline:
    def __init__(self):
        self.position_smoother = CourtPositionSmoother()

    def process_frame(self, frame, tracks, ...):
        positions = self.player_projector.project(tracks, ...)
        for pos in positions:
            result = self.position_smoother.update(
                track_id=pos.track_id,
                frame_index=pos.frame_index,
                x_ft=pos.court_position[0],
                y_ft=pos.court_position[1],
                timestamp=pos.timestamp,
            )
            # 平滑后的坐标写入 artifact（用于小地图/轨迹显示）
            pos.court_position = [result.x, result.y]
            # 同时保留原始坐标和状态，供指标计算过滤
            pos.smoothing_status = result.smoothing_status
            pos.raw_court_position = [result.raw_x, result.raw_y]
```

## Testing

- 连续 10 帧坐标在 ±0.5ft 内抖动 → 平滑后波动 ≤ ±0.25ft
- 单帧跳变 20ft（速度 120ft/s @ 6fps）→ 标记 outlier_clamped
- track 中断 5 帧后恢复 → gap_hold，平滑值不变
- track 中断 15 帧后恢复 → reset_after_gap，使用新值
- gap_hold 点不进入 heatmap cell count
- gap_hold 点不进入移动距离计算
