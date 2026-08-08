# integrate-multiview-analysis-orchestration

## Why

P0（`add-multiview-player-trajectory-fusion`）已经完成多视角球员轨迹融合算法层：`MultiViewFusionRun` 明确设计成"等待两个 source AnalysisJob 完成，再执行融合"，`MultiViewViewInput` 已携带 `analysis_job_id`，`select_trajectory_source()` 已规定 fused 可用时优先 fused。但 P0 产物目前只是一个"可以单独调用的融合引擎"，尚未进入用户可用的业务链路：

- 双摄录制完成后，用户仍要分别在录制卡片上点「分析 A 机位」「分析 B 机位」，创建两个无关联的单摄 AnalysisJob；
- 两个任务各自产出报告，任务列表出现两条卡片，不表达"这是同一次双摄录制"；
- `MultiViewFusionRun` 没有任何任务系统接入——没有"谁等待两路完成、谁触发融合、fused artifact 如何进入报告"的编排者；
- 报告仍然读 Cam1 单摄产物，`fused_player_trajectory.v1` 生成了却没有成为球员位置类数据的消费来源。

本 Change 是**纯工程接线 Change，不扩展任何融合算法**。目标是把一次双摄录制从"两个角度分别分析"升级为一次协同分析：

> 用户点击一次「双摄协同分析」→ 系统自动创建并执行两路单摄 Source Job → 条件满足时调用 P0 Fusion → 基于 fused trajectory 重算位置类指标 → 始终以一个 Parent AnalysisJob 向用户提供进度、报告、降级提示和结果。

完成它以后，"双摄协同分析"才从算法能力升级为平台能力。

## What Changes

### 1. AnalysisJob 契约扩展（Parent / Source 编排）

保留现有 `AnalysisJob` 单实体，不新建一套任务系统。新增字段：

```python
analysisKind: Literal["single_view", "multiview"]     # 普通上传恒 single_view；双摄为 multiview
visibility: Literal["public", "internal"] = "public"  # child 恒 internal
parentJobId: str | None                               # child → parent
analysisScope: Literal["full", "perception"] | None   # child 恒 full；Parent 不适用(None)；预留 perception
sourceJobs: list[{cameraSlot, jobId}]                 # Parent 的所有权映射（数组，可扩展三摄/训练机位）
orchestrationStatus: AnalysisOrchestrationStatus      # 独立编排维度，见第 2 条
fusionRunId: str | None                               # 执行融合前持久化，保证重启/重试幂等
```

`sourceJobs` 采用**数组**而非 `childJob1 / childJob2` 双字段，为三摄 / 训练辅助机位 / 球场侧机位自然扩展留位。

### 2. 编排状态独立维度 + `is_runnable()` 统一收口

`canonicalStatus` 保持 `queued / running / succeeded / failed / canceled` 五态不变（Parent 等待 child 从用户语义上仍属 queued，只是暂时不可执行）。新增独立维度：

```python
AnalysisOrchestrationStatus = Literal[
    "none",              # 普通 single_view
    "waiting_sources",   # Parent 等 child
    "fallback_ready",    # child 不完整，可单摄降级
    "fusion_ready",      # 两 child 完成，可 fusion
    "fusing",
    "composing",
    "completed",
]
```

`claim_next()` 不能再只写 `canonicalStatus == "queued"`，统一收口为：

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

这样"业务状态"与"能否被 Worker claim"不再混在一起，也自然解决 `waiting_sources` 阶段取消问题（Parent 置 `canceled`，Coordinator 级联取消 owned children）。

### 3. Worker 执行分发层（不把 Worker 变胖）

新增 `AnalysisJobExecutor` Protocol + registry，Worker `_execute()` 只做：

```python
executor = self.executor_registry.resolve(job.analysisKind)
result = executor.execute(job, token, progress_callback)
```

