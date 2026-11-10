"""Publish optional joint pose and basic 2D ball layers after identity is authoritative."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import time

from app.schemas.pipeline import PipelineStageResult


def publish_joint_basic_visuals(
    *, job, result, storage, settings, videos, reference_view_id,
    cancellation_token=None, progress_callback=None,
):
    explicit_pose = getattr(job, "enablePoseInference", None)
    pose_enabled = bool(getattr(settings, "enable_pose_inference", False) if explicit_pose is None else explicit_pose)
    ball_2d_enabled = bool(getattr(settings, "enable_ball_detection", False)
                           and not getattr(settings, "enable_ball_reconstruction", True))
    if not pose_enabled and not ball_2d_enabled:
        return
    visual_started = datetime.now(UTC)
    if progress_callback:
        progress_callback(PipelineStageResult(
            id="multiview-metrics", label="运动指标重算", status="done", progress=100,
            detail="已基于最终球员轨迹生成运动指标",
        ))
        progress_callback(PipelineStageResult(
            id="multiview-visualization", label="基础识别叠加", status="active", progress=0,
            detail="读取正式人体叠加，准备骨架与二维球推理", started_at=visual_started,
        ))
    try:
        overlay = storage.read_json(storage.fused_player_overlay_json_path(job.id))
    except FileNotFoundError as exc:
        detail = getattr(result.artifacts, "fused_player_overlay_detail", None)
        raise RuntimeError(f"基础识别缺少正式人体叠加产物：{detail or '人体叠加未生成'}") from exc
    paths = {key: Path(video.path) for key, video in videos.items()}
    ids = {key: video.id for key, video in videos.items()}
    phases = int(pose_enabled) + int(ball_2d_enabled)
    phase_index = 0
    phase_results = []

    def cancel():
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

    def run_stage(stage_id, label, builder, path, artifact_prefix, route):
        nonlocal phase_index
        started = datetime.now(UTC)
        last_report = float("-inf")

        def progress(done, total):
            nonlocal last_report
            now = time.monotonic()
            if progress_callback and (done == total or now - last_report >= .5):
                last_report = now
                progress_callback(PipelineStageResult(
                    id="multiview-visualization", label="基础识别叠加", status="active", started_at=visual_started,
                    detail=f"{label} {done}/{total}", public_message=f"{label} {done}/{total}",
                    progress=round((phase_index + done / max(1, total)) / phases * 100),
                ))
        cancel()
        # Requested inference failures propagate: a successful tracking pass is not successful pose.
        artifact = builder(cancel, progress)
        storage.write_json_atomic(path, artifact)
        if artifact_prefix == "pose_overlay":
            from app.services.overlay_playback import publish_overlay_playback
            publish_overlay_playback(path, artifact, artifact_name=route)
        setattr(result.artifacts, f"{artifact_prefix}_json_path", str(path))
        setattr(result.artifacts, f"{artifact_prefix}_url", f"/api/analysis/jobs/{job.id}/artifacts/{route}")
        setattr(result.artifacts, f"{artifact_prefix}_status", artifact["status"])
        setattr(result.artifacts, f"{artifact_prefix}_detail", artifact["detail"])
        finished = datetime.now(UTC)
        phase_results.append({"id": stage_id, "status": artifact["status"],
                              "detail": artifact["detail"],
                              "duration_ms": int((finished - started).total_seconds() * 1000)})
        phase_index += 1

    if pose_enabled:
        from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter
        from app.services.joint_pose_artifacts import build_joint_pose_artifact
        estimator = RTMPose26Adapter(
            config_path=settings.rtmpose_config_path, checkpoint_path=settings.rtmpose_checkpoint_path,
            device=settings.rtmpose_device, conf_threshold=settings.pose_confidence,
            conf_exit_threshold=settings.pose_confidence_exit, keypoint_schema=settings.pose_keypoint_schema,
        )
        run_stage(
            "multiview-pose", "双摄球员骨架", lambda cancel, progress: build_joint_pose_artifact(
                job_id=job.id, reference_view_id=reference_view_id, fused_overlay=overlay,
                video_paths=paths, video_ids=ids, estimator=estimator,
                cancellation_check=cancel, progress_callback=progress,
            ), storage.pose_overlay_json_path(job.id), "pose_overlay", "pose-overlay",
        )
    if ball_2d_enabled:
        from app.services.joint_ball_2d_artifacts import build_joint_ball_2d_artifact
        from app.vision.detectors.ball_adapter import YoloBallDetectorAdapter
        from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig
        detector = YoloBallDetectorAdapter(
            model_path=settings.ball_model_path, device=settings.detector_device, image_size=1280,
        )
        config = BallTrackerConfig(
            effective_fps=float(job.sourceFps or 60) / max(1, int(job.frameStride or 1)),
            frame_stride=max(1, int(job.frameStride or 1)),
        )
        run_stage(
            "multiview-ball-2d", "双摄二维球检测", lambda cancel, progress: build_joint_ball_2d_artifact(
                job_id=job.id, reference_view_id=reference_view_id, timing_overlay=overlay,
                video_paths=paths, tracker_factory=lambda _: BallTracker(detector=detector, config=config),
                publish_start_seconds=float(job.clipStartMs or 0) / 1000,
                cancellation_check=cancel, progress_callback=progress,
            ), storage.ball_trajectory_json_path(job.id), "ball_trajectory", "ball-trajectory",
        )
    finished = datetime.now(UTC)
    stage = PipelineStageResult(
        id="multiview-visualization", label="基础识别叠加",
        status="done" if all(p["status"] == "available" for p in phase_results) else "unavailable",
        detail="；".join(p["detail"] for p in phase_results), progress=100,
        started_at=visual_started, finished_at=finished,
        duration_ms=int((finished - visual_started).total_seconds() * 1000),
        counters={p["id"]: p for p in phase_results},
    )
    if any(s.id == stage.id for s in result.stages):
        result.stages = [stage if s.id == stage.id else s for s in result.stages]
    else:
        result.stages.append(stage)
    if progress_callback:
        progress_callback(stage)
