# metric-court-scene-calibration Specification

## Purpose

定义以采集任务为边界、以球场和球网非共面几何为约束的度量级 3D 球场场景标定能力。首版通过人工标注生成可复用场景 revision，并为未来自动建议保留 provenance 和人工确认入口。

## ADDED Requirements

### Requirement: 采集任务级场景标定资产

系统 SHALL 以 `capture_take_id` 作为默认场景标定边界，为同一采集任务内的多个录制视频和视角生成可复用的 `metric_court_scene.v1` asset。AnalysisJob SHALL 通过 revision reference 使用该 asset，不得复制或隐式重算场景几何。

#### Scenario: 同一采集任务复用场景
- **WHEN** 同一 `capture_take_id` 下创建多个双摄分析任务或读取多个录制视频
- **THEN** 系统 SHALL 允许它们引用同一个已发布 scene calibration revision
- **AND** 每个任务 artifact SHALL 保存所引用的 `capture_take_id` 与 revision

#### Scenario: 场景 revision 不可变
- **WHEN** 用户修改已发布场景中的球网点位、相机配置或 Canonical Court Frame reference
- **THEN** 系统 SHALL 创建新的 revision 或 draft
- **AND** SHALL NOT 原地覆盖已被任务引用的 revision

### Requirement: 人工球网标注与草稿微调

首版 SHALL 支持按 view 对球网左端、中心、右端进行人工标注，并 SHALL 支持可选的四分之一点和网柱落地点。标注 SHALL 保存 image-space 坐标、对应的 canonical 3D control point、来源、确认状态和使用的 frame/video provenance。

#### Scenario: 完成最小人工标注
- **WHEN** 用户为每个必需视角完成球网两端和中心标注并确认
- **THEN** 系统 SHALL 保存一个可继续编辑的 draft
- **AND** SHALL 显示标准 profile 或现场 measured profile 在当前图像上的回投预览

#### Scenario: 恢复和微调草稿
- **WHEN** 用户重新进入同一采集任务的场景标定工作台
- **THEN** 系统 SHALL 恢复最近的 draft 点位和 profile 选择
- **AND** 用户 SHALL 能拖动点位并重新提交质量检查

### Requirement: 标准球网高度 profile

系统 SHALL 支持标准球网顶部 profile：按项目 Canonical Court Frame，球网两侧边线位置的高度为 `0.9144 m`，中心高度为 `0.8636 m`。系统 SHALL 以三维 profile 表达球网顶部，不得把整个球网顶部固定为单一水平高度。

#### Scenario: 标准 profile 序列化
- **WHEN** 用户选择标准球网高度
- **THEN** scene asset SHALL 保存两端、中心的三维控制点及 `height_source = standard`
- **AND** profile SHALL 在两端达到 91.44 cm、中心达到 86.36 cm

#### Scenario: 现场 measured profile
- **WHEN** 用户提供现场实测高度或额外 profile 控制点
- **THEN** 系统 SHALL 保存 `height_source = measured` 及测量 provenance
- **AND** 该 profile SHALL 优先于默认标准 profile 参与相机 refinement 和场景渲染

### Requirement: 固定机位场景适用范围

系统 SHALL 将同一采集任务内的摄像机位置、角度、镜头设置和图像尺寸视为固定输入，不得在正常分析过程中逐帧动态重标定。场景 asset SHALL 保存适用 view、video identity 和 image size。

#### Scenario: 固定机位跨录制视频复用
- **WHEN** 同一采集任务中的多个录制视频保持相同 camera identity、视角和图像尺寸
- **THEN** 系统 SHALL 允许复用同一 scene calibration revision
- **AND** SHALL 不要求用户为每个录制视频重复标注球网

#### Scenario: 输入不属于固定场景
- **WHEN** 新视频的 camera identity、视角、镜头配置或图像尺寸与 revision provenance 不一致
- **THEN** 系统 SHALL 拒绝静默复用旧 revision
- **AND** SHALL 要求创建新的 scene revision 或显式进入 approximate fallback

### Requirement: 场景标定质量门

只有同时通过球场/球网回投、相机姿态消歧、深度范围、双视角几何质量和 provenance 完整性检查的 revision，才可标记为 `ready` 并作为 metric scene calibration 使用。系统 SHALL 保存每个 view 和整体质量诊断。

#### Scenario: 质量门通过
- **WHEN** 所有必需视角的 control point 回投、相机前方性、Canonical frame 一致性和双视角 ray geometry 均通过阈值
- **THEN** revision SHALL 标记为 `ready`
- **AND** SHALL 提供可供双摄分析引用的 revision id

#### Scenario: 质量门失败
- **WHEN** 任一视角控制点不足、回投误差过大、姿态消歧失败或 Z 轴几何病态
- **THEN** revision SHALL 标记为 `degraded` 或 `invalidated`
- **AND** SHALL 保存结构化 rejection reason
- **AND** SHALL 不得把该 revision 作为 metric 高度依据

### Requirement: 标定来源与自动建议扩展点

场景标定 SHALL 支持 `manual`、`auto_suggested` 和 `manual_verified` provenance。首版 SHALL 只要求人工标注和人工确认；未来自动识别 SHALL 只能生成 suggestion，不得绕过确认和质量门直接发布 `ready`。

#### Scenario: 人工确认自动建议
- **WHEN** 未来自动识别器提供球网点位建议
- **THEN** 系统 SHALL 将其保存为 `auto_suggested`
- **AND** 用户确认或修正后 SHALL 转换为 `manual_verified`

#### Scenario: 没有自动模型
- **WHEN** 当前运行环境未配置球网自动识别模型
- **THEN** 人工标注流程 SHALL 仍可完整生成 scene revision
- **AND** 系统 SHALL 不把缺少自动模型视为标定失败

### Requirement: 场景不确定度可追溯

系统 SHALL 在 scene asset 中保存球网控制点误差、相机回投误差、双视角 ray geometry 和高度不确定度摘要。下游 3D 球路 SHALL 能引用这些不确定度，而不是只保存一个无来源的 `z` 数值。

#### Scenario: 高度不确定度传播
- **WHEN** 双摄球路使用某个 scene revision 进行三角测量
- **THEN** measurement 或重建 sample SHALL 保存 scene revision reference、相机模型来源和高度不确定度
- **AND** 下游 SHALL 能区分 metric、approximate 和 visualization-only 高度
