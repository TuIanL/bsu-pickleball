"""用修复后的 composer 重新生成历史 multiview Parent 的 result.json（回填）。

背景：旧 composer 只填 *_json_path、不填 *_url/*_status，且 Parent result 从不落盘，
导致后端重启后 vision 页 8 个视觉层全部"不可用"。本脚本读取已有的 fused 产物 +
reference child 的 result，用当前 composer.build_pipeline_result 重新组装并落盘。

仅新增/覆写 Parent 的 result.json，不重新分析视频、不删任何东西、不触碰录制资产。
用法：python scripts/backfill_parent_result.py job-5198c2f64d
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.multiview_result_composer import MultiViewResultComposer
from app.services.storage_service import StorageService


def backfill(parent_job_id: str) -> bool:
    from app.services import mock_analysis

    storage = StorageService()
    parent = mock_analysis.get_mock_job(parent_job_id)
    if parent is None:
        print(f"parent job {parent_job_id} not found")
        return False
    if parent.analysisKind != "multiview":
        print(f"job {parent_job_id} is not multiview, skip")
        return False
    if parent.referenceViewId is None or not parent.sourceJobs:
        print(f"parent {parent_job_id} has no reference view / source jobs, skip")
        return False

    capture_take_id = getattr(parent.metadata, "capture_take_id", None)
    storage.resolve_capture_job_root(parent_job_id, capture_take_id)

    # 读取已有的 fused 产物 + manifest（不重新融合）
    fused_path = storage.fused_trajectory_json_path(parent_job_id)
    diag_path = storage.fusion_diagnostics_json_path(parent_job_id)
    manifest_path = storage.fusion_manifest_json_path(parent_job_id)
    if not (fused_path.exists() and diag_path.exists()):
        print(f"fused artifacts missing for {parent_job_id}, skip")
        return False
    fused_artifact = storage.read_json(fused_path)
    diagnostics = storage.read_json(diag_path)
    manifest = storage.read_json(manifest_path) if manifest_path.exists() else {}

    ref_view = parent.referenceViewId
    ref = next((r for r in parent.sourceJobs if r.cameraSlot == ref_view), None)
    if ref is None:
        print(f"reference child for {parent_job_id} not found, skip")
        return False
    reference_child = mock_analysis.get_mock_job(ref.jobId)
    if reference_child is None:
        print(f"reference child {ref.jobId} not found, skip")
        return False

    analysis_source = manifest.get("analysis_source") or {
        "mode": "multiview_fused",
        "source_job_id": parent_job_id,
        "source_view": ref_view,
        "reason": "backfill",
    }
    fusion_performed = analysis_source.get("mode") == "multiview_fused"
    message = "双摄协同分析完成（多视角融合已执行）。" if fusion_performed else "未执行多视角融合（单视角降级）。"

    result = MultiViewResultComposer(storage).build_pipeline_result(
        job=parent,
        fused_artifact=fused_artifact,
        diagnostics=diagnostics,
        analysis_source=analysis_source,
        reference_child=reference_child,
        fusion_performed=fusion_performed,
        message=message,
    )
    # 与 executor 落盘逻辑一致：publicize + 写 result.json
    result = storage.publicize_pipeline_result(result)
    storage.write_json(storage.output_json_path(parent_job_id), result.model_dump(mode="json"))
    print(f"backfilled result.json for {parent_job_id}")
    print("  video_id:", result.video_id)
    print("  observed_player_count:", result.observed_player_count)
    print("  tracking_overlay_url:", result.artifacts.tracking_overlay_url)
    print("  tracking_overlay_status:", result.artifacts.tracking_overlay_status)
    print("  heatmaps_url:", result.artifacts.heatmaps_url)
    print("  position_visualizations_status:", result.artifacts.position_visualizations_status)
    print("  analysis_overlay_video_url:", result.artifacts.analysis_overlay_video_url)
    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "job-5198c2f64d"
    ok = backfill(target)
    sys.exit(0 if ok else 1)
