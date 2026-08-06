## 1. 后端 schema 与任务摘要

- [x] 1.1 `backend/app/schemas/analysis.py`：`AnalysisJobCreate` 新增 `enableModelInference: Optional[bool] = None`、`enablePoseInference: Optional[bool] = None`；`AnalysisJobSummary` 新增同名字段（默认 None）
- [x] 1.2 任务创建时把 None 解析为全局 settings 值后固化进 summary（在 job 持久化处统一处理），并写入 job json

## 2. 后端 pipeline 任务级覆盖

- [x] 2.1 `AnalysisPipeline.__init__` 新增 `enable_model_inference: bool | None = None`、`enable_pose_inference: bool | None = None`，检测器/姿态器按覆盖值创建（None 用 settings）
- [x] 2.2 `mock_analysis.py` `_pipeline_factory` 接受可选任务级配置并透传给 `AnalysisPipeline`
- [x] 2.3 `job_orchestration.py` worker `run_job` 调用 factory 时透传 payload 的两个开关值
- [x] 2.4 `analysis_signature` config_payload 的 `enableModelInference`/`enablePoseInference` 改用任务级解析值（None→settings）

## 3. 后端测试

- [x] 3.1 schema 测试：新字段可选、默认 None
- [x] 3.2 pipeline 测试：enable=true 时检测/姿态启用、false 时走空检测器/跳过姿态、None 时沿用全局（覆盖现有 `test_analysis_pipeline_ball.py:444` 的 enable_model_inference=False 场景）
- [x] 3.3 签名测试：同输入不同开关配置签名不同
- [x] 3.4 后端测试套件全量通过

## 4. 前端类型与请求透传

- [x] 4.1 `src/types/report.ts`：`AnalysisJobSummary` 新增 `enableModelInference?`、`enablePoseInference?`
- [x] 4.2 `src/services/analysisClient.ts`：`AnalysisJobRequest` +2 可选字段，`createAnalysisJob` body 透传

## 5. 上传页双开关 UI

- [x] 5.1 `NewAnalysisPage.tsx` 提交区新增两个 toggle（人体检测 YOLO / 姿态识别 RTMPose），`useState(true)` 默认开启
- [x] 5.2 无标定（limited/demo）时开关可见并显示"需场地标定后生效"提示
- [x] 5.3 提交时把开关值传入 `createAnalysisJob`

## 6. 任务摘要/详情展示

- [x] 6.1 任务管理页任务卡展示开关徽标（如"检测开 / 姿态关"），字段缺失时按"沿用全局"兜底
- [x] 6.2 任务详情页（`AnalysisJobPage`）任务信息区展示两个开关状态

## 7. 验证

- [x] 7.1 后端 `pytest` 全量通过；前端 `npm test` 与 `npm run build` 通过
- [x] 7.2 端到端：用当前后端（全局关闭）创建默认开启的任务 → 检测/姿态启用；创建手动关闭的任务 → skipped；验证任务卡/详情展示开关状态
- [x] 7.3 `openspec validate --changes` 通过
