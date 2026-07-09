# Minimap Bounds

## Purpose

更新小地图渲染器的坐标空间和样式，使其能显示 tracking buffer 内的界外点，并清晰区分"球场内"和"缓冲区内"两个区域。

## Coordinate Mapping

当前映射基于 court_bounds (0~20, 0~44)，改为基于 tracking_bounds (-4~24, -8~52)：

```python
def court_to_pixel(self, x_ft, y_ft, *, clamp=False, bounds="tracking"):
    if bounds == "tracking":
        bounds_zone = self.court.tracking_bounds
    else:
        bounds_zone = self.court.court_bounds

    x_min, x_max = bounds_zone.x_min, bounds_zone.x_max
    y_min, y_max = bounds_zone.y_min, bounds_zone.y_max

    if not clamp:
        if x_ft < x_min or x_ft > x_max or y_ft < y_min or y_ft > y_max:
            return None

    x = min(x_max, max(x_min, float(x_ft))) if clamp else float(x_ft)
    y = min(y_max, max(y_min, float(y_ft))) if clamp else float(y_ft)

    pad = self.config.minimap_padding
    draw_w = self.config.minimap_width - pad * 2
    draw_h = self.config.minimap_height - pad * 2
    px = pad + ((x - x_min) / (x_max - x_min)) * draw_w
    py = pad + ((y - y_min) / (y_max - y_min)) * draw_h
    return (int(round(px)), int(round(py)))
```

## Rendering Changes

```python
def render(self, *, player_points, ...):
    image = np.full((h, w, 3), self.style.background, dtype=np.uint8)
    self._draw_tracking_bounds(image)  # 新增：buffer 浅色底纹
    self._draw_court(image)            # 正式球场区域

    for label, points in grouped.items():
        inside = [p for p in points if self.court.is_in_court_bounds(p.x_ft, p.y_ft)]
        outside = [p for p in points if self.court.is_in_tracking_bounds(p.x_ft, p.y_ft)
                   and not self.court.is_in_court_bounds(p.x_ft, p.y_ft)]

        self._draw_trails(image, inside, color, radius=4)
        # 界外点：更小半径、半透明、虚线
        self._draw_trails_outside(image, outside, color, radius=3, alpha=0.4)

def _draw_tracking_bounds(self, image):
    """绘制 tracking buffer 边界（虚线框 + 浅绿底纹）"""
    ...

def _draw_trails_outside(self, image, points, color, radius, alpha):
    """界外轨迹用虚线 + 半透明绘制"""
    pixels = [self.court_to_pixel(p.x_ft, p.y_ft) for p in points]
    pixels = [p for p in pixels if p is not None]
    if len(pixels) >= 2:
        overlay = image.copy()
        cv2.polylines(overlay, [np.array(pixels)], False, color, 1, cv2.LINE_AA)
        cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    for pixel in pixels:
        cv2.circle(image, pixel, radius, color, -1, cv2.LINE_AA)
```

## Style Additions

```python
@dataclass(frozen=True)
class MinimapStyle:
    # ... 现有 ...
    tracking_bounds_fill: tuple[int, int, int] = (236, 244, 234)  # 比 court_fill 更淡
    tracking_bounds_line: tuple[int, int, int] = (190, 210, 185)  # 浅色虚线框
    outside_player: tuple[int, int, int] = (160, 200, 165)       # 界外球员点颜色（绿中带灰）
```

## OverlayVideoWriter

`_draw_minimap` 使用 `render()` 的新行为，无需额外修改。
