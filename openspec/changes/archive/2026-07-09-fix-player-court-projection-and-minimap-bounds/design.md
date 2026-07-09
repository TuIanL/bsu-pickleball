## 整体架构变化

### 当前数据流（问题所在）

```
Camera Frame
  → YOLO Detection (bbox)
    → FootpointEstimator.estimate()  [bbox_bottom_center]
      → PlayerProjector.project()    [homography]
        → [if not in_bounds: continue]  ← 界外点被丢弃
          → VisualizationPoint (x_ft, y_ft)
            → MinimapVisualizer [if not in_bounds: return None]  ← 又被过滤
            → VisualizationDataBuilder [if not in_bounds: exclude]  ← 还被过滤
```

### 目标数据流

```
Camera Frame
  → YOLO / Pose Detection
    → FootpointEstimator.estimate()  [hybrid: pose_ankle > bbox]
      → PlayerProjector.project()    [homography → tracking_bounds check]
        → [if outside_tracking_area: skip]
        → raw ProjectedPlayerFrame
          → CourtPositionSmoother.update()  [EMA + outlier reject + gap hold]
            → smoothed ProjectedPlayerFrame {
                x_ft, y_ft,
                smoothing_status,       # raw | smoothed | outlier_clamped | gap_hold
                is_inside_court,
                is_inside_tracking_area,
                projection_status,
                projection_confidence,
                footpoint_method
              }
                → MinimapVisualizer [show tracking_area + outside_court_visible]
                → VisualizationDataBuilder [minimap: tracking, heatmap: court]
                → MetricsCalculator [仅使用 raw / smoothed，排除 gap_hold]
```

## 模块设计

### 1. CourtGeometry 边界扩展

**文件**：`court_geometry.py`

新增两个 `CourtZone` 属性：

```python
@property
def court_bounds(self) -> CourtZone:
    """正式球场范围"""
    return CourtZone("court_bounds", 0.0, self.width_ft, 0.0, self.length_ft)

@property
def tracking_bounds(self) -> CourtZone:
    """跟踪缓冲范围（略大于球场）"""
    return CourtZone("tracking_bounds", -4.0, self.width_ft + 4.0, -8.0, self.length_ft + 8.0)
```

新增方法：

```python
def is_in_court_bounds(self, x, y) -> bool  # = is_in_bounds（保持兼容）
def is_in_tracking_bounds(self, x, y) -> bool
def is_inside_court(self, x, y) -> bool      # 别名
def is_outside_court_visible(self, x, y) -> bool  # tracking 内但 court 外
```

`tracking_bounds` 默认值可通过 `PickleballCourtGeometry` 构造参数覆盖。

### 2. 投影数据模型扩展

**文件**：`tracking.py` / `visualization_schemas.py`

```python
@dataclass
class ProjectedPlayerFrame:
    frame_index: int
    timestamp: float
    track_id: int
    bbox: list[float]
    image_footpoint: list[float]
    court_position: list[float]          # [x_ft, y_ft]
    is_inside_court: bool
    is_inside_tracking_area: bool
    projection_status: str               # "inside_court" | "outside_court_visible" | "outside_tracking_area" | "projection_failed"
    projection_confidence: float | None
    footpoint_method: str
    confidence: float | None
    valid: bool                          # 保留旧字段兼容
    validity: str                        # 保留旧字段兼容
```

`VisualizationPoint` 增加可选字段：

```python
@dataclass(frozen=True)
class VisualizationPoint:
    x_ft: float
    y_ft: float
    # ... 现有字段 ...
    projection_status: str | None = None
    footpoint_method: str | None = None
    projection_confidence: float | None = None
```

### 3. PlayerProjector 改造

**文件**：`player_projector.py`

```python
def project(self, tracks, homography, frame_index, timestamp, footpoints=None):
    for track in tracks:
        footpoint = footpoints.get(track.track_id) if footpoints else None
        footpoint = footpoint or self.footpoint_estimator.estimate(track)

        court_x, court_y = image_to_court(footpoint.image_footpoint, homography)

        is_inside_court = self.court.is_in_court_bounds(court_x, court_y)
        is_inside_tracking = self.court.is_in_tracking_bounds(court_x, court_y)

        # 只有超出 tracking bounds 才丢弃
        if status == "outside_tracking_area" and self.drop_outside_tracking:
            continue

        status = self._classify_projection(court_x, court_y, footpoint.confidence)
        confidence = self._compute_projection_confidence(footpoint, status)

        positions.append(PlayerFramePosition(
            ...,
            is_inside_court=is_inside_court,
            is_inside_tracking_area=is_inside_tracking,
            projection_status=status,
            projection_confidence=confidence,
            footpoint_method=footpoint.method,
        ))
```

