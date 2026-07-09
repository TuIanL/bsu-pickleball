# Visualization Data Bounds

## Purpose

让 VisualizationDataBuilder 按可视化模块区分数据来源：热力图只用 court_bounds 内点，轨迹和小地图用 tracking_bounds 内点，确保各可视化产物的数据语义正确。

## Split Logic

```python
def _split_points(self, player_points: list[VisualizationPoint]):
    """返回 (inside_court, outside_court_visible, dropped)"""
    inside = []
    outside_visible = []
    dropped = []
    for p in player_points:
        if self.court.is_in_tracking_bounds(p.x_ft, p.y_ft):
            if self.court.is_in_court_bounds(p.x_ft, p.y_ft):
                inside.append(p)
            else:
                outside_visible.append(p)
        else:
            dropped.append(p)
    return inside, outside_visible, dropped
```

## Per-Visualization Rules

| 可视化模块 | 数据来源 | 界外点如何处理 |
|-----------|---------|---------------|
| 热力图网格 | inside | 不纳入界外点 |
| 散点图球员 | inside + outside_visible | 界外点半透明/不同颜色 |
| 球员轨迹 | inside + outside_visible | 界外段虚线 |
| ball scatter | inside（不变） | — |
| bounce scatter | inside（不变） | — |

## StructuredVisualizationData

```python
@dataclass(frozen=True)
class StructuredVisualizationData:
    court: CourtGeometry
    heatmaps: VisualGrid | None = None
    scatter_plots: ScatterPlots = field(default_factory=ScatterPlots)
    player_trajectories: list[PlayerTrajectory] = field(default_factory=list)

    # 新增元数据
    outside_court_point_count: int = 0
    dropped_point_count: int = 0
```

## Heatmap（position_visualizer.py）

```python
def _generate_heatmaps(self, player_points, ...):
    inside, _, _ = self._split_points(player_points)
    if not inside:
        return []
    # 只使用 inside 点做热力图
    ...
```

输出清单中可注明：

```python
"description": f"基于 {len(inside)} 个场内坐标点，过滤 {len(outside_visible)} 个界外坐标点",
```

## Scatter Plot（position_visualizer.py）

```python
def _generate_scatters(self, player_points, ...):
    # 全部点都可用于散点图
    ...
```

## Player Trajectories（visualization_data_builder.py）

```python
def _build_player_trajectories(self, player_points):
    inside, outside_visible, _ = self._split_points(player_points)
    all_tracking = inside + outside_visible
    # 对每条轨迹：
    # - 纯场内段：实线
    # - 含界外段：虚线
    # 输出 trajectory 时携带 segment_type 标记
```

## Consistency

确保调用方（`PositionVisualizer.generate()` 和 `PositionVisualizationDataBuilder.build()`）使用相同的 `_split_points` 逻辑，避免同一批点在热力图和散点图中表现不一致。
