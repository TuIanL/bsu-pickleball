# Court Bounds

## Purpose

将原本单一 `is_in_bounds` 拆分为两层边界体系，使投影链路能区分"在球场内"和"在可跟踪范围内"，避免界外点被不适当地丢弃。

## Interface

```python
class PickleballCourtGeometry:
    # 现有
    width_ft: float = 20.0
    length_ft: float = 44.0

    # 新增
    tracking_x_margin: float = 4.0    # 左右缓冲 ft
    tracking_y_near_margin: float = 8.0   # 近端底线外缓冲 ft
    tracking_y_far_margin: float = 8.0    # 远端底线外缓冲 ft

    @property
    def court_bounds(self) -> CourtZone:
        return CourtZone("court_bounds", 0.0, self.width_ft, 0.0, self.length_ft)

    @property
    def tracking_bounds(self) -> CourtZone:
        return CourtZone(
            "tracking_bounds",
            -self.tracking_x_margin,
            self.width_ft + self.tracking_x_margin,
            -self.tracking_y_near_margin,
            self.length_ft + self.tracking_y_far_margin,
        )

    def is_in_court_bounds(self, x, y) -> bool  # = 旧 is_in_bounds
    def is_in_tracking_bounds(self, x, y) -> bool
    def is_outside_court_visible(self, x, y) -> bool  # tracking 内、court 外
```

## Defaults

| 参数 | 默认值 | 原因 |
|------|--------|------|
| x margin | 4 ft | 边线外约 1.2m，覆盖救球范围 |
| y near | 8 ft | 底线后约 2.4m，覆盖发球站位 |
| y far | 8 ft | 远端底线后缓冲 |