- `SingleViewAnalysisExecutor` → 现有 `AnalysisPipeline.run()`（原样封装）；
- `MultiViewAnalysisExecutor` → `MultiViewFusionRun` + `MultiViewResultComposer`。

以后 `segment / multimodal / IMU` 进入时只新增 Executor，不动 Worker 主循环。

### 4. MultiViewAnalysisCoordinator（事件驱动，禁止 Parent 占 Worker 等 child）

新增核心服务 `MultiViewAnalysisCoordinator`，负责 Parent Job ↔ Source Job A/B ↔ `MultiViewFusionRun` 的编排。**绝不把 Parent 设计成"被 claim 后 while 等待两个 child"**（`AnalysisWorkerRuntime._running_lock` 一次只跑一个任务，那样会死锁）。采用事件驱动：

```text
创建 Parent → orchestrationStatus = waiting_sources
创建 Cam1 / Cam2 Source Job（dedicated internal）
Worker 正常执行 Source Job
两路 completed → Coordinator 发现 → Parent → fusion_ready / fallback_ready
Worker claim Parent → MultiViewAnalysisExecutor 执行
```

**Child 为 dedicated/owned**：一个 multiview Parent MUST 拥有两个 dedicated internal child jobs（`child.parentJobId = parent.id`）。Child 不跨 Parent 复用（即使输入签名相同也不拿另一个 Parent 的 child），使级联删除语义变成所有权问题而非引用计数问题。

### 5. Parent/Child 状态聚合与启动对账

- Parent 摘要暴露 `viewRuns`（`cam_1 / cam_2` 各自的 `status / stage / progress`），前端只展示聚合状态，不铺 24 行单摄阶段。
- 应用启动后 Coordinator 对账扫描 `analysisKind = multiview AND canonicalStatus not terminal`：child 全完成 → `fusion_ready`；单路失败 → `fallback_ready`；双路失败 → Parent `failed`；至少一路非终态 → 继续 `waiting_sources`（child 交给现有 zombie recovery）。第二轮把 `fusion_ready / fallback_ready` 且无 worker 所有者的 Parent 保持 `canonical queued`，等待 `claim_next`。
- 职责分工：现有 recovery 修 Worker 执行状态；Coordinator reconciliation 修 Parent/Child 依赖关系，两者不揉成一个方法。

### 6. 取消 / 删除级联与 Child 外部保护

```text
取消 Parent: waiting_sources → Parent canceled + owned 非终态 child cancel
             fusion_ready   → Parent canceled（child 已 terminal，不动）
             running fusion → Parent.cancelRequestedAt → Executor 查 token → canceled
取消 Child: 外部 API → 403 blocked；Coordinator 内部允许
删除 Parent: 非终态沿用现有 blocked（先取消）；terminal → 删 Parent + owned child 分析产物 + fusion run 产物 + parent artifacts/report
删除 Child: 外部 API blocked，只能由 Parent cascade 删除
```

**分析任务只是消费者，不拥有录制资产**：删除 Parent 绝不删除 CaptureTake 本身、源视频或 CaptureTrack。

### 7. 双摄创建 API + MultiView Preflight

仍用统一 `POST /api/analysis/jobs`，增加 multiview 负载：一个 `capture_take_id` + 两路 `videoId / calibrationId / courtOrientation`。前端不得自己 create 两个 job 再调 fusion（业务编排不得泄漏到浏览器）。

分析创建前执行 preflight，检查：双视频可用、两路标定可用、两路 orientation 已声明、`sync_calibration.json` 可用、两个机位属于 P0 axis-preserving 范围。不满足时**不静默退化**，前端提前展示原因与操作（如「重新检查同步」「改用 A 机位单摄分析」）。

### 8. `select_trajectory_source()` 语义修正

现有实现：

```python
return "single_view" if single_view_available else "single_view"   # 三元是死的
```

Composer 真正消费后，双路失败时会错误声称存在单视角轨迹。扩为：

