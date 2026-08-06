## Why

人体检测（YOLO）与姿态识别（RTMPose）的启用状态目前只由后端进程全局配置决定（环境变量/权重文件），创建任务时前端无法控制。用户遇到"任务跑完人物框/骨架全部不可用"的问题时只能重启后端改环境变量，无法按任务粒度选择。需要在上传视频时提供开关，让用户按任务选择是否运行这两类模型推理。

## What Changes

- 前端「新建分析」页（上传视频/四角标定完成后）新增**两个独立开关**：人体检测（YOLO）与姿态识别（RTMPose），默认全部开启，用户可手动关闭。
- 任务创建 API payload（`AnalysisJobCreate`）与前端请求类型（`AnalysisJobRequest`）新增两个可选字段：`enableModelInference`、`enablePoseInference`；**未显式传入时沿用后端全局配置**（向后兼容，旧前端行为不变）。
- 后端 `AnalysisPipeline` 支持任务级开关覆盖：开启时创建真实 `PersonDetector`/RTMPose 姿态器，关闭时使用空检测器/跳过姿态（与全局关闭行为一致）。
- `AnalysisJobSummary` 新增两个字段记录任务实际使用的开关状态，任务管理页与任务详情展示（如"推理：检测开 / 姿态关"）。
- 任务去重签名（`configSignature`）纳入任务级开关值，避免相同输入不同开关配置被去重合并。
- 无标定（limited）或 demo 模式下检测阶段本就跳过，前端开关旁提示"需场地标定后生效"。

## Capabilities

### New Capabilities

（无新增能力）

### Modified Capabilities

- `video-analysis-job-flow`: `Analysis job creation` 需求扩展——创建分析任务时支持携带任务级推理开关（人体检测/姿态识别），前端上传页提供对应开关控件。
- `match-analysis-pipeline-capabilities`: `可配置激活比赛分析能力` 需求扩展——pipeline 按任务级开关决定是否运行 YOLO 人体检测与 RTMPose 姿态推理，覆盖全局配置。
- `analysis-task-management`: 新增「分析任务推理开关展示」需求——任务摘要暴露 `enableModelInference`/`enablePoseInference` 字段并在任务管理页/详情页展示。

## Impact

- 后端：
  - `backend/app/schemas/analysis.py`：`AnalysisJobCreate` +2 可选字段；`AnalysisJobSummary` +2 字段（含默认值，兼容旧任务记录缺失）。
  - `backend/app/services/analysis_pipeline.py`：`AnalysisPipeline.__init__` +2 可选覆盖参数，检测器/姿态器按覆盖值创建。
  - `backend/app/services/mock_analysis.py`：`_pipeline_factory` 接受任务级配置并透传；任务摘要构建时写入开关字段。
  - `backend/app/services/job_orchestration.py`：worker 调用 pipeline 时透传任务级开关；`analysis_signature` config 签名加入两字段。
- 前端：
  - `src/services/analysisClient.ts`：`AnalysisJobRequest` +2 可选字段，`createAnalysisJob` 透传。
  - `src/pages/NewAnalysisPage.tsx`：提交区新增双开关（默认开）+ 无标定提示。
  - `src/types/report.ts`：`AnalysisJobSummary` 类型 +2 可选字段。
  - `src/pages/AnalysisTasksPage.tsx` / `AnalysisJobPage.tsx`（或详情页）：任务信息展示开关状态。
- 后端测试：新增/更新 pipeline 与 schema 单测（开关覆盖、默认沿用全局、签名变化）。
- 兼容性：旧前端不传新字段 → 后端 None → 沿用全局配置，行为不变；旧任务记录缺字段 → 摘要默认值兜底。