状态分类逻辑：

```python
def _classify_projection(self, x, y, fp_conf) -> str:
    if self.court.is_in_court_bounds(x, y):
        return "inside_court"
    if self.court.is_in_tracking_bounds(x, y):
        return "outside_court_visible"
    return "outside_tracking_area"
```

### 4. FootpointEstimator 多策略

**文件**：`footpoint_estimator.py`

```python
class FootpointEstimator:
    def __init__(self, method: FootpointMethod = "hybrid"):
        self.method = method

    def estimate(self, bbox_or_track, pose_keypoints=None) -> FootpointEstimate:
        if self.method == "hybrid" and pose_keypoints is not None:
            footpoint = self._estimate_from_pose(pose_keypoints)
            if footpoint is not None:
                return footpoint
        return self._estimate_from_bbox(bbox_or_track)

    def _estimate_from_pose(self, keypoints) -> FootpointEstimate | None:
        """从姿态关键点估算脚点"""
        # 提取左右踝、膝
        # 优先级：双踝 > 单踝 > 膝外推
        # 返回 footpoint + method + confidence

    def _estimate_from_bbox(self, bbox_or_track) -> FootpointEstimate:
        """bbox_bottom_center 回退"""
```

姿态关键点索引（COCO 骨架）：

| 关键点 | COCO 索引 |
|--------|-----------|
| left_ankle | 15 |
| right_ankle | 16 |
| left_knee | 13 |
| right_knee | 14 |

置信度权重：

```python
ANKLE_CONF_THRESHOLD = 0.35
KNEE_CONF_THRESHOLD = 0.4
KNEE_TO_FOOT_RATIO = 0.28  # 膝到脚大约占膝到头顶的比例
```

### 5. 球员球场坐标时间平滑 (CourtPositionSmoother)

**文件**：`court_position_smoother.py`（新增）

```python
class CourtPositionSmoother:
    def __init__(self, alpha=0.45, max_speed_ft_s=30.0, max_gap_frames=10):
        self.alpha = alpha
        self.max_speed_ft_s = max_speed_ft_s
        self.max_gap_frames = max_gap_frames
        self._states: dict[int, SmoothState] = {}  # track_id -> state

    def update(self, track_id, frame_index, x_ft, y_ft, timestamp, confidence=None):
        state = self._get_or_create_state(track_id, frame_index)

        if self._is_outlier(state, x_ft, y_ft, timestamp):
            return CourtPositionResult(
                x=state.smoothed_x, y=state.smoothed_y,
                smoothing_status="outlier_clamped",
                raw_x=x_ft, raw_y=y_ft,
            )

        if self._has_gap(state, frame_index):
            state.gap_frames = frame_index - state.last_frame - 1
            if state.gap_frames > self.max_gap_frames:
                self._reset(state)
                state.smoothed_x = x_ft
                state.smoothed_y = y_ft
                return CourtPositionResult(
                    x=x_ft, y=y_ft,
                    smoothing_status="reset_after_gap",
                    raw_x=x_ft, raw_y=y_ft,
                )
            # gap_hold：保持上一次平滑值，但标记状态
            return CourtPositionResult(
                x=state.smoothed_x, y=state.smoothed_y,
                smoothing_status="gap_hold",
                raw_x=x_ft, raw_y=y_ft,
            )

        # EMA 平滑
        state.smoothed_x = self.alpha * x_ft + (1 - self.alpha) * state.smoothed_x
        state.smoothed_y = self.alpha * y_ft + (1 - self.alpha) * state.smoothed_y

        return CourtPositionResult(
            x=state.smoothed_x, y=state.smoothed_y,
            smoothing_status="smoothed",
            raw_x=x_ft, raw_y=y_ft,
        )

    def _is_outlier(self, state, x, y, timestamp):
        if state.last_timestamp is None:
            return False
        dt = max(timestamp - state.last_timestamp, 0.001)
        dx = x - state.smoothed_x
        dy = y - state.smoothed_y
        speed = math.sqrt(dx*dx + dy*dy) / dt
        return speed > self.max_speed_ft_s
```

**关键约束**：`smoothing_status` 决定点是否能进入下游指标计算。

