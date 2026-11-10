"""Pose inference on authoritative, same-view observed player boxes.

This post-pass does not change the tracking result or infer identity from pose.
Projected/predicted boxes never become pose evidence.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from pathlib import Path
from typing import Any, Callable, Mapping

import cv2

from app.schemas.pose import PoseOverlayArtifact, PoseOverlayFrame, default_skeleton_edges
from app.schemas.tracking import FrameDetection, SourceFrameSize


def build_joint_pose_artifact(
    *,
    job_id: str,
    reference_view_id: str,
    fused_overlay: Mapping[str, Any],
    video_paths: Mapping[str, Path],
    video_ids: Mapping[str, str],
    estimator: Any,
    sample_stride: int = 2,
    capture_factory: Callable = cv2.VideoCapture,
    cancellation_check: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    views = fused_overlay.get("views") or {reference_view_id: fused_overlay}
    sampled = {
        view_id: list(view.get("frames") or [])[::max(1, sample_stride)]
        for view_id, view in views.items() if view_id in video_paths
    }
    total = sum(map(len, sampled.values()))
    done = 0
    output_views = {}
    counters: Counter = Counter()
    for view_id, rows in sampled.items():
        view = views[view_id]
        source = SourceFrameSize.model_validate(view.get("source") or fused_overlay["source"])
        capture = capture_factory(str(video_paths[view_id]))
        frames = []
        next_index = None
        try:
            if not capture.isOpened():
                raise RuntimeError(f"Pose source cannot be opened: {view_id}")
            for row in rows:
                if cancellation_check:
                    cancellation_check()
                source_index = row.get("source_frame_index", row["frame_index"])
                index = int(source_index if source_index is not None else row["frame_index"])
                timestamp = float(row["timestamp_seconds"])
                players = [p for p in row.get("players", [])
                           if p.get("player_id") in {"Player_1", "Player_2", "Player_3", "Player_4"}
                           and p.get("evidence_type") in {"base_observed", "guided_observed", "refined_observed"}]
                counts = Counter(p["player_id"] for p in players)
                players = [p for p in players if counts[p["player_id"]] == 1]
                if source_index is None:
                    counters["source_frame_missing"] += 1
                    players = []
                counters["duplicate_identity_rejected"] += sum(n for n in counts.values() if n > 1)
                result = PoseOverlayFrame(frame_index=index, timestamp_seconds=timestamp)
                if players:
                    failed_grab = False
                    if next_index is not None and 0 <= index - next_index <= 16:
                        for _ in range(index - next_index):
                            if not capture.grab():
                                next_index = None
                                failed_grab = True
                                break
                    else:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ok, image = (False, None) if failed_grab else capture.read()
                    next_index = index + 1 if ok else None
                    if ok:
                        height, width = image.shape[:2]
                        detections = []
                        identity_by_track = {}
                        for player in players:
                            bbox = player.get("bbox")
                            if not isinstance(bbox, list) or len(bbox) != 4:
                                continue
                            x1, y1, x2, y2 = map(float, bbox)
                            if not all(map(isfinite, (x1, y1, x2, y2))):
                                continue
                            bbox = [max(0., x1), max(0., y1), min(float(width), x2), min(float(height), y2)]
                            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                                continue
                            pid = player["player_id"]
                            track = f"{view_id}:{pid}"
                            identity_by_track[track] = pid
                            detections.append(FrameDetection(
                                frame_index=index, timestamp_seconds=timestamp,
                                bbox=bbox, confidence=float(player["confidence"] if player.get("confidence") is not None else 1.),
                                track_id=track, player_id=pid,
                                source_width=width, source_height=height,
                            ))
                        inferred = estimator.estimate_frame(image, detections, index, timestamp)
                        # Hysteresis is view-scoped inside the estimator; output identity is canonical P.
                        result = inferred.model_copy(update={"subjects": [
                            subject.model_copy(update={"track_id": identity_by_track[subject.track_id]})
                            for subject in inferred.subjects if subject.track_id in identity_by_track
                        ]})
                        counters["subjects"] += len(result.subjects)
                    else:
                        counters["decode_missing"] += 1
                # Empty frames are evidence of a gap, not permission to hold an old skeleton.
                frames.append(result)
                done += 1
                if progress_callback:
                    progress_callback(done, total)
        finally:
            capture.release()
        available = any(f.subjects for f in frames)
        output_views[view_id] = {
            "video_id": video_ids.get(view_id), "source": source.model_dump(mode="json"),
            "status": "available" if available else "no_poses",
            "frames": [f.model_dump(mode="json") for f in frames],
        }
    reference = output_views.get(reference_view_id)
    if reference is None:
        raise ValueError("Reference pose view is missing")
    available = counters["subjects"] > 0
    artifact = PoseOverlayArtifact(
        job_id=job_id, video_id=video_ids.get(reference_view_id),
        status="available" if available else "no_poses",
        detail=f"双摄同帧真实球员框姿态：{counters['subjects']}个人体样本；预测框不参与推理",
        source=SourceFrameSize.model_validate(reference["source"]),
        skeleton_edges=default_skeleton_edges(),
        frames=[PoseOverlayFrame.model_validate(f) for f in reference["frames"]],
        timing_provenance={"source": "joint_fused_player_overlay", "reference_view_id": reference_view_id,
                           "frame_index": "per-view source frame", "timestamp": "canonical seconds",
                           "sample_stride": max(1, sample_stride), "counters": dict(counters)},
    ).model_dump(mode="json")
    artifact.update(reference_view_id=reference_view_id, views=output_views)
    return artifact
