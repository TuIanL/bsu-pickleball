# ball-tracking Specification

## Purpose
Define the inactive state for ball detection, trajectory, overlay, and event-analysis artifacts while the active product flow focuses on player movement and pose analysis.
## Requirements
### Requirement: Ball detection artifact
系统 SHALL 在球检测启用且所需 detector 依赖可用时，为真实分析任务创建并暴露球检测 artifact，包括 `ball_overlay.json`（帧级叠加数据）、`detections.jsonl`（共享检测合同）和 `ball_trajectory.json`（轨迹连续采样）。

#### Scenario: Ball detection enabled and candidates are produced
- **WHEN** 真实分析任务启用球检测且配置的 detector 输出可用球候选
- **THEN** backend SHALL 写入 `ball_overlay.json`（帧级叠加数据）
- **AND** backend SHALL 将球检测记录写入共享 `detections.jsonl` artifact 合同
- **AND** backend SHALL 写入 `ball_trajectory.json`（原始轨迹 sample）
- **AND** job result SHALL 暴露生成的 artifact URL、status 和 detail

#### Scenario: Ball detection disabled
- **WHEN** 真实分析任务在球检测关闭时运行
- **THEN** backend SHALL 不生成 `ball_overlay.json`
- **AND** `ball_overlay_status` SHALL 为 `skipped`
- **AND** pipeline SHALL 不因此失败

#### Scenario: Ball detector dependencies are unavailable
- **WHEN** 球检测启用但 detector 配置、模型路径、adapter 或运行时依赖不可用
- **THEN** backend SHALL 将球检测阶段标记为 unavailable 或 failed 并附明确诊断
- **AND** 现有 player movement、pose、tracking、projection 和 serve 输出在自身输入有效时 MUST 继续可用

#### Scenario: Legacy ball artifacts exist
- **WHEN** 旧持久化输出目录仍包含当前 job result 未引用的球 artifact 文件
- **THEN** 系统 SHALL 将这些文件视为旧清理数据而非活跃分析输出

### Requirement: Ball trajectory continuity
The backend SHALL generate ball trajectory continuity artifacts when ball detection is enabled and the pipeline receives usable ball candidate samples.

#### Scenario: Trajectory processing runs
- **WHEN** a current real analysis job runs with ball detection enabled and frame-level ball candidates are available
- **THEN** the pipeline runs ball trajectory filtering, prediction, continuity checks, cleaning, and short-gap interpolation
- **AND** the pipeline writes raw and cleaned ball trajectory artifacts with status and detail

#### Scenario: Trajectory input is unavailable
- **WHEN** ball trajectory processing lacks detector samples, frame timing, or required video metadata
- **THEN** the pipeline records the trajectory stage as skipped, unavailable, partial, or no-candidates with an explanatory detail
- **AND** the job MUST NOT fail solely because ball trajectory output is unavailable

#### Scenario: Player movement remains supported
- **WHEN** ball trajectory processing is omitted, unavailable, or fails in a recoverable way
- **THEN** player/person detection, pose, tracking, projection, and movement metrics remain the supported analysis path

### Requirement: Ball overlay artifact retrieval
系统 SHALL 在 job 生成 `ball_overlay.json` 时通过共享分析 artifact 合同支持球 overlay artifact 获取，返回包含 source metadata、coverage 摘要和 frame 数组的完整 payload。

#### Scenario: Client opens a current job with ball overlay available
- **WHEN** 已完成的当前 job 引用 `ball_overlay.json`
- **THEN** 客户端 MAY 获取并渲染球 overlay 数据作为真实 job 图层
- **AND** 响应 MUST 包含 source metadata（width、height、fps、frame_stride、processed_frame_count）
- **AND** 响应 MUST 包含 coverage 摘要（overlay_frame_count、missing_frame_count、detection_rate）

#### Scenario: Client opens a current job without ball overlay
- **WHEN** 已完成的当前 job 没有生成 ball overlay
- **THEN** 客户端 SHALL 忽略缺失的球 overlay artifact 或标记图层 unavailable
- **AND** 客户端 MUST NOT 渲染模拟球 overlay 数据作为真实 job 结果

#### Scenario: Ball overlay endpoint is requested for a missing current artifact
- **WHEN** 客户端请求未生成 `ball_overlay.json` 的当前 job 的 `ball-overlay`
- **THEN** backend SHALL 返回 404 而非将 artifact name 拒绝为不支持

#### Scenario: Ball overlay endpoint is requested for an existing artifact file
- **WHEN** 客户端请求 job 目录包含 `ball_overlay.json` 的 `ball-overlay`
- **THEN** backend SHALL 通过共享分析 artifact API 返回 JSON artifact

### Requirement: Ball overlay contains frame-level detection data
系统 SHALL 在球检测启用且有候选时写入 `ball_overlay.json`，包含逐帧 image-space bbox/center/confidence 和可选的 court-space 投影点，用于前端视频叠加渲染。

#### Scenario: Ball overlay is generated when detection succeeds
- **WHEN** 真实分析任务启用球检测且逐帧 ball tracker 产生 sample
- **THEN** pipeline SHALL 写入 `ball_overlay.json` 到 `outputs/{job_id}/ball_overlay.json`
- **AND** `AnalysisPipelineResult.artifacts` SHALL 填充 `ball_overlay_json_path`、`ball_overlay_url`、`ball_overlay_status` 和 `ball_overlay_detail`

#### Scenario: Ball overlay records per-frame detection status
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 每个 frame SHALL 通过 `track_status` 字段区分 `detected`（检测到且接受）、`missing`（无候选或未通过连续性检查）、`rejected`（被面积/长宽比/ROI 过滤）

#### Scenario: Ball overlay aligns with ball trajectory frame indices
- **WHEN** `ball_overlay.json` 和 `ball_trajectory.json` 同时生成
- **THEN** 两者的 `frame_index` 和 `timestamp_seconds` MUST 对齐
- **AND** 同一 `frame_index` 的 ball center 坐标 MUST 一致

#### Scenario: Ball overlay is not generated when tracking is unavailable
- **WHEN** 球检测未启用、模型不可用或 pipeline 路径 B/C（无标定/无视频）
- **THEN** `ball_overlay_status` MUST 为 `skipped` 或 `unavailable`
- **AND** `ball_overlay_json_path` 和 `ball_overlay_url` MAY 为 null
- **AND** pipeline MUST NOT failed

### Requirement: Ball tracking does not imply shot events
The system SHALL allow ball tracking, trajectory, and bounce candidate artifacts to become available before full shot, rally, scoring, or tactical event semantics are implemented.

#### Scenario: Ball trajectory facts are available
- **WHEN** a current real-job report surface has ball trajectory or bounce candidate artifacts
- **THEN** the system may present those facts as algorithm-derived candidates
- **AND** the system MUST label them distinctly from complete shot, rally, scoring, or tactical conclusions

#### Scenario: Report requires event semantics
- **WHEN** a current real-job report surface would require hit events, shot classification, rally segmentation, scoring, or tactical conclusions that are not implemented
- **THEN** the system omits that surface or marks it unavailable rather than fabricating event conclusions

