# Proposal: multiview-parent-result-contract

## Why

multiview Parent 的 `AnalysisPipelineResult` 从不落盘到 `result.json`，且继承 reference child 产物时只填 `*_json_path`、从不填 `*_url`/`*_status`；加上 Parent 自身的 `videoId` 缺失。后果是：**后端一旦重启（内存 `RESULTS` 缓存清空）→ `GET /result` 读不到结果 → 前端拿不到视频源与产物 URL → 视频无法播放、vision 页 8 个视觉层全部显示"不可用"**。这正是本次会话实际踩到的线上故障。

## What Changes

- **executor 落盘 Parent result**：`MultiViewAnalysisExecutor.execute` 在 compose 完成后显式 `publicize_pipeline_result` + 把结果写入 `result.json`（与单摄 pipeline 的 `_write_result` 对齐），使 Parent 结果可跨重启读取。
- **Parent videoId 自含**：
  - 创建 Parent 时（`MultiViewAnalysisCoordinator.create_multiview_job`）从 reference child 继承 `videoId`/`calibrationId`；
  - `get_mock_job` 在 Parent 缺 `videoId` 时从 reference child **虚拟解析**（只读、不落盘），保证历史 job 也能确定视频源。
- **composer 产物契约补齐**：继承 reference child 产物时，除复制文件 + 填 `*_json_path` 外，同步补齐 `*_url`（指向 Parent 命名空间）与 `*_status`/`*_detail`（继承自 child 落盘结果）；修复 `detections` / `analysis_overlay_video` / `serve_debug_overlay` / `player_render_trajectory` 因 storage 访问器名不匹配而**从未被继承**的问题；GB 级叠加视频不再复制到 Parent 命名空间，改为引用 child 的 URL；顺带补 `source_video_url` 与 `observed_player_count`。

## Capabilities

### New Capabilities

<!-- 无新增能力 -->

### Modified Capabilities

- `multiview-analysis-orchestration`: Parent 创建时继承 reference child 的 `videoId`/`calibrationId`；`get_mock_job` 对缺 `videoId` 的 Parent 从 reference child 虚拟解析视频源。
- `analysis-job-executor-dispatch`: `MultiViewAnalysisExecutor` 完成 compose 后显式将 Parent `AnalysisPipelineResult` 落盘到 `result.json`（并 `publicize_pipeline_result`）。
- `multiview-analysis-result-composer`: 继承 reference child 产物时补齐 `*_url`/`*_status`/`*_detail` 契约；修复 getter 名不匹配导致未继承的产物；叠加视频不复制改引用 child URL；补 `source_video_url` / `observed_player_count`。

## Impact

- `backend/app/services/analysis_executor_dispatch.py`：`MultiViewAnalysisExecutor.execute` 落盘 result。
- `backend/app/services/multiview_coordinator.py`：`create_multiview_job` 继承 videoId/calibrationId。
- `backend/app/services/mock_analysis.py`：`get_mock_job` + `_resolve_parent_video_source` 虚拟解析。
- `backend/app/services/multiview_result_composer.py`：`_INHERITED_ARTIFACT_SPECS` 契约表 + `_inherit_reference_artifacts` 补齐 url/status/detail + `_load_child_artifacts`。
- `backend/tests/test_multiview_orchestration.py`：新增 composer 继承 / videoId 解析测试。
- `backend/scripts/backfill_parent_result.py`：用修复后 composer 回填历史 Parent result 的工具脚本。
