## Context

人体检测（YOLO）与姿态识别（RTMPose）的启用开关目前只存在于后端全局配置（`backend/app/core/config.py`）：
- `enable_model_inference`：仅由环境变量 `PICKLEBALL_ENABLE_MODEL_INFERENCE` 决定（默认 true；空串/0/no 解析为 false）；
- `enable_pose_inference`：显式环境变量优先，否则按 RTMPose config/checkpoint 权重文件是否存在自动判断。

`AnalysisPipeline.__init__` 构造时按全局 settings 决定创建真实 `PersonDetector` 还是 `EmptyPersonDetector`、是否初始化 RTMPose 姿态器，**任务运行时无法改变**。worker 通过 `_pipeline_factory()`（`mock_analysis.py:69`）无参构造 pipeline。

实际案例：任务 `job-88ce6f798c` 因后端进程环境被注入 `PICKLEBALL_ENABLE_*=false`，导致人体检测/姿态全部 skipped，用户只能重启后端改环境变量，无法按任务选择。

## Goals / Non-Goals

**Goals:**
- 上传视频页提供两个独立开关（人体检测/姿态识别），默认全部开启。
- 任务级开关覆盖后端全局配置；未显式选择时沿用全局（向后兼容）。
- 任务摘要/详情展示每个任务实际使用的开关状态。
- 去重签名区分不同开关配置的任务。

**Non-Goals:**
- 不改变球检测、发球检测等其他分析能力的开关模型（本次仅 YOLO 人体检测 + RTMPose 姿态）。
- 不提供运行时（分析中）切换开关的能力。
- 不修改全局配置的默认语义（`PICKLEBALL_ENABLE_MODEL_INFERENCE` 默认仍为 true）。

## Decisions

### D1: 覆盖注入点在 `AnalysisPipeline.__init__`（而非 `run`）
检测器与姿态器在构造时按配置创建，`run` 阶段已定死。因此给 `__init__` 增加两个可选参数 `enable_model_inference: bool | None`、`enable_pose_inference: bool | None`，构造时优先用覆盖值。
- 备选：在 `run()` 参数传入再动态重建检测器——运行期重建模型开销大、破坏现有阶段进度语义，否决。

### D2: `_pipeline_factory` 接受任务级选项
`_pipeline_factory()` 改为接受 `analysis_options: dict | None`，worker 在 `run_job` 中把 payload 的两个开关值透传；`AnalysisPipeline` 构造时收到 None 的字段沿用全局 settings。
- 保持 worker 现有 `inspect.signature` 兼容机制不变（pipeline.run 参数过滤逻辑不受影响）。

### D3: 任务摘要固化解析后的开关值
`AnalysisJobCreate`/`AnalysisJobSummary` 新增 `enableModelInference: Optional[bool]`、`enablePoseInference: Optional[bool]`。任务创建时把 **None 解析为全局 settings 当前值**后写入 summary，保证：
- 展示总是有确定值（旧任务记录缺字段时用全局兜底）；
- 后续读 job json 不回查进程环境（进程重启前后行为稳定）。

### D4: 去重签名纳入任务级开关
`analysis_signature` 的 config_payload 加入 `enableModelInference`、`enablePoseInference`（None 时取 settings 值，与 D3 一致），避免同输入不同开关被 `find_by_signature` 合并。注意：之前 `job_orchestration.py:291` 已有全局 settings 值参与签名，本次替换为任务级解析值（默认情况下与全局一致，签名兼容旧任务哈希不受影响——旧任务未存这两个字段，用全局值参与签名即可，保持确定性）。

### D5: 前端双开关默认开启
`NewAnalysisPage` 提交区新增两个 toggle（人体检测 YOLO / 姿态识别 RTMPose），`useState(true)` 默认开启；`AnalysisJobRequest` 与 `createAnalysisJob` 透传两个布尔值。无标定（limited/demo）时开关保持可见但显示提示文案"需场地标定后生效"。

### D6: 展示文案与兼容
任务管理页任务卡与任务详情页展示紧凑徽标（如"检测开 / 姿态关"），由 `enableModelInference`/`enablePoseInference` 派生；字段缺失时按"未知/沿用全局"展示，不渲染失败。

## Risks / Trade-offs

- [全局环境变量被注入 false 时，前端默认"开"仍会以 true 覆盖，用户可能没意识到覆盖了全局] → 创建页开关默认开是明确需求（默认都打开）；任务详情展示实际值，可回溯。
- [旧任务 json 缺新字段，读取时 KeyError/None] → 摘要字段默认 None，展示层按"沿用全局"兜底，不抛错。
- [后端测试改动面较大（pipeline 构造签名变化）] → 保持 `__init__` 新参数为可选、默认 None，现有测试不受影响；仅新增覆盖用例。
- [`_pipeline_factory` 签名变化影响 worker 调用点] → 改动限定在 `mock_analysis.py` 的 factory 与 `job_orchestration.run_job` 的调用处，参数默认 None 向后兼容。

## Migration Plan

- 纯代码变更 + job json 追加字段，无数据库迁移。
- 部署顺序：先合并后端（新 payload 字段可选、兼容旧前端），再合并前端（透传新字段）。
- 回滚：后端字段可选，前端回退后行为回到全局配置，无破坏。

## Open Questions

- （无，探索阶段已与用户确认：两个独立开关；任务摘要展示开关状态。）
