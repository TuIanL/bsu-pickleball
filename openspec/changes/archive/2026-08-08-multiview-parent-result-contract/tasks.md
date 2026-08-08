# Tasks: multiview-parent-result-contract

## 1. Parent result 落盘

- [x] 1.1 在 `backend/app/services/analysis_executor_dispatch.py` 的 `MultiViewAnalysisExecutor.execute` 中，compose 完成后显式 `publicize_pipeline_result` + `write_json(output_json_path(parent.id), result.model_dump(mode="json"))`
- [x] 1.2 验证：`GET /jobs/{parent_id}/result` 在后端重启后仍返回完整 pipeline result

## 2. Parent videoId 自含

- [x] 2.1 在 `backend/app/services/multiview_coordinator.py` 的 `create_multiview_job` 中，从 reference child 继承 `videoId`/`calibrationId` 写入 Parent
- [x] 2.2 在 `backend/app/services/mock_analysis.py` 新增 `_resolve_parent_video_source`，并在 `get_mock_job` 中对缺 `videoId` 的 Parent 虚拟解析（只读、不落盘）
- [x] 2.3 新增测试：创建时继承 videoId；读取时对历史 Parent 虚拟解析

## 3. Composer 产物契约

- [x] 3.1 用显式契约表 `_INHERITED_ARTIFACT_SPECS` 替代 `getattr(storage, f"{field}_json_path")` 推断，覆盖 22 项产物（含 getter 名不匹配的 `detections` / `analysis_overlay_video` / `serve_debug_overlay` / `player_render_trajectory`）
- [x] 3.2 继承时补齐 `*_url`（指向 Parent 命名空间）与 `*_status`/`*_detail`（从 reference child 落盘结果继承，新增 `_load_child_artifacts`）
- [x] 3.3 叠加视频不复制（`copy_file=False`），`analysis_overlay_video_url` 引用 child URL
- [x] 3.4 `build_pipeline_result` 补 `source_video_url` 与 `observed_player_count`；方法开头重新 `resolve_capture_job_root`（重启后路径正确）
- [x] 3.5 新增测试：composer 继承 url/status/detail、文件复制到 Parent 命名空间

## 4. 验证与回填

- [x] 4.1 后端 `pytest` 全部通过
- [x] 4.2 新增 `backend/scripts/backfill_parent_result.py`，用修复后 composer 为历史 Parent 回填 `result.json`
- [x] 4.3 对 job-5198c2f64d 执行回填，验证 8 个视觉层 URL/status 全部恢复、视频可播