```python
TrajectorySource = Literal["fused", "single_view", "unavailable"]
def select_trajectory_source(fused_available, single_view_available):
    if fused_available: return "fused"
    if single_view_available: return "single_view"
    return "unavailable"
```

### 9. MultiViewResultComposer（三步，不模糊地"合并结果"）

```text
MultiViewResultComposer
│
├── 1. Select / Recompute    fused trajectory + metric_eligible
│                            → 重算 distance / speed / heatmap / zone stats / movement metrics
│                            （绝不复制 child 在 local frame 里算好的位置指标）
├── 2. Inherit               reference-view 的 pose / ball / action classification / overlay video
└── 3. Normalize             发布到 Parent namespace：parent-owned report.json + artifact manifest
                            + artifact URL（/jobs/parent/artifacts/...）+ provenance
```

**artifact manifest 是 Parent 的唯一产品出口**。P0 的 `MultiViewFusionRun` 把 fused 产物写在 `multiview/run/<run_id>/`（中间产物）；Composer 发布时把 `fused_player_trajectory.v1` / `fused_diagnostics.json` 等**复制/改写 URL 到 Parent artifact 命名空间**，并在 parent report 内嵌 `artifacts` 清单作为唯一出口：

```json
{
  "artifacts": {
    "playerTrajectory": {
      "source": "fused",
      "url": "/jobs/{parent}/artifacts/fused_player_trajectory.json"
    },
    "fusionDiagnostics": {
      "url": "/jobs/{parent}/artifacts/fusion_diagnostics.json"
    },
    "referenceOverlay": {
      "source": "cam_1"
    }
  }
}
```

原则：`multiview/run/` 是中间产物，`parent/artifacts/` 是产品出口；**前端只消费 Parent 命名空间，永远不知道 fusion run 存在**。

fallback 时不能 `parent.report = child.report`（child report 内含 `job_id = child`、artifact URL 指向 child、child 是 internal），必须由 Composer 重新 compose Parent report，同时保留 provenance：

```json
{
  "analysis_source": {
    "mode": "single_view_fallback",
    "source_job_id": "job-child-a",
    "source_view": "cam_1",
    "reason": "cam_2_failed"
  }
}
```

### 10. 前端：双摄主 CTA、SetupPage、Parent-only 展示

- 双摄录制完成后的主按钮从「分析 A 机位 / 分析 B 机位」改为「**双摄协同分析**」，A/B 单摄入口退到次级操作；修复现有 `cameraAngle` 错误映射（`RecordingAnalyzePage` 用 `session.match_format` 查角度表几乎恒落 `unknown`）。
- 新增 `MultiViewAnalysisSetupPage`（路由 `/capture/takes/:captureTakeId/analyze`），四阶段：素材检查 → A 机位标定 → B 机位标定 → 确认；复用 `CourtCornerCalibrator`，一次完成两个 calibration。CourtOrientation 不对用户暴露 `identity/rotate_180` 等算法概念，只显示「A 机位位于球场 A 端 / B 端底线」，或由摄像头安装角色自动确定。
- 任务列表、任务详情、结果页只公开一个 Parent Job：展示 A/B 子进度、fusion/fallback 状态、数据来源（哪些指标融合了、哪些仍取 reference view）、融合质量（`fused_diagnostics`）。

## Non-Goals

