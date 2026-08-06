## 1. 后端对齐修复

- [x] 1.1 修改 `display_player_label`（`backend/app/vision/pickleball_game_analysis/visualization_schemas.py`）：canonical `Player_N` → `P1`..`P4`，更新 docstring；非 canonical 回退原 label
- [x] 1.2 修改 `compute_zone_stats`（`backend/app/vision/pickleball_game_analysis/zone_stats.py`）：`id` 改用 `canonical_player_id(label)`；`color` 改为按 canonical 序号显式分配（解析失败回退索引）
- [x] 1.3 修改 `visualization_data_builder.py` 的 `_build_heatmaps` / `_build_scatter_plots` / `_build_player_trajectories` / `_build_zone_stats`：`id` 用 canonical、`label` 用 `display_player_label`（已改 P 风格）、`color` 按 canonical 序号分配
- [x] 1.4 更新 `backend/tests/test_zone_heatmap.py`：`"球员1"` → `"P1"`、`id` 索引 → canonical `Player_N` 等断言
- [x] 1.5 新增/补充后端测试：heatmaps / scatter / zone / trajectories 的球员 `id` 为 canonical、`label` 为 `P1`..`P4`、颜色按 canonical 序号（保持调色板不变）

## 2. 前端数据模型与 mock

- [x] 2.1 `src/types/report.ts` 新增 `PLAYER_SCORE_DIMENSIONS`（发球 / 接发球 / 进攻能力 / 防守能力 / 敏捷 / 击球稳定性）、`PlayerScore`（`player_id` + 六维字段，0–10、1 位小数）、`PlayerScoring`
- [x] 2.2 新增 `src/data/mockPlayerScores.ts`：`MOCK_PLAYER_SCORES` 按 `Player_1`..`Player_4` 键，六维全覆盖
- [x] 2.3 新增前端 canonical 球员颜色映射 `PLAYER_ID_TO_COLOR`（镜像后端 `PLAYER_HEX_COLORS`，保持现有调色板）

## 3. RadarChart 组件

- [x] 3.1 实现 `src/components/platform/RadarChart.tsx`：六轴等角 SVG 雷达，0–10 环形网格（0/2/4/6/8/10），顶点维度标签 + 分值 `toFixed(1)`，多边形用球员 canonical 色填充
- [x] 3.2 `RadarChart` 测试：六轴渲染、分值保留 1 位小数、球员色应用

## 4. PlayerScoringPanel 组件

- [x] 4.1 实现 `src/components/platform/PlayerScoringPanel.tsx`：整行 `sport-card`，左侧 `RadarChart`、右侧球员 tab（chip）+ 六项分值列表 + 六项均分；默认选中 roster[0]；scores 缺省回退 `MOCK_PLAYER_SCORES`；标注"演示数据"
- [x] 4.2 自适应 roster 提取：从 `result.tracks` 去重 canonical `track_id` 并按自然序排序；无真实结果时兜底 `Player_1`..`Player_4`（结合 `match_context.expected_player_count`）
- [x] 4.3 `PlayerScoringPanel` 测试：tab 切换、默认选中、自适应 roster（单打 2 人）、mock 回退、演示数据标注

## 5. VisionPage 接入

- [x] 5.1 `src/pages/VisionPage.tsx` jobId 视图在可视化产物 gallery 之后追加整行 `PlayerScoringPanel`，传入 roster 与 scores
- [x] 5.2 更新相关前端类型检查与冒烟测试

## 6. 验证

- [x] 6.1 后端：`cd backend && pytest tests/test_zone_heatmap.py` 及相关测试通过
- [x] 6.2 前端：`npm run test` 通过、TypeScript 类型检查通过
