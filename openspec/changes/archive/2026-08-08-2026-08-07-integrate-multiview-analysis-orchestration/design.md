# Design: integrate-multiview-analysis-orchestration

## Context

P0（`add-multiview-player-trajectory-fusion`）已完成融合算法层，仓库现状已为 P0.5 留好入口：

1. **`MultiViewFusionRun` 已设计成等待两个 source AnalysisJob**：`wait_for_source_jobs(job_status, required="completed")`、`check_eligibility()` 即 job-level gate；产物目录 `analysis_dir/multiview/<run_id>` 不挂任何 job。
2. **`MultiViewViewInput` 已含 `analysis_job_id`**：`view_id / capture_track_id / video_id / analysis_job_id / calibration_id / court_orientation`。
3. **`select_trajectory_source()` 已规定 fused 优先**，`metric_eligibility_policy` 已实现 `dual_observed / single_view_fallback → metrics yes`。
4. **sync 权威路径已冻结**：`take_dir/timeline/sync_calibration.json`（schema `dual_camera_sync_calibration.v1`）。
5. **Worker 单任务锁**：`AnalysisWorkerRuntime._running_lock` 非阻塞拿锁，`run_one()` 一次只执行一个任务，`claim_next()` 只挑 `canonicalStatus == "queued"` —— Parent 若被 claim 后 while 等待 child，child 永远无法被领取，必然死锁。

同时存在三个必须在本 Change 冻结的缺陷：

- `RecordingAnalyzePage` 的 `cameraAngle` 用 `session.match_format`（`"singles"/"doubles"`）查 `angleMap`（键是 `baseline_high/sideline/elevated...`），几乎恒落 `"unknown"`。
- `select_trajectory_source()` 末尾 `return "single_view" if single_view_available else "single_view"`，三元是死的，双路失败时会错误声称存在单视角轨迹。
- 没有 Parent/Child 任务编排：两路 child 报告泄漏 job_id/URL 到产品层，删除/取消无级联语义。

## Goals / Non-Goals

**Goals:**
- 把一次双摄录制变成"点击一次 → 自动两路分析 → 自动融合 → 一个 Parent 任务 → 一套 Parent-owned 结果"的端到端链路。
- 纯工程接线：所有融合算法、现有单摄 Pipeline、现有 AnalysisJob 实体全部复用，不改算法。
- 一个 multiview Parent 拥有两个 dedicated internal child（不跨 Parent 复用），级联删除是所有权问题而非引用计数问题。
- Parent 不占 Worker 等待 child；重启/重试幂等（`fusionRunId` 持久化）。
- 后端 `visibility` 为主闸，产品层永远只见 Parent；fallback 也 compose Parent-owned report，child 不泄漏。
- 修正 `cameraAngle` 错误映射与 `select_trajectory_source()` 死三元。

**Non-Goals:**
- 不修改 `MultiViewFusionRun` / CourtOrientation / GlobalTrackFilter / PlayerPositionFusion 任何算法逻辑。
- 不实现 source-job 复用；不实现 secondary 裁剪为 perception-only（仅预留 `analysisScope`）。
- 不实现"最佳单视角"自动选择；不新建独立任务系统；不删除现有单摄分析入口。
- 不删除 CaptureTake / 源视频 / CaptureTrack（分析任务是消费者，不拥有录制资产）。

## Decisions

### 1. `orchestrationStatus` 独立维度，`canonicalStatus` 五态不变

**Decision**：不把 `waiting_sources` 塞进 `canonicalStatus`。`canonicalStatus` 保持 `queued / running / succeeded / failed / canceled`；新增独立字段 `orchestrationStatus: Literal["none","waiting_sources","fallback_ready","fusion_ready","fusing","composing","completed"]`。Parent 等待 child 时：`canonicalStatus=queued, orchestrationStatus=waiting_sources`。

**Rationale**：整个任务系统（取消、恢复、列表、进度）都围绕 `canonicalStatus` 五态建，塞入第七态会破坏所有既有分支。"业务状态"与"是否可 claim"是两个正交维度。取消 `waiting_sources` 的 Parent 只需 `canonicalStatus=canceled` + Coordinator 级联 cancel children，不需要给 canonical 状态体系加特殊状态。

