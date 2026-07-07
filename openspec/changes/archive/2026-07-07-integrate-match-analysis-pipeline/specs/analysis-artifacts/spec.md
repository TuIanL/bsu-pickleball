# analysis-artifacts Delta Spec

## ADDED Requirements

### Requirement: Ball overlay schema is concretely defined
系统 SHALL 将 `ball_overlay.json` 的 schema 从"可按帧渲染的 ball overlay 数据"具体化为包含 source metadata、coverage 摘要和 frames 数组的完整合同，使前端无需猜测 overlay 结构。

#### Scenario: Ball overlay declares source metadata
- **WHEN** `ball_overlay.json` 被写入
- **THEN** 文件 MUST 包含 `source` object，含 `width`（int）、`height`（int）、`fps`（float）、`frame_stride`（int）、`processed_frame_count`（int）
- **AND** `source` 字段 MUST 即使在 `status` 为 `unavailable` 或 `skipped` 时也存在

#### Scenario: Ball overlay declares coverage metadata
- **WHEN** `ball_overlay.json` 被写入
- **THEN** 文件 MUST 包含 `coverage` object
- **AND** `coverage` MUST 包含 `overlay_frame_count`（int）、`missing_frame_count`（int）、`detection_rate`（float）
- **AND** `detection_rate` MUST 等于 `overlay_frame_count / processed_frame_count`（当 `processed_frame_count > 0`）

#### Scenario: Ball overlay frame specifies per-frame ball data
- **WHEN** `ball_overlay.json` 被写入且有球候选
- **THEN** 每个 frame entry MUST 包含 `frame_index`（int）
- **AND** MUST 包含 `timestamp_seconds`（float）
- **AND** MUST 包含 `ball` object
- **AND** `ball` object MUST 包含 `center`（`{"x": float|null, "y": float|null}`）
- **AND** `ball` object MUST 包含 `bbox`（`[x1, y1, x2, y2]` 或 null）
- **AND** `ball` object MUST 包含 `confidence`（float|null）
- **AND** `ball` object MUST 包含 `track_status`（string: `"detected"`、`"missing"`、`"rejected"`）
- **AND** `ball` object MAY 包含 `court`（`{"x": float, "y": float, "unit": "ft"}` 或 null）

#### Scenario: Ball overlay frames are sparse
- **WHEN** `ball_overlay.json` 被写入
- **THEN** `frames` 数组 MUST 只包含球检测实际运行的抽样帧
- **AND** `frames` 数组 MUST NOT 强制包含每个 frame_index 的条目
- **AND** 帧覆盖缺失情况 MUST 由 `coverage` 元数据表达

### Requirement: Ball engine artifact contract is active
系统 SHALL 将球相关 artifact 合同从"保持可选直到 pipeline 集成"更新为"活跃集成状态"，因为 `AnalysisPipeline` 已在真实路径中写入这些 artifact。

#### Scenario: Pipeline writes all five ball artifacts when enabled
- **WHEN** 球检测启用且有视频和标定
- **THEN** pipeline SHALL 写入 `ball_overlay.json`
- **AND** pipeline SHALL 写入 `detections.jsonl`（包含 player + ball 记录）
- **AND** pipeline SHALL 写入 `ball_trajectory.json`
- **AND** pipeline SHALL 写入 `cleaned_ball_trajectory.json`
- **AND** pipeline SHALL 写入 `bounce_events.json`
- **AND** `AnalysisPipelineResult.artifacts` SHALL 包含上述 artifact 的 path、url、status 和 detail

#### Scenario: Ball artifacts are independently skippable
- **WHEN** 球检测未启用、无标定、无视频或依赖缺失
- **THEN** 缺失的 artifact 字段 SHALL 为 null 或携带 skipped/unavailable 状态
- **AND** 已生成的 tracking、pose、serve 等 artifact MUST 不受影响

## MODIFIED Requirements

### Requirement: Ball overlay can drive browser rendering
系统 SHALL 定义 `ball_overlay.json` 的具体 schema，使前端可以获取包含 source metadata、coverage 摘要和 frames 数组的 payload，按帧渲染球叠加层。

#### Scenario: Ball overlay schema is concrete
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 文件 MUST 包含 `schema_version`（`"ball_overlay.v1"`）
- **AND** MUST 包含 `job_id`
- **AND** MUST 包含 `video_id`
- **AND** MUST 包含 `status` 和 `detail`
- **AND** MUST 包含 `source` object（video frame metadata）
- **AND** MUST 包含 `coverage` object（detection rate summary）
- **AND** MUST 包含 `frames` 数组（每个元素含 `frame_index`、`timestamp_seconds` 和 `ball` object）

#### Scenario: Ball overlay is ready for rendering
- **WHEN** 前端获取 `ball_overlay.json`
- **THEN** 前端 MAY 在对应 video timestamp 处渲染 ball bbox 或 center marker
- **AND** MISSING track_status 的帧 MAY 被跳过或显示为"未检测到"
- **AND** 前端 MUST NOT 需要额外解析 `ball_trajectory.json` 来渲染逐帧球位置
