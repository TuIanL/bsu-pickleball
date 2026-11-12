from __future__ import annotations

from dataclasses import dataclass, field
import json
from math import hypot, isclose, isfinite
import os
from pathlib import Path
from typing import Any, Iterable

from app.schemas.tracking import Detection
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import PersonDetector

from .contracts import validate_contract
from .preflight import PreflightReport, ProviderPreflightError, effective_configuration, run_preflight


@dataclass(frozen=True)
class FrameEvidence:
    frame_index: int
    timestamp_seconds: float
    detections: list[Detection] = field(default_factory=list)
    status: str = "observed"
    error_code: str | None = None


def build_candidate_result(
    request: dict[str, Any],
    frames: Iterable[FrameEvidence],
    *,
    provider_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic review candidates without reading labels or product state."""
    validate_contract("provider_request", request)
    configuration = effective_configuration(request["configuration"])
    tracker = MultiObjectTracker(
        iou_threshold=configuration["tracker_iou_threshold"],
        max_lost=configuration["tracker_max_lost"],
        algorithm=configuration["tracker_algorithm"],
    )
    frame_records: list[dict[str, Any]] = []
    track_observations: dict[int, list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []

    ordered_frames = sorted(frames, key=lambda item: item.frame_index)
    seen_frames: set[int] = set()
    for frame in ordered_frames:
        if not 0 <= frame.frame_index < request["video"]["frame_count"]:
            raise ValueError(f"source frame index out of range: {frame.frame_index}")
        if frame.frame_index in seen_frames:
            raise ValueError(f"duplicate source frame index: {frame.frame_index}")
        seen_frames.add(frame.frame_index)
        detections = sorted(
            frame.detections,
            key=lambda item: (*[round(value, 8) for value in item.bbox], -round(item.confidence, 8)),
        )
        tracks = tracker.update(detections) if frame.status == "observed" else tracker.update([])
        detection_records: list[dict[str, Any]] = []
        for sequence, track in enumerate(tracks, start=1):
            detection_id = f"f{frame.frame_index:06d}-d{sequence:03d}"
            bbox = [float(value) for value in track.bbox]
            record = {
                "detection_id": detection_id,
                "track_id": track.track_id,
                "bbox_source": bbox,
                "bbox_roi": bbox,
                "confidence": float(track.confidence),
                "observation_source": "detected",
            }
            detection_records.append(record)
            track_observations.setdefault(track.track_id, []).append(
                {
                    "frame_index": frame.frame_index,
                    "timestamp_seconds": frame.timestamp_seconds,
                    "bbox_source": bbox,
                    "confidence": float(track.confidence),
                    "detection_id": detection_id,
                }
            )
        frame_records.append(
            {
                "frame_index": frame.frame_index,
                "timestamp_seconds": frame.timestamp_seconds,
                "status": frame.status,
                "roi_transform": {
                    "version": "source-roi-affine.v1.0",
                    "offset_x": 0.0,
                    "offset_y": 0.0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                },
                "detections": detection_records,
                "error_code": frame.error_code,
            }
        )
        if frame.status == "error":
            errors.append(
                {
                    "scope": "frame",
                    "frame_index": frame.frame_index,
                    "code": frame.error_code or "frame_processing_error",
                    "message": "Frame processing failed; no person evidence was emitted.",
                }
            )

    tracklets = _build_tracklets(track_observations)
    groups = _merge_tracklets(
        tracklets,
        max_gap=configuration["candidate_merge_max_gap"],
        min_iou=configuration["candidate_merge_min_iou"],
    )
    candidates = _build_candidates(
        groups,
        frame_records=frame_records,
        frame_count=request["video"]["frame_count"],
        frame_width=request["video"]["width"],
        frame_height=request["video"]["height"],
    )
    calibration = _calibration_result(request["calibration"])
    result = {
        "schema_version": "pb.target-candidate-result.v1.0",
        "request_id": request["request_id"],
        "sample_id": request["sample_id"],
        "video_sha256": request["video"]["sha256"],
        "provider": provider_metadata,
        "calibration": calibration,
        "frames": frame_records,
        "tracklets": [_public_tracklet(item) for item in tracklets],
        "candidates": candidates,
        "errors": errors,
    }
    validate_contract("provider_result", result)
    return result


def run_video_provider(
    request: dict[str, Any],
    *,
    request_dir: Path,
    output_path: Path,
    detector: Any | None = None,
    platform_root: Path | None = None,
) -> dict[str, Any]:
    preflight = run_preflight(
        request,
        request_dir=request_dir,
        output_path=output_path,
        platform_root=platform_root,
    )
    frames = _detect_video(request, preflight, detector=detector)
    result = build_candidate_result(
        request,
        frames,
        provider_metadata=_provider_metadata(preflight),
    )
    _write_json_atomic(output_path, result)
    return result


def _detect_video(
    request: dict[str, Any], preflight: PreflightReport, *, detector: Any | None
) -> list[FrameEvidence]:
    import cv2

    detector = detector or PersonDetector(
        model_path=str(preflight.model_paths["person_detector"]),
        conf_threshold=request["configuration"]["detector_confidence"],
        device=request["configuration"].get("detector_device"),
    )
    capture = cv2.VideoCapture(str(preflight.video_path))
    output: list[FrameEvidence] = []
    frame_index = 0
    try:
        if not capture.isOpened():
            raise ProviderPreflightError(f"could not open video: {preflight.video_path}")
        declared = request["video"]
        width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if width != declared["width"] or height != declared["height"]:
            raise ProviderPreflightError(
                f"video dimensions mismatch: declared {declared['width']}x{declared['height']}, "
                f"decoded {width}x{height}"
            )
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not isfinite(fps) or fps <= 0:
            raise ProviderPreflightError(f"video frame rate unavailable or invalid: {fps}")
        if not isclose(fps, declared["fps"], rel_tol=0.001, abs_tol=0.01):
            raise ProviderPreflightError(
                f"video frame rate mismatch: declared {declared['fps']}, decoded {fps}"
            )
        while True:
            ok, image = capture.read()
            if not ok:
                break
            if frame_index >= declared["frame_count"]:
                raise ProviderPreflightError(
                    f"video frame count mismatch: declared {declared['frame_count']}, "
                    f"decoded at least {frame_index + 1}"
                )
            if image is None or image.shape[:2] != (declared["height"], declared["width"]):
                raise ProviderPreflightError(f"decoded frame {frame_index} dimensions mismatch")
            try:
                detections = detector.detect_frame(image, frame_index)
                output.append(FrameEvidence(frame_index, frame_index / fps, detections))
            except Exception as exc:
                output.append(
                    FrameEvidence(
                        frame_index,
                        frame_index / fps,
                        [],
                        status="error",
                        error_code=type(exc).__name__,
                    )
                )
            frame_index += 1
        if frame_index != declared["frame_count"]:
            raise ProviderPreflightError(
                f"video frame count mismatch: declared {declared['frame_count']}, decoded {frame_index}"
            )
    finally:
        capture.release()
    return output


def _build_tracklets(observations: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output = []
    for index, track_id in enumerate(sorted(observations), start=1):
        items = sorted(observations[track_id], key=lambda item: item["frame_index"])
        output.append(
            {
                "tracklet_id": f"tracklet_{index:03d}",
                "source_track_ids": [track_id],
                "first_frame": items[0]["frame_index"],
                "last_frame": items[-1]["frame_index"],
                "detection_ids": [item["detection_id"] for item in items],
                "identity_diagnostics": [],
                "observations": items,
            }
        )
    return output


def _merge_tracklets(tracklets: list[dict[str, Any]], *, max_gap: int, min_iou: float) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for tracklet in tracklets:
        best_group: list[dict[str, Any]] | None = None
        best_iou = -1.0
        for group in groups:
            previous = group[-1]
            gap = tracklet["first_frame"] - previous["last_frame"] - 1
            score = _iou(previous["observations"][-1]["bbox_source"], tracklet["observations"][0]["bbox_source"])
            if 0 <= gap <= max_gap and score >= min_iou and score > best_iou:
                best_group = group
                best_iou = score
        if best_group is None:
            groups.append([tracklet])
        else:
            best_group.append(tracklet)
            best_group.sort(key=lambda item: (item["first_frame"], item["tracklet_id"]))
    return groups


def _build_candidates(
    groups: list[list[dict[str, Any]]],
    *,
    frame_records: list[dict[str, Any]],
    frame_count: int,
    frame_width: int,
    frame_height: int,
) -> list[dict[str, Any]]:
    timestamps = {item["frame_index"]: item["timestamp_seconds"] for item in frame_records}
    fps = _infer_fps(frame_records)
    candidates: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        by_frame: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
        for tracklet in group:
            for observation in tracklet["observations"]:
                by_frame[observation["frame_index"]] = (tracklet, observation)
        observations = []
        for frame_index in range(frame_count):
            pair = by_frame.get(frame_index)
            if pair is None:
                observations.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": timestamps.get(frame_index, frame_index / fps),
                        "status": "missing",
                        "bbox_source": None,
                        "confidence": None,
                        "source_tracklet_id": None,
                        "source_track_id": None,
                    }
                )
                continue
            tracklet, observation = pair
            observations.append(
                {
                    "frame_index": frame_index,
                    "timestamp_seconds": observation["timestamp_seconds"],
                    "status": "detected",
                    "bbox_source": observation["bbox_source"],
                    "confidence": observation["confidence"],
                    "source_tracklet_id": tracklet["tracklet_id"],
                    "source_track_id": tracklet["source_track_ids"][0],
                }
            )
        evidence = _score_evidence(observations, frame_count, frame_width, frame_height)
        score = (
            0.35 * evidence["coverage"]
            + 0.25 * evidence["mean_confidence"]
            + 0.2 * evidence["continuity"]
            + 0.1 * min(1.0, evidence["motion"] * 10.0)
            + 0.1 * min(1.0, evidence["geometry"] * 4.0)
        )
        candidates.append(
            {
                "candidate_id": f"candidate_{index:03d}",
                "tracklet_ids": [item["tracklet_id"] for item in group],
                "source_track_ids": sorted({value for item in group for value in item["source_track_ids"]}),
                "rank": 0,
                "score": round(score, 8),
                "score_evidence": evidence,
                "observations": observations,
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates


def _score_evidence(observations: list[dict[str, Any]], frame_count: int, width: int, height: int) -> dict[str, Any]:
    present = [item for item in observations if item["status"] != "missing"]
    confidences = [item["confidence"] for item in present]
    boxes = [item["bbox_source"] for item in present]
    coverage = len(present) / frame_count if frame_count else 0.0
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    span = present[-1]["frame_index"] - present[0]["frame_index"] + 1 if present else frame_count
    continuity = len(present) / span if span else 0.0
    diagonal = hypot(width, height) or 1.0
    centers = [((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) for box in boxes]
    distances = [hypot(b[0] - a[0], b[1] - a[1]) / diagonal for a, b in zip(centers, centers[1:])]
    motion = sum(distances) / len(distances) if distances else 0.0
    image_area = float(width * height) or 1.0
    areas = [max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1]) / image_area for box in boxes]
    geometry = sum(areas) / len(areas) if areas else 0.0
    return {
        "coverage": round(coverage, 8),
        "mean_confidence": round(mean_confidence, 8),
        "motion": round(motion, 8),
        "continuity": round(continuity, 8),
        "geometry": round(geometry, 8),
        "pose_motion": None,
    }


def _calibration_result(calibration: dict[str, Any]) -> dict[str, Any]:
    valid = (
        calibration["requested_mode"] == "origin_calibration"
        and calibration.get("calibration_id")
        and calibration.get("calibration_sha256")
        and calibration.get("homography")
        and len(calibration["homography"]) == 9
    )
    if valid:
        return {
            "mode": "origin_calibration",
            "status": "accepted",
            "calibration_id": calibration["calibration_id"],
            "calibration_sha256": calibration["calibration_sha256"],
            "reason": None,
        }
    return {
        "mode": "fallback_image_space",
        "status": "fallback",
        "calibration_id": None,
        "calibration_sha256": None,
        "reason": "origin calibration missing, invalid, or explicitly disabled",
    }


def _public_tracklet(tracklet: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in tracklet.items() if key != "observations"}


def _provider_metadata(preflight: PreflightReport) -> dict[str, Any]:
    return {
        "contract_version": "pb.target-candidate-provider.v1.0",
        "platform_commit": preflight.platform_commit,
        "worktree_clean": preflight.worktree_clean,
        "configuration_sha256": preflight.configuration_sha256,
        "models": preflight.model_sha256,
        "runtime_versions": preflight.runtime_versions,
    }


def _infer_fps(frames: list[dict[str, Any]]) -> float:
    if len(frames) >= 2:
        elapsed = frames[1]["timestamp_seconds"] - frames[0]["timestamp_seconds"]
        if elapsed > 0:
            return 1.0 / elapsed
    return 1.0


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.incomplete")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _iou(a: list[float], b: list[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0