### 2. `is_runnable(job)` 统一收口 claimability

**Decision**：`claim_next()` 不再直接写 `canonicalStatus == "queued"`，改为调用：

```python
def is_runnable(job) -> bool:
    if job.canonicalStatus != "queued":
        return False
    if job.analysisKind == "single_view":
        return True
    if job.analysisKind == "multiview":
        return job.orchestrationStatus in {"fusion_ready", "fallback_ready"}
    return False
```

**Rationale**：这是整个 Change 的基石——它保证 `waiting_sources` 的 Parent 天然不可 claim（`_running_lock` 死锁从根上不可能发生），也保证 `fusion_ready / fallback_ready` 的 Parent 一旦就绪即被现有 Worker 正常领取，无需改造 Worker 主循环。

### 3. Worker 通过 Executor Protocol 分发，不把 `_execute` 变胖

**Decision**：

```python
class AnalysisJobExecutor(Protocol):
    def execute(self, job, token, progress_callback) -> AnalysisPipelineResult: ...

executor_registry: dict[AnalysisKind, AnalysisJobExecutor]
# _execute 内：
executor = self.executor_registry.resolve(job.analysisKind)
result = executor.execute(job, token, progress_callback)
```

- `SingleViewAnalysisExecutor.execute` 主体 = 现有 `_execute` 里重建 `AnalysisJobCreate` + `pipeline.run()` 的代码，原样搬入。
- `MultiViewAnalysisExecutor.execute` = 读两路 child artifact → 构建/复用 `MultiViewFusionRun` → 执行融合 → Composer → 返回 `AnalysisPipelineResult`（completed + 自定义 stages）。

**Rationale**：`if analysisKind == "multiview"` 直接写死能跑，但 `segment / multimodal / IMU` 进来 Worker 会不断变胖。抽 Protocol + registry 只是把"选择跑什么"抽出来，不重构 Worker 主循环，侵入最小。

**第一版收缩范围**：不做 executor 插件框架——没有 plugin discovery、没有通用 factory、没有第三方扩展 API。`executor_registry` 就是一张恰好含两个执行体（SingleView / MultiView）的分发表；"Worker 不知道不同类型任务怎么跑" 是真实需求，"建立通用执行平台" 不是。

### 4. Child 恒 dedicated/owned，不跨 Parent 复用

**Decision**：一个 multiview Parent 拥有两个 dedicated internal child（`child.parentJobId = parent.id`、`child.visibility = "internal"`、`child.analysisScope = "full"`）。即使输入签名相同，也绝不把另一个 Parent 的 child 拿来复用。Parent 侧用**数组** `sourceJobs: [{cameraSlot, jobId}]` 记录所有权映射，而非 `childJob1 / childJob2` 双字段——三摄 / 训练辅助机位 / 球场侧机位可自然扩展。

**Rationale**：一旦允许 `Parent A ─┐ ├→ 同一 cam1 child / Parent B ─┘`，"删除 Parent A 能不能删 child？"立刻变成引用计数问题。dedicated/owned 让级联删除变成纯所有权清理：删 Parent → 删 owned child 分析产物 + fusion run 产物 + parent artifacts。将来为省算力做 source-job reuse 再单独设计引用关系。

### 5. 删除级联的资产边界

**Decision**：删除 Parent 时删除 `Parent analysis artifacts + Child A/B analysis artifacts + MultiViewFusionRun artifacts + parent report`；**绝不删除 CaptureTake 本身、源视频、CaptureTrack**。分析任务是消费者，不拥有录制资产。

**Rationale**：现有 `delete_analysis_job` 有共享 video/calibration 清理逻辑（`excluded_job_id` 防误删）。P0.5 引入新的共享关系（Parent 与 child 共享同一 take），必须显式把"分析产物"与"录制资产"的边界写死，否则删除 API 可能误删录制数据。

### 6. 事件驱动编排，`waiting_sources` 不可 claim

**Decision**：`MultiViewAnalysisCoordinator` 负责：创建 Parent + 两个 dedicated child；监听 child completion；把 Parent 从 `waiting_sources` 推进到 `fusion_ready / fallback_ready`。Parent 绝不持有"被 claim 后 while 等待 child"的逻辑。

