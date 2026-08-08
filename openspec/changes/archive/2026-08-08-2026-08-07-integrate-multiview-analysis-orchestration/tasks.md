# Tasks: integrate-multiview-analysis-orchestration

## 1. AnalysisJob 契约扩展（Parent/Source 编排字段）

- [x] 1.1 新增 `AnalysisKind = Literal["single_view", "multiview"]`；`AnalysisJobSummary` 增加 `analysisKind`（缺省按 `single_view` 兼容历史 job）
- [x] 1.2 新增 `Visibility = Literal["public", "internal"]`，`AnalysisJobSummary.visibility` 缺省 `"public"`
- [x] 1.3 新增 `parentJobId: str | None` 与 `analysisScope: Literal["full", "perception"] | None`（**Parent 为 None 不适用**；child 恒 `"full"`；`perception` 只预留不实现裁剪）
- [x] 1.4 新增独立维度 `orchestrationStatus: AnalysisOrchestrationStatus`，`Literal["none","waiting_sources","fallback_ready","fusion_ready","fusing","composing","completed"]`；`canonicalStatus` 五态不变
- [x] 1.5 新增 `fusionRunId: str | None`（执行融合前持久化）、`sourceJobs: list[{cameraSlot, jobId}]`（数组，非 `childJob1/childJob2` 双字段）与 `viewRuns`（`cam_1 / cam_2` 各自 `status / stage / progress`）
- [x] 1.6 单元测试：历史 job 无新字段时读取兼容；`analysisKind`/`visibility`/`orchestrationStatus` 缺省值正确

## 2. `claim_next()` 统一收口为 `is_runnable(job)`

- [x] 2.1 实现 `is_runnable(job)`：`canonicalStatus != "queued"` → False；`single_view` → True；`multiview` → `orchestrationStatus ∈ {fusion_ready, fallback_ready}`
- [x] 2.2 `JobStore.claim_next()` 改用 `is_runnable()`，不再直接写 `canonicalStatus == "queued"`
- [x] 2.3 单元测试：`waiting_sources` 的 Parent 被 `claim_next` 跳过（返回 None），不占用 Worker；`fusion_ready`/`fallback_ready` 可被领取

## 3. Worker 执行分发层（Executor Protocol + registry）

- [x] 3.1 定义 `AnalysisJobExecutor` Protocol：`execute(job, token, progress_callback) -> AnalysisPipelineResult`；**第一版不过度框架化**——`executor_registry` 仅含 SingleView / MultiView 两个执行体，不做插件发现/通用 factory/第三方扩展 API
- [x] 3.2 实现 `SingleViewAnalysisExecutor`：把现有 `_execute` 重建 `AnalysisJobCreate` + `pipeline_factory().run()` 的逻辑原样搬入（回归：现有单摄 job 行为不变）
- [x] 3.3 实现 `executor_registry: dict[AnalysisKind, AnalysisJobExecutor]`；`AnalysisWorkerRuntime._execute` 改为 `executor_registry.resolve(job.analysisKind).execute(...)`；取消/重试/超时兜底逻辑保留在 Worker 或 Executor 层（明确归属，不重复）
- [x] 3.4 实现 `MultiViewAnalysisExecutor`：读两路 child artifact → 构建/复用 `MultiViewFusionRun` → 融合 → `MultiViewResultComposer` → 返回 `AnalysisPipelineResult`（completed + 聚合 stages）
- [x] 3.5 单元测试：registry 按 `analysisKind` 分发正确；未知 kind 抛稳定错误；单摄回归测试全绿

## 4. MultiViewAnalysisCoordinator（Parent + dedicated internal Child）

- [x] 4.1 实现 `MultiViewAnalysisCoordinator.create_multiview_job(payload)`：创建 1 个 public Parent（`analysisKind=multiview`, `orchestrationStatus=waiting_sources`）+ 2 个 dedicated internal child（`parentJobId=parent.id`、`visibility=internal`、`analysisScope=full`、`cameraSlot=cam_1/cam_2`）；Parent 侧 `sourceJobs` 记录为数组 `[{cameraSlot, jobId}]`
- [x] 4.2 实现事件驱动推进：监听 child completion → 两路 completed → Parent `fusion_ready`；单路失败/取消 → Parent `fallback_ready`；双路失败 → Parent `failed`；至少一路非终态 → 保持 `waiting_sources`
- [x] 4.3 实现 child 恒 dedicated/owned：即使输入签名相同也不复用另一个 Parent 的 child（加测试断言）
- [x] 4.4 单元测试：创建 Parent 返回且 child 落盘为 internal；child 不跨 Parent 复用；`waiting_sources` 时 Parent 不可 claim

