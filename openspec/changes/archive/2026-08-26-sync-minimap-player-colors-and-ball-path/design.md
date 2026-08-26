## Context

`VideoAnalysisCard` 的视频人物框已通过 `resolvePlayerIdentityHue(player_id)` 取得 canonical 身份颜色；`CourtMinimap` 则按经过排序的球员数组下标使用独立的 `PLAYER_COLORS` 调色板。排序、缺帧或仅部分球员可见都会改变数组下标，因此小地图颜色不是身份的稳定属性。

球路存在两条数据路径：旧 `BallTrajectoryArtifact` 同时含 `image_xy` 与可选 `court_xy`；新的 `ReconstructedBallTrajectoryArtifact` 为视频提供按 `render_view_id` 选择的 `image_paths_by_view`，并提供经质量门筛选的 canonical court-space 重建样本。视频已经优先消费后者，但 `CourtMinimap` 未接收该 artifact，形成展示断层。

## Goals / Non-Goals

**Goals:**

- 以 canonical `player_id` 作为视频人物框和小地图球员颜色的唯一输入，使颜色不受轨迹排序、可见人数和证据来源影响。
- 让小地图在同一 canonical tick 渲染可展示的重建球路，并延续视频的段级时间窗口、断段及展示资格语义。
- 保留旧 `BallTrajectoryArtifact` 的场地坐标回退，避免影响单摄或历史任务。

**Non-Goals:**

- 不修改后端球检测、球路重建、质量门或 API schema。
- 不将 `image_xy` 投影/猜测为小地图坐标，也不将 `court_xy` 转换为视频像素路径。
- 不改变视频人物框的证据线型、透明度或颜色调色板定义。

## Decisions

### 以现有 identity hue resolver 作为前端颜色唯一 authority

`CourtMinimap` 将从 HUD player 的 canonical 身份取得颜色，并调用 `resolvePlayerIdentityHue`，与 `FusedPlayerBox` 完全一致。对 legacy 或未知 ID，复用该 resolver 的兼容和确定性 hash 行为。

不采用按 `render_slot` 或显示顺序着色：slot 在部分旧/单摄输入中不稳定或不可用，而顺序正是当前错色的根源。

### 为小地图建立独立的 court-space 重建球路适配器

视频继续使用 `image_paths_by_view[render_view_id]`；小地图新增只读取已展示合格 segment 的 canonical court-space 样本。适配器接收同一个 `currentTime`，使用与视频一致的 active/retention 策略，只返回一个可绘制 segment，并保留长时间缺口的断段。

不复用视频 image-space 适配器：两者坐标空间不同，复用会造成场地投影错误。适配器放在现有前端球路显示边界附近，以便共享展示资格和时间窗口常量，而不是让 SVG 组件直接解析 artifact。

### 重建球路优先，旧球路回退

`VideoAnalysisCard` 同时把重建 artifact、render view 和 canonical 时间传入小地图。若重建适配器返回可展示 court-space 路径，小地图优先渲染它；否则仅在没有可用重建路径时使用旧 `ballTrajectory.samples[].court_xy`。这与视频的“重建产物存在但不可展示时不伪造旧路径”的语义保持一致。

### 由现有图层开关统一控制

小地图球路继续受 `showBallPath` 控制；关闭视频球路时，同时隐藏小地图球路，但不影响球员、当前球点或弹跳层已有的独立开关语义。

## Risks / Trade-offs

- [重建 artifact 的样本字段可能随 schema 演进变化] → 仅消费已有类型定义中的 canonical court-space 字段，并以有限、类型化的 adapter 隔离 schema 解析。
- [重建段缺少合法 court-space 点] → 不绘制伪造路线；遵循回退规则并保持小地图球层状态可解释。
- [颜色 resolver 处理未知 ID 的结果与旧静态色不同] → 这是刻意的身份一致性修复；canonical P1–P4 颜色与视频严格相同，未知 ID 保持确定性而非随机。
- [视频与小地图时间窗口细节偏离] → 使用同一 canonical tick 和共享的 active/retention 常量，并以集成测试覆盖。