**Rationale**：`AnalysisWorkerRuntime._running_lock` 一次只跑一个任务，Parent 占着锁等 child，child 排队永远等不到 Worker → 死锁。事件驱动下 Parent 在 `waiting_sources` 时不可 claim，child 被 Worker 正常执行，完成后再推进 Parent 到可 claim。

### 7. `fusionRunId` 先持久化再执行

**Decision**：Parent 达到 `fusion_ready` 时：若 `fusionRunId == null` → `MultiViewFusionRun.create()` → **先 save `Parent.fusionRunId`** → 再执行融合。重启后：`Parent.fusionRunId` 已存在 → 检查对应 fused artifact：完整且 schema 合法 → reuse；不完整 → 对同一个 Run 重试/重建。绝不在每次 retry 创建全新 Run。

**Rationale**：`MultiViewFusionRun.create()` 每次生成新的 `mvf_xxxx`。若"创建 Run → fusion 完成 → artifact 写完 → 进程崩溃 → Parent 未 mark completed"，重启后重新 create 会得到第二个 Run，两个 Run 相互孤立、产物分裂。先持久化 `fusionRunId` 使整个执行路径 restart-safe。

### 8. 启动对账两轮，与现有 zombie recovery 分离

**Decision**：应用启动后 Coordinator 扫描 `analysisKind=multiview AND canonicalStatus not terminal`：

```text
Parent = waiting_sources
│
├─ A completed + B completed           → fusion_ready
├─ A completed + B failed/canceled     → fallback_ready(A)
├─ A failed/canceled + B completed     → fallback_ready(B)
├─ A failed + B failed                 → Parent failed
└─ 至少一个 child 非终态               → 继续 waiting_sources（child 交给现有 zombie recovery）
```

第二轮：`Parent = fusion_ready / fallback_ready` 且无 worker 所有者 → 保持 `canonical queued` → 下一次 `claim_next` 正常领取。`Parent = processing` 但 Worker 死亡 → 复用现有 zombie job 机制。

**Rationale**：现有 `recover_zombie_jobs()` 修"Worker 执行状态"；Coordinator reconciliation 修"Parent/Child 依赖关系"。两者职责不同，不揉成一个方法，否则互相干扰。

### 9. 取消/删除规则冻结

**Decision**：

```text
取消 Parent
  waiting_sources : Parent → canceled；owned 非终态 child → cancel
  fusion_ready    : Parent → canceled（child 已 terminal，不动）
  running fusion  : Parent.cancelRequestedAt → MultiViewExecutor 检查 token → canceled
取消 Child        : 普通用户 API → 403 blocked「internal source job cannot be canceled directly」；Coordinator 内部允许
删除 Parent       : 非终态沿用现有 blocked（先取消）；terminal → 级联删除（见决策 5）
删除 Child        : 外部 API blocked；只能由 Parent cascade 删除
```

**Rationale**：child 是内部工程实体，用户永远不应直接操作。把 Child 外部操作保护写死，避免任务管理页出现"删了父任务、剩两个孤儿 child"的脏状态。

### 10. `visibility` 后端为主闸

**Decision**：`AnalysisJobSummary.visibility: Literal["public", "internal"] = "public"`。`GET /api/analysis/jobs` 默认只返回 `public`；`?include_internal=true` 才返回 child，且该参数仅用于开发/诊断界面。录制卡片按 session 查询分析任务时同样只返回 Parent。

**Rationale**：前端过滤是双保险，不能当主闸。后端过滤保证任何客户端（包括旧页面）默认都看不到 child。

### 11. MultiView Preflight 不静默退化

**Decision**：创建双摄任务前执行 preflight：`CaptureTake completed` → `cam_1/cam_2 video available` → `cam_1/cam_2 calibration available` → `cam_1/cam_2 orientation declared` → `sync_calibration.json available` → 两机位属 P0 axis-preserving 范围。不满足时创建请求返回结构化失败原因，前端提前展示原因与操作（重新检查同步 / 改用单摄），**绝不静默退化**。