## 5. Parent/Child 状态聚合与应用启动 reconciliation

- [x] 5.1 Parent `AnalysisJobSummary.viewRuns` 暴露两路 `status / stage / progress` 聚合
- [x] 5.2 实现启动 reconciliation 第一轮：扫描 `analysisKind=multiview AND canonicalStatus not terminal`，按 child 终态把 Parent 推进到 `fusion_ready / fallback_ready / failed / 保持 waiting_sources`（child 非终态交给现有 zombie recovery）
- [x] 5.3 实现 reconciliation 第二轮：`fusion_ready / fallback_ready` 且无 worker 所有者 → 保持 `canonical queued`，等待 `claim_next`
- [x] 5.4 单元测试：模拟重启，Parent 在 child 已完成时恢复为 `fusion_ready` 并被 claim；与现有 `recover_zombie_jobs()` 职责不重叠（各自独立测试）

## 6. Parent cancel / delete cascade 与 Child 外部保护

- [x] 6.1 取消 Parent：`waiting_sources` → Parent canceled + owned 非终态 child cancel；`fusion_ready` → Parent canceled（child 已 terminal 不动）；`running fusion` → Parent `cancelRequestedAt`，Executor 查 token → canceled
- [x] 6.2 取消 Child：外部 API 返回 `403 / blocked`（`internal source job cannot be canceled directly`）；Coordinator 内部允许
- [x] 6.3 删除 Parent：非终态沿用现有 blocked；terminal → 级联删除 Parent 分析产物 + owned child 分析产物 + fusion run 产物 + parent artifacts/report
- [x] 6.4 删除边界：**绝不删除 CaptureTake 本身、源视频、CaptureTrack**（测试断言这些资产在删除后存活）
- [x] 6.5 删除 Child：外部 API blocked，只能由 Parent cascade 删除
- [x] 6.6 单元测试：级联删除/取消各分支；`excluded_job_id` 共享资产保护逻辑对 child 生效

## 7. 双摄创建 API 与 MultiView Preflight

- [x] 7.1 扩展 `POST /api/analysis/jobs`：`analysisKind=multiview` 负载含 `capture_take_id` + 两路 `viewId / videoId / calibrationId / courtOrientation`；前端不得 create 两个 job 再调 fusion（业务编排不泄漏到浏览器）
- [x] 7.2 实现 preflight：`CaptureTake completed` → 双视频 available → 双 calibration available → 双 orientation declared → `sync_calibration.json` available → 两机位属 P0 axis-preserving 范围
- [x] 7.3 preflight 失败返回结构化原因；前端展示原因与操作（「重新检查同步」「改用 A 机位单摄分析」），不静默退化
- [x] 7.4 单元测试：preflight 各失败分支返回明确原因；缺 sync artifact ≠ `offset_ms=0`（沿用 P0 硬断言）

## 8. 接入 `MultiViewFusionRun` 并持久化 `fusionRunId`

- [x] 8.1 `fusion_ready` 时：`fusionRunId == null` → `MultiViewFusionRun.create()` → **先 save Parent.fusionRunId** → 再执行融合
- [x] 8.2 重启/重试幂等：`fusionRunId` 已存在 → 检查 fused artifact 完整且 schema 合法 → reuse；不完整 → 对同一个 Run 重试/重建（绝不在每次 retry 创建全新 Run）
- [x] 8.3 `MultiViewAnalysisExecutor` 消费 child 的 `player_render_trajectory` 产物构建 `MultiViewViewInput`（含 `analysis_job_id`），job-level fallback（orientation 未声明 / sync unavailable）时不生成 fused artifact
- [x] 8.4 单元测试：fusion 中途崩溃后重启复用同一 `fusionRunId`；job-level fallback 不生成 fused artifact

## 9. 修正 `select_trajectory_source()`

- [x] 9.1 `TrajectorySource` 扩展 `Literal["fused", "single_view", "unavailable"]`
- [x] 9.2 `select_trajectory_source(fused_available, single_view_available)`：fused → `"fused"`；仅单摄 → `"single_view"`；双路失败 → `"unavailable"`
- [x] 9.3 单元测试：`fused=false, single=false` 返回 `"unavailable"`（不再假装存在单视角轨迹）

