## Context

`redesign-video-analysis-overlay` 交付后的小地图（`CourtMinimap`）与视频叠加（`VideoAnalysisCard`）在真实任务上暴露出四类问题：

1. 小地图为竖长条（SVG 180×330，约 1:1.83），非全屏时从右上向下延伸，会压到右下角播放控件栏（含全屏按钮）。
2. 视频中段检测框标签从 `P1-P4` 退化为 `person`：检测框 `player_id` 只在本帧身份层成功分配时写入（`analysis_pipeline.py:1861`），而身份层分配只认 lock hint 或既有映射（`player_identity.py:_assign_player`）；中段多目标跟踪器产生的**新 track_id** 在拿到 hint 前一律 `unmatched`。
3. 小地图近/远方向与视频相反：标定把"图像上方（远侧）"映射到 court y=0，而 `CourtMinimap` 的 `toSvg` 做了 y 翻转且假设 y=0 为近侧，导致近端球员显示在顶部。
4. 小地图点位滞后：身份中段丢失后，身份层停止为该球员产出新样本，小地图停在最后已知位置（可能是底线），与继续播放的视频脱节。

约束：不改变 lock manager 的硬锁状态机；不改变现有 artifact 字段语义；不要求旧任务产物迁移；不改球检测/标定算法本身。

## Goals / Non-Goals

**Goals:**

- 小地图默认收起，仅在用户主动展开时显示，展开后不遮挡播放控件。
- 通过身份层**位置连续性软接管**，让中段新 track 也能被就近归入既有球员槽位并产出低置信度 `tentative` 样本，保持检测框 `P1-P4` 标签与小地图点位持续更新。
- 小地图球场方向与视频拍摄方向一致（近端在底部、远端在顶部）。
- 小地图对落后于当前播放时间的点位显示停滞/丢失状态，不再伪装成"当前位置"。

**Non-Goals:**

- 不改 lock manager 状态机（SEARCHING/TENTATIVE/LOCKED/LOST 语义不变；软接管在身份层兜底，lock hint 仍优先）。
- 不改标定/homography 算法，不做后端 near/far 语义的整体翻转（见 Risks）。
- 不改球检测、弹跳检测、骨架、发球检测算法。
- 不新增后端 API，不改 `P1-P4` 之外的对外字段。

## Decisions

### 1. 小地图默认收起，手动展开（前端）

`RealVideoOverlay` 增加 `showCourtHud: boolean`（默认 `false`）。在右上角图层控制簇旁增加一个地图切换按钮；收起时只显示按钮，展开时显示 `CourtMinimap` 并保留按钮可再次收起。

- **为什么默认收起**：视频是主视觉，小地图是复盘辅助；默认收起天然消除遮挡，且与 design.md 决策 6（不遮挡）一致。
- **备选**：按视口高度自动折叠。更"聪明"但不可预测，且实现复杂，弃用。
- **展开后仍不挡控件**：地图容器 `max-h` 约束 + 播放控件栏保持更高可用性；展开态按钮常驻，短视口下用户可一键收起。

### 2. 身份层位置连续性软接管（后端）

在 `player_identity.py::_assign_player` 中，在"lock hint"与"既有映射"之后、`unmatched` 之前新增第三条路径：对**合格且在球场范围内、既无 hint 也无映射**的观测，找到 `last_position_m` 距该观测最近、且在 `soft_takeover_max_distance_m` 阈值内、且**本帧尚未被更新**的球员槽位，把 track 绑定到该 `player_id` 并产出样本。

- 样本标记：`PlayerTrackingStatus` 新增 `"tentative"`（`schemas/tracking.py:61` 的 Literal），`tracking_status="tentative"`、`is_interpolated=False`、`source="detector"`，置信度取 `min(观测置信度, soft_takeover_confidence)`。
- `analysis_pipeline.py:1832` 的 `player_by_track` 过滤从 `tracking_status == "detected"` 放宽为 `in ("detected", "tentative")`，这样软接管样本才会写入检测框 `player_id`，标签恢复 `P1-P4`。
- 本帧去重：`_update_player` 会把 `last_seen_frame` 置为当前帧；软接管候选只挑 `last_seen_frame != 当前帧` 的球员，天然避免一帧内两名 track 抢占同一身份。
- 优先级：`_assign_player` 先查 hint（lock 权威）→ 再查既有映射 → 再软接管。lock 一旦追上并给出 hint，立即取代软接管，不与硬锁冲突。
- 诊断：新增 `soft_takeover_assigned` 诊断事件（`player_identity._diagnose` 的 `event` 为字符串，向后兼容；`_RENDER_EVENT_MAPPING` 未映射的事件会被忽略，不影响分段语义）。
- 配置：新增 `soft_takeover_enabled: bool = True`、`soft_takeover_max_distance_m: float = 4.0`、`soft_takeover_confidence: float = 0.45`。