**Rationale**：P0 已规定没有 orientation 或 sync authority 时 `MultiViewFusionRun` 不合法启动、进入 job-level fallback。前端提前把原因告诉用户，比"创建了任务然后悄悄降级"诚实得多，也和"永不静默退化"的产品语义一致。

### 12. CourtOrientation 产品化确认（端 A/B），不暴露算法枚举

**Decision**：前端不向用户展示 `identity / rotate_180 / mirror_x / mirror_y`。**MVP 由用户人工确认**每个机位位于哪一端：「A 机位位于球场 A 端底线 / B 端底线」。后端据用户选择 + `CaptureTrack + Calibration` 生成 `CourtOrientation`。摄像头安装角色自动推断（`cam_1 = End A / cam_2 = End B`）涉及新规则，**第一版不做，列为后续 Change**。同时清理 `RecordingAnalyzePage` 用 `match_format` 查 `angleMap` 的错误语义。

**Rationale**：`CourtOrientation` 是算法概念（矩形二面体群的四元素），不是产品概念。用户理解的是"相机在哪一端"。安装模板知道 `cam_1/cam_2` 的物理角色，应自动生成，减少人工错误（P0 风险第一条：orientation 声明错误 → 融合整体镜像）。

### 13. Composer 三步，fallback 也 compose Parent report

**Decision**：`MultiViewResultComposer` 三步：**(1) Select/Recompute**——用 fused trajectory + `metric_eligible` 重算 movement / speed / heatmap / zone stats，绝不复制 child 在 local frame 算好的位置指标；(2) **Inherit**——reference-view 的 pose / ball / action classification / overlay video；(3) **Normalize**——发布到 Parent namespace（parent-owned report.json + artifact manifest + `/jobs/parent/artifacts/...` URL），带 `analysis_source` provenance。fallback 时同样重新 compose Parent report（内容可继承，所有权必须归 Parent）。

**Rationale**：child report 内含 `job_id = child`、artifact URL 指向 child、`report_id = child-report-id`，child 又是 internal。若 fallback 直接 `parent.report = child.report`，internal child 就通过 URL 和 reportId 泄漏到产品层。"用户永远只知道 Parent" 必须由 Composer 在所有权层兑现，而非前端掩盖。

**artifact manifest 作为 Parent 唯一产品出口**：P0 的 `MultiViewFusionRun` 把 fused 产物写在 `multiview/run/<run_id>/`——这是**中间产物**。Composer 第 3 步发布时把 `fused_player_trajectory.v1` / `fused_diagnostics.json` 等**复制/改写 URL** 到 Parent artifact 命名空间（`/jobs/{parent}/artifacts/...`），并在 parent report 内嵌 `artifacts` 清单（`playerTrajectory` / `fusionDiagnostics` / `referenceOverlay`，各自带 `source` 与 `url`）作为唯一出口。前端只消费该 manifest，**永远不知道 fusion run 存在**。缺失此契约，就会出现"报告能看到、技术详情找不到 fused 产物"以及"前端 URL 直指 fusion run"的泄漏。

### 14. 确定性 fallback 选择，第一版不做"最佳单视角"

**Decision**：

```text
Cam1  Cam2  Sync   Parent 结果
✓     ✓     ✓      → 执行 Fusion → succeeded → source=fused
✓     ✓     ✕      → 不执行 Fusion → succeeded → source=reference-view 优先
                   （reference 缺关键 artifact 才 secondary）→ 展示「双摄同步不可用，已使用单摄」
✓     ✕     -      → succeeded → source=Cam1 → 展示「B 机位分析失败」
✕     ✓     -      → succeeded → source=Cam2 → 展示「A 机位分析失败」
✕     ✕     -      → Parent failed
```

**Rationale**：除非现在同时定义"最佳"的算法，否则写"最佳单视角"无法测试。第一版用确定规则：单路成功选成功那路；双路成功但 fusion 不可用优先 reference view。结果可预测、可测试。以后要按 coverage/confidence 自动选最佳，再做独立策略 Change。

### 15. `analysisScope` 只预留，不实现