| smoothing_status | minimap | heatmap | 移动距离 | 速度 | 区域占比 |
|-----------------|---------|---------|---------|------|---------|
| raw / smoothed | ✅显示 | ✅纳入 | ✅计算 | ✅计算 | ✅统计 |
| outlier_clamped | ✅显示（半透明） | ❌不纳入 | ❌不计算 | ❌不计算 | ❌不统计 |
| gap_hold | ✅显示（虚线） | ❌不纳入 | ❌不计算 | ❌不计算 | ❌不统计 |
| reset_after_gap | ✅显示 | ✅纳入 | ✅计算 | ✅计算 | ✅统计 |
```

### 6. MinimapVisualizer 改造

**文件**：`minimap_visualizer.py`

```python
def court_to_pixel(self, x_ft, y_ft, *, clamp=False, bounds="tracking"):
    if bounds == "court":
        valid = self.court.is_in_court_bounds(x_ft, y_ft)
    else:
        valid = self.court.is_in_tracking_bounds(x_ft, y_ft)

    if not clamp and not valid:
        return None

    # 使用 tracking_bounds 做像素映射，确保界外点也能显示
    tracking_w = self.court.width_ft + 8.0   # 24
    tracking_h = self.court.length_ft + 16.0  # 60
    x = min(self.court.width_ft + 4.0, max(-4.0, float(x_ft))) if clamp else float(x_ft)
    y = min(self.court.length_ft + 8.0, max(-8.0, float(y_ft))) if clamp else float(y_ft)
    pad = self.config.minimap_padding
    draw_width = self.config.minimap_width - pad * 2
    draw_height = self.config.minimap_height - pad * 2
    px = pad + ((x + 4.0) / tracking_w) * draw_width      # x 从 -4 开始
    py = pad + ((y + 8.0) / tracking_h) * draw_height     # y 从 -8 开始
    return (int(round(px)), int(round(py)))
```

渲染改造：

```python
def render(self, *, player_points, ...):
    image = np.full((...), self.style.background, dtype=np.uint8)
    self._draw_court(image)          # 正式球场区域
    self._draw_tracking_bounds(image)  # tracking buffer 浅色底纹

    for label, points in grouped.items():
        # 分离场内/界外点
        inside = [p for p in points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        outside = [p for p in points if self.court.is_in_tracking_bounds(p.x_ft, p.y_ft)
                   and not self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        self._draw_trails(image, inside, color, radius=4)
        self._draw_trails(image, outside, color, radius=3, alpha=0.5)
```

### 7. VisualizationDataBuilder 改造

**文件**：`visualization_data_builder.py`

```python
def _split_points(self, player_points):
    inside = []
    outside = []
    for p in player_points:
        if self.court.is_in_tracking_bounds(p.x_ft, p.y_ft):
            if self.court.is_in_court_bounds(p.x_ft, p.y_ft):
                inside.append(p)
            else:
                outside.append(p)
    return inside, outside

def _build_visual_grid(self, player_points):
    inside, _ = self._split_points(player_points)
    # 只使用 inside 做热力图
    ...

def _build_scatter_plots(self, player_points, ...):
    inside, outside = self._split_points(player_points)
    # 散点图两类都用，但 outside 带 status
    ...

def _build_player_trajectories(self, player_points):
    _, outside = self._split_points(player_points)
    # 轨迹使用 tracking_bounds 内的所有点
    # 界外段用虚线样式标记
    ...
```

## 前端同步

**App.tsx StandardCourtPlan**：

```tsx
<svg viewBox="-4 -8 28 60">
  <!-- tracking buffer 背景 -->
  <rect x="-4" y="-8" width="28" height="60" fill="#F0F4EE" rx="0.2" stroke="#BCCFBB" strokeWidth="0.12" strokeDasharray="0.6 0.3" />
  <!-- 正式球场（保持现有） -->
  <rect x="0" y="0" width="20" height="44" rx="0.2" fill="#DDEFE2" stroke="#173321" strokeWidth="0.24" />
  ...
  <!-- 界外轨迹点用虚线连接 -->
  <polyline points="..." strokeDasharray="0.2 0.15" ... />
</svg>
```

**courtGeometry.ts**：

```typescript
export const TRACKING_WIDTH_FT = 28;   // -4 to 24
export const TRACKING_LENGTH_FT = 60;  // -8 to 52
// courtToSvg 使用 tracking viewBox 映射
```

## 时序：最小修复路径

```
第一阶段（修边界——先解决"人消失"）：
  CourtGeometry bounds → Projection schema → PlayerProjector → MinimapVisualizer
  → VisualizationDataBuilder → 前端同步 → OverlayVideoWriter → PositionVisualizer

第二阶段（修脚点——再解决"位置不准"）：
  FootpointEstimator hybrid

第三阶段（修抖动——再解决"漂移跳跃"）：
  CourtPositionSmoother

第四阶段（补测试与兼容性）：
  测试 + 旧分析结果验证
```
