## Why

当前自动标定已经能返回分割掩码、角点和基础置信度，但诊断解释力还不够强。对于“为什么这个建议可信”或“为什么这个建议被拒绝”，后端目前主要依赖分割模型置信度和基础几何检查，缺少类似 Good-Pickleball 中 reference line support 这种基于标准球场线投影的一致性证据。

现在补上这层诊断很合适，因为项目已经具备自动标定、预览图生成和上传工作流承接能力。增强解释性可以直接提升人工复核效率，也能让前端在可用、拒绝、低置信度三种状态下给出更可操作的提示。

## What Changes

- 为自动标定建议增加基于标准匹克球场投影线的 reference line support 诊断，用于衡量预测掩码与拟合球场结构的一致性。
- 将自动标定最终置信度从“分割模型置信度 + 几何置信度”扩展为可解释的组合结果，并暴露组成项。
- 扩展自动标定预览内容，使其能够展示检测掩码、关键点、球场覆盖线以及 reference support 相关提示。
- 扩展自动标定返回的结构化 diagnostics 字段，使前端能够显示 reference score、coverage、supported line 数量、拒绝原因和组合置信度来源。
- 在上传/标定工作流中展示更强的自动标定解释信息，帮助用户决定接受、修正还是退回手工标定。

## Capabilities

### New Capabilities

无

### Modified Capabilities

- `automatic-court-line-calibration`: 自动标定推理、后处理、预览和用户侧诊断需要增加 reference line support 解释信息与组合置信度来源。
- `video-analysis-job-flow`: 自动标定建议交互需要展示增强后的诊断字段和预览解释，而不仅是单一 confidence 与基础 rejection detail。

## Impact

- 后端自动标定服务：`backend/app/services/automatic_calibration_service.py`
- 球场后处理与几何诊断：`backend/app/vision/courtvision_calibration_engine/`
- 自动标定响应 schema 与前端消费类型
- 上传/标定工作流中的自动标定诊断展示与预览文案