**Decision**：`AnalysisScope = Literal["full", "perception"]`。P0.5：**Parent `analysisScope = None`（不适用，不填）**，cam_1/cam_2 child 恒 `full`。将来性能优化：reference child `full`、secondary child `perception`。创建协议现在就带该字段，将来纯数据变更。

**Rationale**：知道下一步是"secondary 裁剪成 perception-only"，现在就在创建协议预留字段，将来省一次契约变更。但 P0.5 明确不实现裁剪——两路完整跑现有 Pipeline 接线最稳、对原系统侵入最小；裁剪是优化，不该和产品闭环混在一起。

## Risks / Trade-offs

- **Parent 占 Worker 等 child → 死锁**。Mitigation：决策 2 `is_runnable()` + 决策 6 事件驱动；加单测断言 `waiting_sources` 时 `claim_next` 返回 None。
- **`fusionRunId` 未持久化 → 重启生成第二个 Run**。Mitigation：决策 7 先 save 再执行；重启后检查 fused artifact 完整性与 schema 再 reuse。
- **fallback 泄漏 child job_id/URL/reportId**。Mitigation：决策 13 Composer 强制 Parent-owned；单测断言 fallback 报告不含 child 标识。
- **删除 Parent 误删录制资产**。Mitigation：决策 5 边界写死；测试断言 CaptureTake / 源视频 / CaptureTrack 存活。
- **旧页面仍显示 child**。Mitigation：决策 10 后端 `visibility` 主闸。
- **`analysisKind` 缺省兼容**：历史 job 缺省按 `single_view`，`visibility` 缺省按 `public`，`orchestrationStatus` 缺省按 `none`；additive 迁移，无数据回写。
- **Composer 误复制 child local-frame 位置指标**。Mitigation：决策 13 明确 fused + `metric_eligible` 重算；测试断言 fused 可用时位置指标来自 fused。

## Migration Plan

1. **数据**：`AnalysisJobSummary` 新增字段全部可选/带默认（`analysisKind`/`visibility`/`orchestrationStatus`/`parentJobId`/`analysisScope`/`fusionRunId`/`viewRuns`），历史 job 读取兼容，无数据迁移。
2. **代码**：先抽 `AnalysisJobExecutor` Protocol + `SingleViewAnalysisExecutor`（纯搬移，回归保证现有单摄 job 行为不变）；再新增 `MultiViewAnalysisCoordinator` / `MultiViewAnalysisExecutor` / `MultiViewResultComposer` / preflight；最后前端改造。
3. **回滚**：删除 Coordinator/Executor/Composer 与 Parent 创建路径即恢复现状（两路 child 照常可被创建），无数据迁移成本。
4. **验证**：端到端验收——对已完成双摄 CaptureTake，用户完成两路标定、点击一次「双摄协同分析」，系统自动创建/执行/隐藏两路 Source Job，条件满足时调用 P0 Fusion，基于 fused trajectory 重算位置指标，始终以一个 Parent AnalysisJob 提供进度、报告、降级提示与结果。

## Open Questions

1. **Executor `execute()` 返回的 stage 结构**：`MultiViewAnalysisExecutor` 返回的 `AnalysisPipelineResult.stages` 需要表达"素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 报告"六个聚合阶段。现有 `STABLE_ANALYSIS_STAGE_IDS` 与 `merge_stage_progress` 按 `ORDERED_STAGES` 强约束，双摄聚合阶段需决定是扩展 stage id 集合还是复用现有 id + `viewRuns` 并列展示。倾向：复用现有 stage id 集合，额外暴露 `viewRuns` 子进度（不改 `merge_stage_progress` 的排序假设）。
2. **`fusion_ready → fusing` 的推进时机**：Parent 被 claim 后由 Executor 内部推进，还是 Coordinator 在 claim 前预置？倾向：claim 后由 Executor 推进（保持 claim 原子性，避免 claim 与状态推进的竞态）。
3. **preflight 的"机位属 P0 范围"判定**：以什么字段为准（`court_orientation` 声明 + 安装角色 + 标定质量）？第一版以"两路 orientation 均已声明 + sync 可用 + axis-preserving 标定"为充分条件，细粒度判定留给实现。
