# Design: multiview-parent-result-contract

## Context

当前 multiview Parent 的结果链路存在三处断裂，叠加起来在「后端重启」后全部爆发：

1. **result 不落盘**：单摄 pipeline 内部 `_write_result` 写 `result.json`，但 `MultiViewAnalysisExecutor.execute` 直接返回 composer 结果，没人落盘 → 内存 `RESULTS` 缓存（`mock_analysis` 模块级）是唯一持有者，重启即丢。
2. **Parent videoId 缺失**：`create_multiview_job` 创建 Parent 时不带 `videoId`（Parent 是聚合体），前端靠 `pipelineResult.video_id ?? nextJob.videoId` 定视频源；result 丢了之后两个都拿不到。
3. **产物契约不完整**：composer `_inherit_reference_artifacts` 只 `setattr(artifacts, f"{field}_json_path", ...)`，不填 `*_url`/`*_status`/`*_detail`；且用 `getattr(storage, f"{field}_json_path")` 推断访问器，导致 `detections`（`detections_jsonl_path`）、`analysis_overlay_video`（`_video_path`）、`serve_debug_overlay`（`_video_path`）、`player_render_trajectory`（`_path`）四个产物 getter 名不匹配而**从未被继承**。前端 `shouldLoad*` 全依赖 `*_url` → 全层不可用。

约束：修复必须是**结构性**的（防复发），不能依赖「重跑分析」或「手工补数据」。

## Goals / Non-Goals

**Goals:**
- Parent 的 `AnalysisPipelineResult` 可跨重启读取（`result.json` 落盘）。
- 前端始终能确定 Parent 的视频源（创建时继承 + 读取时虚拟解析双保险）。
- Parent 的产物契约完整（`*_url` / `*_status` / `*_detail`），8 个视觉层可加载、状态正确。
- 历史 job（无 result.json、videoId=None）无需改数据即可恢复视频与视觉层。

**Non-Goals:**
- 不改动融合算法、不修 cam_1 检测漏人（`observed_player_count=3` 是另一问题）。
- 不改变录制资产、不影响删除语义（`recording-analysis-cleanup` 已单独归档）。

## Decisions

### D1: executor 显式落盘 Parent result

`MultiViewAnalysisExecutor.execute` 在 `composer.build_pipeline_result(...)` 之后追加：

```python
result = storage.publicize_pipeline_result(result)
storage.write_json(storage.output_json_path(parent.id), result.model_dump(mode="json"))
```

`publicize_pipeline_result` 把 capture 产物的绝对路径转成逻辑引用（`analysis/<job_id>/<rel>`），与单摄 pipeline 的 `_write_result` 行为一致。`output_json_path` 对 capture Parent 解析为 `take_dir/analysis/<parent_id>/result.json`。

**为什么放 executor 而非 worker 回调**：`_on_worker_completed` 只写内存 `RESULTS`；单摄 pipeline 自身落盘，multiview 没有"自身落盘"的载体，executor 是最贴近 compose 的位置，且幂等（重跑覆盖）。

### D2: Parent videoId 自含（创建时继承 + 读取时虚拟解析）

- **创建时**：`create_multiview_job` 记录每个 view 的 child，循环后取 `reference_child.videoId/calibrationId` 写入 Parent（`store.update(parent.id, videoId=..., calibrationId=...)`）。
- **读取时**：`get_mock_job` 对 `analysisKind == "multiview"` 且 `videoId` 为空的 job，调用 `_resolve_parent_video_source(job)`：按 `referenceViewId` 找 reference child，取其 `videoId` 做 `model_copy` 返回（**不落盘**，避免写放大）。

**为什么双保险**：创建时继承覆盖新任务；读取时虚拟解析覆盖历史任务（result 未落盘、字段为 None），且不依赖数据迁移。

### D3: composer 产物契约表 + 补齐 url/status/detail

用显式契约表替代 `getattr(storage, f"{field}_json_path")` 推断：

```python
_INHERITED_ARTIFACT_SPECS: dict[路径字段名, (storage访问器, 路由名, url字段, status字段|None, 是否复制)]
```

- 复制文件成功 → 填 `*_path` + `*_url`（`/api/analysis/jobs/{parent}/artifacts/{route}`）。
- `status`/`detail` 从 reference child 的落盘结果继承（`_load_child_artifacts` 读 child 的 `result.json`），child 结果缺失/损坏时静默跳过。
- **叠加视频不复制**（`copy_file=False`）：GB 级视频引用 child 的 URL，避免 Parent 命名空间磁盘翻倍。
- 重启后 `_capture_job_roots` 为空 → 方法开头重新 `resolve_capture_job_root(parent/child, capture_take_id)`，路径才能解析正确。

**为什么继承 status/detail 而非重新计算**：视觉层的可用性语义（available / no_detections / skipped / failed）由单摄阶段决定，Parent 是聚合，应如实继承而非臆测。

## Risks / Trade-offs

- **继承 child status 的时效性** → [Risk] 若 child 结果与文件不一致（文件在 result 之后变更）可能状态错报 → Mitigation: 文件复制以磁盘为准，status 仅作展示，前端实际仍按文件可读性兜底。
- **叠加视频引用 child** → [Risk] child 被独立删除时 Parent 的叠加视频 404 → Mitigation: child 仅经 Parent cascade 删除（既有不变式），同生共死。
- **`_load_child_artifacts` 读磁盘** → [Risk] 大结果 JSON 每次读取开销 → Mitigation: 仅 compose 时读一次，不在轮询路径。

## Migration Plan

- 无数据迁移。新分析自动获得正确 result.json + videoId + 产物契约。
- 历史 job：提供 `scripts/backfill_parent_result.py`，读取已有 fused 产物 + reference child result，用修复后 composer 重新生成 Parent result.json（纯新增文件，不重跑分析）。

## Open Questions

- 是否需要在 `_load_child_artifacts` 失败时回退读内存 `RESULTS`（同进程场景）？——本期从磁盘读已足够，内存命中与否不影响正确性。