## 10. MultiViewResultComposer：fused 重算位置类指标

- [x] 10.1 实现 Composer 第 1 步 Select/Recompute：用 fused trajectory + `metric_eligible` 重新计算 movement distance / speed / heatmap / zone stats / movement metrics（复用单摄 metrics 阶段同一套数学，输入换 fused）；**禁止复制 child 在 local frame 算好的位置指标**
- [x] 10.2 实现 Composer 第 2 步 Inherit：reference-view 的 pose / ball / action classification / overlay video / serve 等结果
- [x] 10.3 单元测试：fused 可用时位置指标来自 fused 而非 child；`predicted`/`unavailable` 样本不进指标（`metric_eligibility_policy` 生效）

## 11. Composer 归一化到 Parent namespace + fallback compose

- [x] 11.1 实现 Composer 第 3 步 Normalize：把 P0 fused artifacts + diagnostics **复制/改写 URL** 到 Parent artifact namespace（`/jobs/{parent_id}/artifacts/...`），生成 parent-owned `report.json` + artifact manifest
- [x] 11.2 **artifact manifest 作为 Parent 唯一产品出口**：parent report 内嵌 `artifacts` 清单（`playerTrajectory / fusionDiagnostics / referenceOverlay`，各带 `source` 与 `url`）；前端只消费该 manifest，**永不引用 `multiview/run/<run_id>/` 中间产物**
- [x] 11.3 fallback 时同样 compose Parent report：内容可继承 child，但所有权必须归 Parent（`job_id=parent`、artifact URL 指向 parent），并带 `analysis_source` provenance（`mode / source_job_id / source_view / reason`）
- [x] 11.4 单元测试：fallback 报告不含 child `job_id`/reportId/artifact URL；provenance 字段正确；产品层无任何引用指向 fusion run 目录；manifest 内 URL 全部解析到 Parent

## 12. 前端：双摄主 CTA、SetupPage、cameraAngle 修正

- [x] 12.1 双摄录制完成主按钮改为「双摄协同分析」→ `/capture/takes/:captureTakeId/analyze`；「仅分析 A/B 机位」降级为次级操作（工程调试入口）
- [x] 12.2 新增 `MultiViewAnalysisSetupPage`：素材检查（A/B 视频、双摄同步、融合支持）→ A 机位标定 → B 机位标定 → 确认；复用 `CourtCornerCalibrator`，一次完成两个 calibration；全部就绪才可启动
- [x] 12.3 CourtOrientation 产品化：MVP 由用户人工确认「A 机位位于球场 A 端/B 端底线」；不暴露 `identity/rotate_180` 等算法枚举；**摄像头安装角色自动推断列为后续 Change，本版不做**
- [x] 12.4 修复 `RecordingAnalyzePage` 的 `cameraAngle` 错误映射（用 `match_format` 查 `angleMap` 恒落 `unknown`）；清理该错误语义
- [x] 12.5 点击「开始双摄协同分析」只创建 1 个 Parent 任务，直接导航 `/analysis/<parentId>`；用户永不导航到 child

## 13. 任务列表 / 详情 / 结果页 Parent-only 改造

- [x] 13.1 任务列表只出现一张 Parent 卡片（「双摄协同分析」+ A/B/融合子状态）；child `visibility=internal` 默认不进入 `AnalysisTasksPage`，`include_internal=true` 才展示（诊断）
- [x] 13.2 录制卡片按 session 查询分析任务同样只返回 Parent；卡片展示「双摄协同分析」CTA 与状态
- [x] 13.3 任务详情页双摄任务展示聚合阶段（素材与同步检查 → A 机位视觉分析 → B 机位视觉分析 → 多视角融合 → 指标重算 → 报告）+ `viewRuns` 子进度；不铺 24 行单摄阶段
- [x] 13.4 结果页展示数据来源（哪些指标 fused、哪些取 reference view）与融合质量（`fused_diagnostics`：双视角共同观测 / 单视角补偿 / 预测补点 / 视角位置差异中位数 / 同步质量）
- [x] 13.5 降级提示明确展示：sync 不可用 / B 机位失败等横幅，不静默；失败原因（job-child-a failed / mvf not eligible）只放技术详情