```text
- 不扩展/修改任何融合算法（P0 的 CourtOrientation / GlobalTrackFilter / PlayerPositionFusion 等一律不动）。
- 不做 source-job 复用/引用计数（Child 恒 dedicated/owned；将来省算力再单独设计引用关系）。
- 不把两路裁剪成 perception-only（P0.5 两路完整跑现有 Pipeline；`analysisScope` 仅预留，不实现）。
- 不实现"最佳单视角"自动选择（第一版用确定性规则：单路成功选成功那路；双路成功但 sync 不可用优先 reference view）。
- 不把 Executor 做成插件框架（第一版 registry 只含 SingleView / MultiView 两个执行体，不做工厂/插件发现/第三方扩展 API）。
- 不做摄像头安装角色自动推断（第一版由用户确认「A/B 机位位于球场哪一端」；自动推断涉及新规则，后续单独 Change）。
- 不新建一套独立于 AnalysisJob 的任务系统（任务列表/取消/删除/报告/恢复全部复用现有 AnalysisJob）。
- 不把业务编排泄漏到前端（前端不 create 两个 job 再调 fusion）。
- 不删除现有单摄分析入口（RecordingAnalyzePage 降级为工程调试入口，仍可用）。
- 不删除 CaptureTake / 源视频 / CaptureTrack（分析任务是消费者，不拥有录制资产）。
```

## Capabilities

### New Capabilities

- `multiview-analysis-orchestration`: Parent/Source Job 编排（`analysisKind` / `orchestrationStatus` / `parentJobId` / `visibility` / `sourceJobs` 数组 / `is_runnable()`）、`MultiViewAnalysisCoordinator`、dedicated/owned child、启动对账、取消/删除级联与 Child 外部保护、MultiView preflight。
- `analysis-job-executor-dispatch`: `AnalysisJobExecutor` 入口 + registry（第一版仅 `SingleViewAnalysisExecutor` / `MultiViewAnalysisExecutor` 两个执行体，不做插件框架），`SingleViewAnalysisExecutor` 封装现有 Pipeline，`MultiViewAnalysisExecutor` 执行 FusionRun + Composer。
- `multiview-analysis-result-composer`: 三步 Composer（fused 重算位置指标 / 继承 reference-view 结果 / 归一化到 Parent namespace），artifact manifest 作为 Parent 唯一产品出口，fallback 时同样 compose Parent-owned report，带 `analysis_source` provenance。
- `multiview-analysis-setup-page`: `MultiViewAnalysisSetupPage`（素材检查 → 双标定 → 确认），双摄主 CTA，CourtOrientation 产品化确认（MVP 用户确认端 A/B，自动推断后续 Change），修复 `cameraAngle` 映射。

### Modified Capabilities

- `analysis-job-orchestration`: `AnalysisJobSummary` 新增编排字段与 `is_runnable()` 收口；`_execute()` 走 executor dispatch。
- `analysis-task-management`: `GET /api/analysis/jobs` 默认只返回 `public`，`?include_internal=true` 仅用于诊断；录制卡片与任务列表只展示 Parent。
- `recording-analysis-bridge`: 主 CTA 改为「双摄协同分析」，单摄入口降级；`cameraAngle` 语义修正。
- `analysis-details-page`: Parent 双摄任务展示聚合子进度、fusion/fallback 状态、数据来源与融合质量。
- `multiview-analysis-input-contract`: 新增 MultiView preflight 校验入口与不满足时的显式失败原因。
- `multiview-player-trajectory-fusion`: `select_trajectory_source()` 返回值扩展 `unavailable`。

## Impact

- **后端**：`job_orchestration.py`（`is_runnable` / executor dispatch / cancel-delete 级联）、`schemas/analysis.py`（新字段）、新增 `MultiViewAnalysisCoordinator`、`SingleViewAnalysisExecutor`、`MultiViewAnalysisExecutor`、`MultiViewResultComposer`、preflight 模块；`consumers.py` 修 `select_trajectory_source()`。
- **数据**：`AnalysisJobSummary` 新增字段均为可选/带默认，历史 job 兼容；Child job 落盘为 internal，默认不列表。
- **前端**：新增 `MultiViewAnalysisSetupPage`；`RecordingAnalyzePage` 降级；任务列表/详情/结果页 Parent-only 改造；录制卡片主 CTA 变更。

## Migration / Compatibility

