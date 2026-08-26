## 1. 统一小地图身份颜色

- [x] 1.1 扩展 HUD 球员展示数据，使 `CourtMinimap` 能以 canonical `player_id` 而非渲染顺序解析颜色。
- [x] 1.2 复用视频人物框的 identity hue resolver，替换小地图的顺序调色板，并保留未知/legacy ID 的确定性回退。

## 2. 接入重建球路的小地图投影

- [x] 2.1 为 `ReconstructedBallTrajectoryArtifact` 实现或扩展 court-space 小地图适配器，按展示资格、canonical tick、时间窗口和断段规则输出可绘制球路。
- [x] 2.2 将重建球路 artifact 与 render view 从 `VideoAnalysisCard` 传递给 `CourtMinimap`，并优先渲染重建 court-space 路径。
- [x] 2.3 保留旧 `BallTrajectoryArtifact.court_xy` 的兼容回退，且在无合法 court-space 数据时不伪造球路。

## 3. 验证与回归

- [x] 3.1 增加小地图测试：P1–P4 颜色与视频 identity hue 一致，且缺失/排序变化不改变同一身份颜色。
- [x] 3.2 增加球路测试：仅有可展示重建球路时小地图显示轨迹；长缺口断段；旧球路仍可回退。
- [x] 3.3 运行相关前端测试与类型检查，确认球路开关、单摄旧任务和双摄展示机位切换未回归。