- **为什么在身份层而非 lock 层**：lock 层是硬锁的权威，改动它要动状态机且风险大；身份层做兜底只影响"标签归属"，且 lock hint 仍优先，冲突最小。
- **备选**：放宽 lock 的 reconnect 门控。会让 LOST 槽位更容易抢占，改变锁定语义，弃用。

### 3. 修正小地图 y 轴方向（前端）

`CourtMinimap.tsx::createMapper` 的 `toSvg` 去掉 y 翻转：

```
// 之前：svgY = VIEW_HEIGHT - (offsetY + (y - yMin) * scale)
// 之后：svgY = offsetY + (y - yMin) * scale
```

同时把厨房区多边形换位（近端厨房用 y 37–44、远端厨房用 y 0–7），"NET" 文字移到球网线（y≈22）附近而非当前底部。球场/边界多边形、球网线、中线均经 `toSvg`，自动随翻转修正。

- **为什么这样是"对"的**：标定把图像上方（视频远侧）映射到 court y=0，故投影数据里**近端在 y≈44、远端在 y≈0**。`AnalysisDetailsPage.StandardCourtPlan` 直接以 court 坐标直出并标"近端底线"在底部，与投影数据、视频一致；`CourtMinimap` 之前做了 y 翻转且假设 y=0=近，故颠倒。把 minimap 改为与 `StandardCourtPlan`/投影数据一致（近端在底部）即修正方向，且 P1-P4 点的相对位置也随视频一致。
- **备选（弃用）**：改标定对应关系让 near=low-y（对齐 `court_geometry.py` 文档约定）。这会一次性翻转整个后端 near/far 分类与全部下游（lock 槽位、发球底线、near-clip 补偿等），回归风险高，且与本次用户可见问题无直接对应，故不在本 change 处理（见 Risks）。

### 4. 小地图停滞/丢失状态（前端）+ 由软接管保证连续性

`videoOverlayHud.ts::buildVideoOverlayHud` 对每个球员增加 `stale: boolean`：`latest.timestampSeconds < currentTime - staleThresholdSeconds`（默认 0.5s）即视为停滞。`CourtMinimap` 对停滞球员**降低透明度、去掉光晕与方向箭头**，并在底部摘要标"丢失"。

- 主修复是第 2 点的软接管——身份连续 → 小地图持续拿到新点，自然不再滞后；停滞态只是数据真中断（如长遮挡）时的诚实降级。
- 备选：不做停滞态、只依赖软接管。但软接管阈值外仍有数据空洞，诚实展示比误导性"当前位置"更符合 design.md 决策 6（真实数据优先）。

## Risks / Trade-offs

- [软接管可能把球场附近误入者/观众误配到某球员] → 距离阈值（4m）+ 必须合格 track + 只对"本帧未更新的球员"生效；且 lock hint 优先，最终身份仍由 lock 校正。
- [软接管样本被 `court_track_postprocessor` 当作非 detected，影响"可靠起点/主侧"统计] → 这是保守方向（tentative 不提升为高置信度统计），可接受；轨迹分段仍包含这些点，保证连续性。
- [后端 near/far 语义相对摄像头整体颠倒（court_geometry 文档约定 y=0=近 与 实际标定 y=0=远 不一致）] → 本 change 只对齐前端 minimap 到"实际投影数据/视频"，不动后端语义；该不一致另立 change 处理，避免一次回归面过大。
- [新状态 `tentative` 被旧代码误判] → 仅新增 Literal 值，读取方多为 `== "detected"` 判断，tentative 落到"非可靠"分支（保守安全）；已排查 `court_track_postprocessor.py:147`、`analysis_pipeline.py:1832` 并做相应放宽。

## Migration Plan

1. 前端先行：`CourtMinimap` y 轴修正 + 折叠交互 + `videoOverlayHud` 停滞态，前端测试同步更新，可独立上线。
2. 后端次之：`PlayerTrackingStatus` 增加 `tentative`、`player_identity` 软接管、pipeline `player_by_track` 放宽，后端测试同步更新。
3. 旧任务产物不迁移：新增字段/状态向后兼容；新分析自动受益。
4. 回滚：前端回滚组件即可；后端软接管可用 `soft_takeover_enabled=false` 关闭，不影响其余逻辑。

## Open Questions

- `soft_takeover_max_distance_m` 默认 4.0m 是否合适，需在真实 60 FPS 视频上观察后再调参（可能缩到 3.0m 或放到 5.0m）。
- 软接管样本是否需要在检测框上做视觉区分（如 `P1?` 或降低标签透明度）？当前方案保持 canonical 标签 + 框置信度不变，先不加视觉区分，避免范围膨胀。
- 后端 near/far 语义与文档约定的整体不一致，是否要单独立 change 修正标定对应关系？（本 change 明确不处理。）
