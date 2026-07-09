# Projection Schema

## Purpose

扩展投影点数据模型，使每个投影点携带位置状态、来源方法和可信度信息，为下游可视化、过滤和分析提供决策依据。

## Data Model

### PlayerFramePosition（tracking.py）

```python
@dataclass
class PlayerFramePosition:
    # 现有字段
    frame_index: int
    timestamp: float
    track_id: int
    bbox: list[float]
    image_footpoint: list[float]
    court_position: list[float]   # [x_ft, y_ft]
    confidence: float | None

    # 新增字段
    is_inside_court: bool = False
    is_inside_tracking_area: bool = False
    projection_status: str = "unknown"          # 见下方枚举
    projection_confidence: float | None = None  # 0~1
    footpoint_method: str = "bbox_bottom_center"

    # 保留（deprecated）
    valid: bool = True
    validity: str = "valid"
```

### ProjectionStatus 枚举

```python
class ProjectionStatus(str, Enum):
    INSIDE_COURT = "inside_court"                  # 在正式球场内
    OUTSIDE_COURT_VISIBLE = "outside_court_visible" # 在 tracking buffer 内但不在球场内
    OUTSIDE_TRACKING_AREA = "outside_tracking_area"  # 超出 tracking buffer
    PROJECTION_FAILED = "projection_failed"         # 投影失败
```

### VisualizationPoint（visualization_schemas.py）

```python
@dataclass(frozen=True)
class VisualizationPoint:
    x_ft: float
    y_ft: float
    frame_index: int | None = None
    timestamp_seconds: float | None = None
    label: str | None = None
    source: str = "artifact"
    confidence: float | None = None

    # 新增可选字段（不影响下游消费）
    projection_status: str | None = None
    footpoint_method: str | None = None
    projection_confidence: float | None = None
```

## Downstream Impact

- `PlayerProjector` 写入新字段
- `MinimapVisualizer` 根据 `projection_status` 决定渲染样式
- `VisualizationDataBuilder` 根据 `is_inside_court` / `is_inside_tracking_area` 分流
- 旧 consumer 只读 `x_ft` / `y_ft`，无影响
