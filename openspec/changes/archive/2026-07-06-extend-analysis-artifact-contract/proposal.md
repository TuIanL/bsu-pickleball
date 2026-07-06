## Why

当前分析平台已经有 `StorageService`、`AnalysisPipelineResult` 和 artifact API 等基础，但新增比赛分析产物仍缺少稳定契约。为了迁移 Good-Pickleball 风格的球轨迹、弹跳点、逐帧检测、标注视频和位置可视化能力，需要先统一这些结果怎么命名、存储、暴露和描述，避免后续算法、Pipeline 和前端各自临时定义格式。

## What Changes

- 新增分析产物契约，定义球相关和位置可视化相关 artifact 的稳定文件路径、API artifact name 和 `AnalysisPipelineResult.artifacts` 字段。
- 扩展 artifact API，使客户端可以通过稳定名称读取新增 JSON、JSONL、视频和 visualization manifest 产物。
- 定义新增 JSON / JSONL schema，包括逐帧检测、球轨迹、清洗球轨迹、弹跳事件、球 overlay 和位置可视化 manifest。
- 增加后续算法接入所需配置项，包括球模型路径、球检测启用、弹跳检测启用、叠加视频启用、位置可视化输出和可视化语言。
- 保持现有 tracking、pose、serve、player trajectory、court-view ROI 等 artifact 名称和行为兼容。
- 明确本 change 不实现球检测、球轨迹清洗、弹跳检测、标注视频生成、热力图生成、散点图生成或前端展示。

## Capabilities

### New Capabilities

- `analysis-artifacts`: 定义分析任务新增 artifact 的存储路径、API 名称、PipelineResult 引用字段和 JSON / JSONL 数据契约。

### Modified Capabilities

- `ball-tracking`: 调整 ball overlay artifact retrieval 语义，从“不支持的 artifact name 返回 422”迁移为“artifact name 已知；当前任务未生成文件时返回 404”。

## Impact

- 后端文件：`backend/app/services/storage_service.py`、`backend/app/schemas/pipeline.py`、`backend/app/api/routes_analysis.py`、`backend/app/core/config.py`。
- 测试文件：`backend/tests/test_api_smoke.py`、`backend/tests/test_config.py`，以及必要的 schema/contract 测试。
- API：`GET /api/analysis/jobs/{job_id}/artifacts/{artifact_name}` 将接受新增 artifact name；不存在的产物仍返回 404。
- 数据契约：`AnalysisPipelineResult.artifacts` 将增加新增产物的 path、url、status 和 detail 字段。
- 本 change 不引入新的运行时算法依赖；如果需要 JSONL 或视频响应处理，应优先复用现有标准库和 FastAPI response 类型。
