## ADDED Requirements

### Requirement: view_scale_profiled 与 stale 淡化样式

视频叠加 HUD SHALL 支持 `bbox_source=view_scale_profiled` 的展示语义：以虚线框呈现（与 `last_good_bbox_reanchored` 的跨摄补全虚线族一致，可按来源微调透明度/标签），MUST NOT 伪装为真实 YOLO 检测实线框。前端 SHALL 在 `bbox_stale=true` 时淡化 bbox（如降低透明度/加"陈旧"标记），淡化程度 SHALL 基于后端提供的 `bbox_age_ms`（MUST NOT 前端自行估算）。`display_state` 存在时 SHALL 用于视觉语义（如 `REAL_BOX` 实线、`PROJECTED_BOX` 虚线、`PROJECTED_POINT` 光圈）。

#### Scenario: scale profile 虚线框

- **WHEN** overlay entity 的 `bbox_source == "view_scale_profiled"`
- **THEN** 前端 SHALL 以虚线框渲染
- **AND** 可显示来源标签（如"尺度投影"）区分于真实检测

#### Scenario: stale bbox 淡化

- **WHEN** overlay entity 的 `bbox_stale == true` 且存在 `bbox_age_ms`
- **THEN** 前端 SHALL 淡化该 bbox
- **AND** 淡化程度 SHALL 基于 `bbox_age_ms`（不自行估算）

#### Scenario: 旧枚举兼容

- **WHEN** overlay entity 的 `bbox_source` 为既有值（`last_good_bbox_reanchored` / `none`）或缺失，或 `display_state/bbox_stale/bbox_age_ms` 缺失
- **THEN** 前端 SHALL 按既有样式渲染
- **AND** SHALL NOT 因新枚举值或新字段缺失破坏解析
