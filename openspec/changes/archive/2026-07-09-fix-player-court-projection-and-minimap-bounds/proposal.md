## Why

当前小地图在球员发球、救球或走出球场线时会消失，原因是投影链路在 PlayerProjector、MinimapVisualizer、VisualizationDataBuilder 三处都只接受 0–20ft / 0–44ft 的场内坐标，一旦球员脚点投影到球场线外（发球站底线后、救球冲出边线等），整帧数据被丢弃或过滤，前端 SVG 拿不到任何坐标。

同时，球员位置投影依赖 bbox 底边中点和单帧单应性投影，没有姿态辅助脚点估计、没有时间平滑、没有镜头畸变校正，导致脚点误差大、边缘漂移严重、帧间抖动明显，直接影响小地图可信度、移动距离计算、站位分析、发球识别和回合状态判断。

这不是 UI 问题。这是**球员球场坐标可靠性问题**，是整个位置分析链路的根基。

## What Changes

### 1. 边界体系：court bounds 与 tracking bounds 分离

将原本单一的 `is_in_bounds` 拆分为两层：

- **`court_bounds`**（x=0~20, y=0~44）：正式球场范围，用于热力图统计、区域占比、站位指标
- **`tracking_bounds`**（x=-4~24, y=-8~52）：合理跟踪范围，用于小地图、轨迹连续性、发球前站位、界外救球

PlayerProjector 不再默认丢弃 tracking bounds 内的点；MinimapVisualizer 不再因点不在 court_bounds 直接过滤；VisualizationDataBuilder 区分 minimap 数据与 heatmap 数据。

### 2. 投影数据模型扩展

每个投影点不再只是一个 `(x_ft, y_ft)` 坐标，而是携带状态信息：

- `x_ft` / `y_ft`：投影后的球场坐标
- `is_inside_court`：是否在正式球场内
- `is_inside_tracking_area`：是否在跟踪缓冲区内
- `projection_status`：`inside_court` | `outside_court_visible` | `outside_tracking_area` | `projection_failed`
- `projection_confidence`：投影可信度
- `footpoint_method`：脚点估计方法（`bbox_bottom_center` | `pose_ankle_midpoint` | `pose_ankle_single` | `knee_extrapolated`）

### 3. 脚点估计升级

从单一的 bbox_bottom_center 升级为多策略 hybrid：

| 优先级 | 条件 | 方法 |
|--------|------|------|
| 1 | 双踝可见且置信度 ≥ 0.35 | 左右踝中点 |
| 2 | 单踝可见 | 可见踝 |
| 3 | 双膝可见 | 从膝向下外推 |
| 4 | 以上皆不可用 | bbox_bottom_center fallback |

同时输出 `footpoint_method` 和 `footpoint_confidence`，供 debug overlay 和后端日志使用。

### 4. 球员球场坐标时间平滑 (CourtPositionSmoother)

引入 `CourtPositionSmoother`，按 player_id 做指数移动平均（EMA）：

- `alpha = 0.35~0.55`，可配置
- 异常跳变过滤：超过 `max_speed_ft/s`（默认 30ft/s）的跳变降低信任或标记 outlier
- 短缺失 gap 插值：track 断开 ≤10 帧时保持最后已知位置
- 每条 track 独立平滑器，track 结束超时后自动重置
- 输出 `smoothing_status`：`raw` | `smoothed` | `outlier_clamped` | `gap_hold` | `reset_after_gap`
- `gap_hold` / `outlier_clamped` 点仅用于小地图显示，**不纳入**热力图、移动距离、速度、区域占比等指标计算

### 5. 小地图渲染升级

- view 范围扩到 tracking_bounds（x=-4~24, y=-8~52）
- 正式球场区域正常绘制（填充 + 线）
- tracking buffer 区域用浅色半透明底纹区分
- `outside_court_visible` 点用半透明或虚线样式、不同颜色标记
- 前端 SVG viewBox 同步扩大

### 6. 各可视化模块边界规则统一

| 模块 | 是否显示界外点 | 原因 |
|------|---------------|------|
| 小地图 Minimap | 显示 tracking buffer 内界外点 | 真实比赛中球员会发球、捡球、救球出界 |
| 球员轨迹线 | 显示 tracking buffer 内界外点 | 保持轨迹连续 |
| 散点图 | 可以显示，但用不同样式 | 用于复盘位置分布 |
| 热力图 | 不纳入界外点 | 热力图表达场内站位 |
| 移动距离 | 可纳入，但标记来源 | 界外移动也是移动 |
| 区域占比 | 不纳入，或放入 `outside_court` 区域 | 避免污染 court zone 指标 |

## Capabilities

### New

- `court-bounds`: 球场和跟踪双层边界定义（修改 `court_geometry.py`）
- `projection-schema`: 扩展投影点数据模型，增加状态字段
- `footpoint-estimator`: 多策略混合脚点估计
- `position-smoother`: 球员位置时间平滑
- `minimap-bounds`: 小地图边界策略升级
- `viz-data-bounds`: VisualizationDataBuilder 边界隔离

### Unchanged

- `structured-heatmap`, `structured-scatter-plot`, `frontend-viz-beautification` 不受影响

## Impact

- **后端修改文件**：`court_geometry.py`, `player_projector.py`, `footpoint_estimator.py`, `minimap_visualizer.py`, `position_visualizer.py`, `visualization_data_builder.py`, `overlay_video_writer.py`, `visualization_schemas.py`, `tracking.py`
- **后端新增文件**：`court_position_smoother.py`
- **前端修改文件**：`App.tsx`（StandardCourtPlan viewBox）, `courtGeometry.ts`
- **无 breaking changes**：所有旧字段保留兼容；旧分析结果不受影响
- **新增可选诊断字段**：`projection_status`, `footpoint_method`, `projection_confidence` 不影响下游消费

## Acceptance Criteria

- 球员在发球位（y=-5ft）时，小地图可见、轨迹连续、热力图不纳入该点
- 球员救球冲出场外（x=-3ft）时，小地图显示该点（半透明）、轨迹连续
- 球员超出 tracking bounds（x=-10ft）时，小地图不显示该点
- 姿态脚踝可用时，优先使用 ankle midpoint；不可用时 fallback 到 bbox bottom center
- 连续帧间小幅抖动（≤2ft/帧）经 smoother 后波动降低 ≥50%
- 单帧异常跳变（≥15ft/帧）被 smoother 标记或过滤
- 旧分析结果不报错、不丢失数据
- `outside_court_visible` 点应进入小地图轨迹，但不得进入 heatmap cell count
- `gap_hold` 产生的补点只用于 minimap display，不参与移动距离、速度、热力图统计
- `projection_status` 在前端/结构化数据中可见，旧字段 `valid` / `validity` 仍能被旧组件读取
- 无 `pose_keypoints` 的旧 pipeline 仍能完整 fallback 到 `bbox_bottom_center`，不影响现有分析任务