additive 迁移。所有新增字段带默认值，历史 `AnalysisJobSummary` 读取兼容（`analysisKind` 缺省按 `single_view`、`visibility` 缺省按 `public`、`orchestrationStatus` 缺省按 `none` 处理）。`AnalysisPipeline` 及其产物契约完全不动。现有单摄 job 全链路行为不变。Child job 采用 `visibility = internal` 从任务列表隐藏，无需数据迁移；`include_internal=true` 为诊断保留后门。

## Recommended Architecture

```text
                      CaptureTake
                  CT_xxxxxxxxxxxxx
                         │
            用户点击「双摄协同分析」
                         │
                         ▼
               Parent AnalysisJob
                job-mv-xxxxxxxx
         【唯一用户可见任务】
     analysisKind=multiview · orchestrationStatus 流转
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       Source AnalysisJob      Source AnalysisJob
          cam_1                   cam_2
   visibility=internal         visibility=internal
   parentJobId=parent          parentJobId=parent
   analysisScope=full          analysisScope=full
        【dedicated/owned】
              │                     │
       现有 AnalysisPipeline   现有 AnalysisPipeline
              │                     │
              ▼                     ▼
     player_render_trajectory player_render_trajectory
              │                     │
              └──────────┬──────────┘
                         ▼
               MultiViewFusionRun          ← P0 算法层，P0.5 不扩展
         fusionRunId 已在 Parent 持久化
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
     fused_player_trajectory   fused_diagnostics
                         │
                         ▼
          MultiViewResultComposer
         ┌────────────────────────────────┐
         │ 1. fused + metric_eligible     │
         │    → 重算 movement/heatmap/speed│
         │ 2. 继承 reference-view         │
         │    → pose/ball/action/overlay  │
         │ 3. 归一化到 Parent namespace    │
         │    → parent report + artifacts │
         └────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        fused 位置类指标      reference-view
        movement/heatmap      pose/ball/video
              │                     │
              └────────┬────────────┘
                       ▼
              Parent-owned 最终分析报告
```

Worker 侧：

```text
AnalysisWorkerRuntime._execute(job)
        │
        ▼
executor_registry.resolve(job.analysisKind)
        │                        │
   single_view               multiview
        ▼                        ▼
SingleViewAnalysisExecutor  MultiViewAnalysisExecutor
        │                        │
  AnalysisPipeline.run()   MultiViewFusionRun + Composer
```

## Risks

- **Parent 占 Worker 等待 child = 死锁**（`_running_lock` 单任务）。Mitigation：设计冻结事件驱动，`waiting_sources` 不可 claim，`is_runnable()` 是唯一入口；加单测断言 Parent 在 `waiting_sources` 时 `claim_next` 返回 None。
- **`fusionRunId` 未持久化 → 重启生成第二个 Run**。Mitigation：执行前先 save `Parent.fusionRunId`，重启后复用同一 Run（artifact 完整 → reuse；不完整 → 同一 Run 重试/重建）。
- **fallback 时 child 通过 URL / reportId 泄漏到产品层**。Mitigation：Composer 强制 Parent-owned namespace + provenance，child 恒 internal；单测断言 fallback 报告不含 child job_id/URL。
- **前端触达 fusion run 中间产物（`multiview/run/<id>/`）**。Mitigation：artifact manifest 作为唯一出口，Composer 把 fused 产物复制/改写 URL 到 Parent 命名空间；单测断言产品层无任何引用指向 fusion run 目录。
- **删除 Parent 误删录制资产**。Mitigation：级联删除只删分析产物；测试断言 CaptureTake / 源视频 / CaptureTrack 存活。
- **前端仍旧展示 child**。Mitigation：后端 `visibility` 为主闸，`include_internal=true` 仅诊断；录制卡片按 session 查询同样只返回 Parent。
- **fused 指标污染/复制 child local-frame 指标**。Mitigation：Composer 必须用 fused + `metric_eligible` 重算，禁止复制 child 位置指标；加"fused 可用时位置指标来自 fused"的断言。
