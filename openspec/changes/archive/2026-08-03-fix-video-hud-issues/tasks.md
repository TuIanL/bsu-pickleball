## 1. 小地图默认收起与展开交互（前端）

- [x] 1.1 在 `src/components/platform/VideoAnalysisCard.tsx::RealVideoOverlay` 增加 `showCourtHud` 状态（默认 `false`），在右上角图层控制簇旁增加地图展开按钮（带 `aria-expanded`）
- [x] 1.2 收起态只显示展开按钮；展开态渲染 `CourtMinimap`（复用现有 wrapper 定位），再次点击收起；切换不改变视频播放位置与图层状态
- [x] 1.3 展开容器增加 `max-h` 与 z-index 约束，确保非全屏下不遮挡底部播放控件（含全屏按钮），并为折叠交互补充前端测试

## 2. 小地图球场方向修正（前端）

- [x] 2.1 `src/components/platform/CourtMinimap.tsx::createMapper` 的 `toSvg` 去掉 y 翻转（`svgY = offsetY + (y - yMin) * scale`），使近端（高 y）渲染在底部
- [x] 2.2 交换厨房区多边形定义（近端厨房 y 37–44、远端厨房 y 0–7），将 "NET" 文字移到球网线（y≈22）附近，修正图例与球场线朝向
- [x] 2.3 更新 `src/components/platform/CourtMinimap.test.tsx`：覆盖近端球员渲染在底部、方向与视频/详情页场地图一致的断言

## 3. 小地图停滞状态与点位连续性（前端）

- [x] 3.1 `src/services/videoOverlayHud.ts` 给 `HudPlayer` 增加 `stale: boolean`，`buildVideoOverlayHud` 在 `latest` 落后当前播放时间超过新鲜度阈值（默认 0.5 秒）时标记为停滞
- [x] 3.2 `src/components/platform/CourtMinimap.tsx` 对 `stale` 球员降低透明度、去掉当前位置光晕与方向箭头，并在摘要区域显示丢失/停滞标记
- [x] 3.3 为 `videoOverlayHud` 的停滞判定与 `CourtMinimap` 的停滞渲染补充单元测试

## 4. 身份层位置连续性软接管（后端）

- [x] 4.1 `backend/app/schemas/tracking.py` 的 `PlayerTrackingStatus` Literal 增加 `"tentative"`
- [x] 4.2 `backend/app/vision/player_tracking_engine/player_identity.py` 的 `PlayerIdentityConfig` 增加 `soft_takeover_enabled`、`soft_takeover_max_distance_m`、`soft_takeover_confidence`
- [x] 4.3 `_assign_player` 在"lock hint"与"既有映射"之后、`unmatched` 之前增加软接管路径：取距观测最近、在距离阈值内且本帧未更新的球员；`_update_player` 支持 `tracking_status="tentative"` 与低置信度截断；记录 `soft_takeover_assigned` 诊断
- [x] 4.4 在 `backend/tests/test_player_identity.py` 增加软接管测试：阈值内就近指派、超阈值 unmatched、一帧去重、lock hint 优先

## 5. 检测框标签接入软接管（后端 pipeline）

- [x] 5.1 `backend/app/services/analysis_pipeline.py:1832` 的 `player_by_track` 过滤从 `tracking_status == "detected"` 放宽为 `in ("detected", "tentative")`
- [x] 5.2 验证软接管样本写入检测框 `player_id`（标签显示 canonical ID），并确认 `court_track_postprocessor` 对 `tentative` 样本的保守处理（不计入可靠 detected 统计、仍进入轨迹分段）

## 6. 验证与回归

- [x] 6.1 运行后端相关 pytest（`test_player_identity`、`test_player_lock_manager`、`test_api_smoke`、`test_match_format_analysis`）
- [x] 6.2 运行前端 typecheck、lint 与相关 Vitest（`CourtMinimap`、`VideoAnalysisCard`、`videoOverlayHud`）
- [x] 6.3 打开真实任务视觉分析页核对：默认收起不遮挡播放控件、展开可再收起、小地图方向与视频一致、球员点位随视频更新不滞后、中段检测框标签保持 `P1-P4`
