"""Same-source-frame, per-view 2D ball observations without 3D reconstruction."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

import cv2


def build_joint_ball_2d_artifact(
    *, job_id: str, reference_view_id: str, timing_overlay: Mapping[str, Any],
    video_paths: Mapping[str, Path], tracker_factory: Callable[[str], Any],
    publish_start_seconds: float = 0., capture_factory: Callable = cv2.VideoCapture,
    cancellation_check: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    views = timing_overlay.get("views") or {reference_view_id: timing_overlay}
    selected = {k: v for k, v in views.items() if k in video_paths}
    total = sum(len(v.get("frames") or []) for v in selected.values())
    done = 0
    output = {}
    for view_id, view in selected.items():
        capture = capture_factory(str(video_paths[view_id]))
        samples = []
        next_index = None
        try:
            if not capture.isOpened():
                raise RuntimeError(f"Ball source cannot be opened: {view_id}")
            tracker = tracker_factory(view_id)
            for row in view.get("frames") or []:
                if cancellation_check:
                    cancellation_check()
                source_index = row.get("source_frame_index", row["frame_index"])
                index = int(source_index if source_index is not None else row["frame_index"])
                timestamp = float(row["timestamp_seconds"])
                failed_grab = source_index is None
                if failed_grab:
                    pass
                elif next_index is not None and 0 <= index - next_index <= 16:
                    for _ in range(index - next_index):
                        if not capture.grab():
                            failed_grab = True
                            break
                else:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, image = (False, None) if failed_grab else capture.read()
                next_index = index + 1 if ok else None
                sample = {"frame_index": index, "timestamp_sec": timestamp,
                          "image_xy": None, "court_xy": None, "confidence": None,
                          "visible": False, "accepted": False, "interpolated": False,
                          "candidate_count": 0, "source": "missing_frame"}
                if ok:
                    observed = tracker.update(image, frame_index=index, timestamp_sec=timestamp)
                    accepted = bool(observed.accepted and observed.publication_eligible
                                    and observed.image_xy is not None and timestamp >= publish_start_seconds)
                    sample.update(
                        image_xy=list(observed.image_xy) if accepted else None,
                        confidence=observed.confidence, visible=observed.visible, accepted=accepted,
                        candidate_count=observed.candidate_count, source=observed.source,
                        reject_reason=observed.reject_reason,
                        quality_status=observed.quality_status,
                    )
                # Never turn predicted_position into a real detection or join it across a gap.
                samples.append(sample)
                done += 1
                if progress_callback:
                    progress_callback(done, total)
        finally:
            capture.release()
        accepted_count = sum(s["accepted"] for s in samples)
        output[view_id] = {
            "source": view.get("source") or timing_overlay.get("source"),
            "status": "available" if accepted_count else "no_detections",
            "detail": f"同机位二维球检测：{accepted_count}/{len(samples)}帧；没有预测点冒充检测",
            "samples": samples,
        }
    if reference_view_id not in output:
        raise ValueError("Reference ball view is missing")
    reference = output[reference_view_id]
    return {
        "schema_version": "ball_trajectory.v1", "job_id": job_id,
        "status": reference["status"], "detail": reference["detail"],
        "reference_view_id": reference_view_id, "views": output,
        "source": reference["source"], "samples": reference["samples"],
        "coordinate_system": {"image": "source_pixels", "court": "unavailable_2d_only"},
        "filtering": {"implementation": "existing_ball_tracker", "prediction_publication": False},
    }
