#!/usr/bin/env python3
"""Remote-only extraction of aligned pose, ball, court-line, and quality features."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np
import torch
from rtmlib import RTMPose
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def rounded(values: Any, digits: int = 4) -> Any:
    return np.asarray(values).round(digits).tolist()


@dataclass
class Track:
    track_id: int
    center: np.ndarray
    last_sample: int


class CenterTracker:
    """Small deterministic tracker for the four selected court players."""

    def __init__(self, max_distance: float = 0.18, max_missing_samples: int = 18) -> None:
        self.max_distance = max_distance
        self.max_missing_samples = max_missing_samples
        self.next_id = 1
        self.tracks: dict[int, Track] = {}

    def update(self, centers: np.ndarray, sample_index: int) -> list[int]:
        stale = [key for key, item in self.tracks.items() if sample_index - item.last_sample > self.max_missing_samples]
        for key in stale:
            self.tracks.pop(key, None)
        ids = [-1] * len(centers)
        active = list(self.tracks.values())
        if active and len(centers):
            distances = np.linalg.norm(
                np.stack([item.center for item in active])[:, None, :] - centers[None, :, :], axis=2
            )
            rows, cols = linear_sum_assignment(distances)
            for row, col in zip(rows.tolist(), cols.tolist()):
                if distances[row, col] <= self.max_distance:
                    item = active[row]
                    item.center = centers[col]
                    item.last_sample = sample_index
                    ids[col] = item.track_id
        for index, value in enumerate(ids):
            if value >= 0:
                continue
            value = self.next_id
            self.next_id += 1
            self.tracks[value] = Track(value, centers[index], sample_index)
            ids[index] = value
        return ids

    def seed(self, people: list[dict[str, Any]], sample_index: int) -> None:
        """Restore the last known tracks when resuming an interrupted cache."""
        for person in people:
            track_id = int(person["track_id"])
            bbox = np.asarray(person["bbox_xyxy_norm"], dtype=np.float32)
            center = np.array([(bbox[0] + bbox[2]) * 0.5, bbox[3]], dtype=np.float32)
            self.tracks[track_id] = Track(track_id, center, sample_index)
            self.next_id = max(self.next_id, track_id + 1)


def result_boxes(result: Any) -> tuple[np.ndarray, np.ndarray]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
    return boxes.xyxy.detach().cpu().numpy(), boxes.conf.detach().cpu().numpy()


def select_players(boxes: np.ndarray, scores: np.ndarray, width: int, height: int, limit: int = 4) -> tuple[np.ndarray, np.ndarray]:
    if not len(boxes):
        return boxes, scores
    feet_x = (boxes[:, 0] + boxes[:, 2]) * 0.5 / width
    feet_y = boxes[:, 3] / height
    area = ((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])) / (width * height)
    soft_court = (feet_x >= 0.07) & (feet_x <= 0.93) & (feet_y >= 0.10) & (feet_y <= 0.99)
    rank = scores + np.clip(area, 0, 0.15) * 0.7 + soft_court.astype(np.float32) * 0.25
    order = np.argsort(-rank)[:limit]
    return boxes[order], scores[order]


def court_record(result: Any, timestamp_ms: int, width: int, height: int) -> dict[str, Any]:
    boxes, scores = result_boxes(result)
    masks = getattr(result, "masks", None)
    polygons: list[list[list[float]]] = []
    areas: list[float] = []
    if masks is not None:
        for polygon in masks.xy:
            points = np.asarray(polygon, dtype=np.float32)
            if len(points) > 160:
                points = points[:: max(1, len(points) // 160)]
            normalized = points / np.array([width, height], dtype=np.float32)
            polygons.append(rounded(normalized))
        for mask in masks.data.detach().cpu().numpy():
            areas.append(round(float(mask.mean()), 6))
    return {
        "timestamp_ms": timestamp_ms,
        "boxes_xyxy_norm": rounded(boxes / np.array([width, height, width, height], dtype=np.float32)),
        "confidences": rounded(scores),
        "mask_area_ratios": areas,
        "polygons_xy_norm": polygons,
    }


def extract_media(
    *,
    dataset_root: Path,
    dataset_manifest_id: str,
    take: dict[str, Any],
    media: dict[str, Any],
    profile: dict[str, Any],
    models: dict[str, Path],
    person_model: YOLO,
    ball_model: YOLO,
    court_model: YOLO,
    pose_model: RTMPose,
    device: str,
    output_root: Path,
    start_seconds: float,
    resume_partial: bool,
    max_samples: int | None,
) -> dict[str, Any]:
    config = profile["extractor"]
    fps = float(config["sampling_fps"])
    preprocessing = {
        "profile": profile,
        "model_sha256": {name: sha256_file(path) for name, path in models.items()},
    }
    preprocessing_sha = stable_hash(preprocessing)
    cache_identity = {
        "dataset_manifest_id": dataset_manifest_id,
        "logical_media_uri": media["logical_uri"],
        "extractor_name": config["name"],
        "extractor_version": config["version"],
        "sampling_fps": fps,
        "preprocessing_config_sha256": preprocessing_sha,
    }
    cache_key = stable_hash(cache_identity)[:24]
    target = output_root / cache_key
    target.mkdir(parents=True, exist_ok=True)
    summary_path = target / "summary.json"
    if summary_path.exists():
        existing = json.loads(summary_path.read_text())
        if existing.get("status") == "complete" and existing.get("cache_identity") == cache_identity:
            return {"status": "cached", "cache_key": cache_key, "summary": str(summary_path)}

    media_path = dataset_root / media["remote_relative_path"]
    frames_partial = target / "frames.jsonl.partial"
    court_partial = target / "court-line.jsonl.partial"
    tracker = CenterTracker()
    counts = {"samples": 0, "four_players": 0, "pose_usable": 0, "ball_observed": 0, "court_samples": 0}
    started = time.time()
    resumed_sample_count = 0
    resumed_last_timestamp_ms = -1
    resumed_last_people: list[dict[str, Any]] = []
    if resume_partial and frames_partial.exists() and frames_partial.stat().st_size > 0:
        with frames_partial.open() as existing_file:
            for line in existing_file:
                if not line.strip():
                    continue
                record = json.loads(line)
                resumed_sample_count += 1
                resumed_last_timestamp_ms = int(record["take_timestamp_ms"])
                resumed_last_people = record.get("people", [])
                counts["four_players"] += int(record.get("quality", {}).get("four_players_observed", False))
                counts["pose_usable"] += int(record.get("quality", {}).get("pose_usable", False))
                counts["ball_observed"] += int(record.get("quality", {}).get("ball_observed", False))
        counts["samples"] = resumed_sample_count
        tracker.seed(resumed_last_people, max(0, resumed_sample_count - 1))
    resumed_court_count = 0
    if resume_partial and court_partial.exists() and court_partial.stat().st_size > 0:
        with court_partial.open() as existing_court_file:
            resumed_court_count = sum(1 for line in existing_court_file if line.strip())
        counts["court_samples"] = resumed_court_count
    next_sample_seconds = max(
        0.0,
        start_seconds,
        (resumed_last_timestamp_ms / 1000.0 + 0.001) if resumed_last_timestamp_ms >= 0 else 0.0,
    )
    next_court_seconds = max(
        0.0,
        start_seconds,
        (resumed_last_timestamp_ms / 1000.0 + 0.001) if resumed_last_timestamp_ms >= 0 else 0.0,
    )
    first_pts_seconds: float | None = None
    last_timestamp_ms = -1

    frames_mode = "a" if resume_partial and frames_partial.exists() else "w"
    court_mode = "a" if resume_partial and court_partial.exists() else "w"
    with av.open(str(media_path)) as container, frames_partial.open(frames_mode) as frames_out, court_partial.open(court_mode) as court_out:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for decoded_index, frame in enumerate(container.decode(stream)):
            if frame.pts is None:
                continue
            pts_seconds = float(frame.pts * stream.time_base)
            if first_pts_seconds is None:
                first_pts_seconds = pts_seconds
            relative_seconds = max(0.0, pts_seconds - first_pts_seconds)
            if relative_seconds + 1e-6 < next_sample_seconds:
                continue
            timestamp_ms = int(round(relative_seconds * 1000.0))
            image = frame.to_ndarray(format="bgr24")
            height, width = image.shape[:2]

            person_result = person_model.predict(
                image,
                device=device,
                classes=[0],
                conf=float(config["person_detector"]["confidence_threshold"]),
                imgsz=int(config["person_detector"]["image_size"]),
                verbose=False,
            )[0]
            person_boxes, person_scores = result_boxes(person_result)
            person_boxes, person_scores = select_players(person_boxes, person_scores, width, height)
            centers = np.column_stack(((person_boxes[:, 0] + person_boxes[:, 2]) * 0.5 / width, person_boxes[:, 3] / height)) if len(person_boxes) else np.zeros((0, 2))
            track_ids = tracker.update(centers, counts["samples"])

            if len(person_boxes):
                keypoints, keypoint_scores = pose_model(image, person_boxes.tolist())
                keypoints = np.asarray(keypoints)
                keypoint_scores = np.asarray(keypoint_scores)
            else:
                keypoints = np.zeros((0, 26, 2), dtype=np.float32)
                keypoint_scores = np.zeros((0, 26), dtype=np.float32)

            ball_result = ball_model.predict(
                image,
                device=device,
                conf=float(config["ball"]["confidence_threshold"]),
                imgsz=int(config["ball"]["image_size"]),
                verbose=False,
            )[0]
            ball_boxes, ball_scores = result_boxes(ball_result)

            court_available = False
            if relative_seconds + 1e-6 >= next_court_seconds:
                result = court_model.predict(
                    image,
                    device=device,
                    conf=float(config["court_line"]["confidence_threshold"]),
                    imgsz=int(config["court_line"]["image_size"]),
                    verbose=False,
                )[0]
                record = court_record(result, timestamp_ms, width, height)
                court_out.write(json_line(record))
                court_available = bool(record["polygons_xy_norm"])
                counts["court_samples"] += 1
                next_court_seconds += float(config["court_line"]["sample_interval_seconds"])

            visibility_threshold = float(config["pose"]["visibility_threshold"])
            visible_ratio = float((keypoint_scores >= visibility_threshold).mean()) if keypoint_scores.size else 0.0
            four_players = len(person_boxes) == 4
            pose_usable = four_players and visible_ratio >= float(profile["quality_mask"]["minimum_pose_visible_ratio"])
            normalized_scale = np.array([width, height], dtype=np.float32)
            people = []
            for index in range(len(person_boxes)):
                people.append({
                    "track_id": track_ids[index],
                    "bbox_xyxy_norm": rounded(person_boxes[index] / np.array([width, height, width, height], dtype=np.float32)),
                    "det_confidence": round(float(person_scores[index]), 5),
                    "keypoints_xy_norm": rounded(keypoints[index] / normalized_scale),
                    "keypoint_confidences": rounded(keypoint_scores[index]),
                    "keypoint_visible_mask": (keypoint_scores[index] >= visibility_threshold).astype(int).tolist(),
                })
            ball_candidates = []
            for box, score in zip(ball_boxes, ball_scores):
                ball_candidates.append({
                    "bbox_xyxy_norm": rounded(box / np.array([width, height, width, height], dtype=np.float32)),
                    "center_xy_norm": rounded(np.array([(box[0] + box[2]) * 0.5 / width, (box[1] + box[3]) * 0.5 / height])),
                    "confidence": round(float(score), 5),
                })
            sample = {
                "schema_version": "match_state_structured_frame.v1",
                "capture_take_id": take["capture_take_id"],
                "source_session_id": take["source_session_id"],
                "camera_role": media["camera_role"],
                "logical_media_uri": media["logical_uri"],
                "take_timestamp_ms": timestamp_ms,
                "decoded_frame_index": decoded_index,
                "image_size": [width, height],
                "people": people,
                "ball_candidates": ball_candidates,
                "court_coordinates": None,
                "quality": {
                    "four_players_observed": four_players,
                    "pose_visible_ratio": round(visible_ratio, 5),
                    "pose_usable": pose_usable,
                    "ball_observed": bool(ball_candidates),
                    "ball_missing_semantics": None if ball_candidates else "unknown_not_no_ball",
                    "court_line_sample_available": court_available,
                    "court_projection_available": False,
                    "structured_loss_mask": int(pose_usable),
                    "timestamp_monotonic": timestamp_ms > last_timestamp_ms,
                },
            }
            frames_out.write(json_line(sample))
            counts["samples"] += 1
            counts["four_players"] += int(four_players)
            counts["pose_usable"] += int(pose_usable)
            counts["ball_observed"] += int(bool(ball_candidates))
            last_timestamp_ms = timestamp_ms
            next_sample_seconds += 1.0 / fps
            if max_samples is not None and counts["samples"] >= max_samples:
                break

    os.replace(frames_partial, target / "frames.jsonl")
    os.replace(court_partial, target / "court-line.jsonl")
    total = max(1, counts["samples"])
    summary = {
        "schema_version": "match_state_structured_feature_cache.v1",
        "status": "complete",
        "cache_key": cache_key,
        "cache_identity": cache_identity,
        "capture_take_id": take["capture_take_id"],
        "source_session_id": take["source_session_id"],
        "camera_role": media["camera_role"],
        "media_relative_path": media["remote_relative_path"],
        "counts": counts,
        "rates": {key: round(counts[key] / total, 6) for key in ("four_players", "pose_usable", "ball_observed")},
        "elapsed_seconds": round(time.time() - started, 3),
        "last_timestamp_ms": last_timestamp_ms,
        "limited_smoke_run": max_samples is not None,
        "requested_start_seconds": start_seconds,
        "resumed_from_partial": resumed_sample_count > 0,
        "resumed_sample_count": resumed_sample_count,
        "artifacts": {"frames": "frames.jsonl", "court_line": "court-line.jsonl"},
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--only-session")
    parser.add_argument("--only-camera", choices=["cam_1", "cam_2"])
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--resume-partial", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-samples", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.dataset_root.resolve()
    manifest_path = root / "manifests/dataset-manifest-2026-07-20.v1.json"
    manifest = json.loads(manifest_path.read_text())
    profile = json.loads(args.profile.read_text())
    model_root = root / "models"
    onnx_paths = list((model_root / "rtmpose-onnx").rglob("end2end.onnx"))
    if len(onnx_paths) != 1:
        raise RuntimeError(f"expected one RTMPose ONNX model, found {len(onnx_paths)}")
    models = {
        "person": model_root / "person/yolo11x.pt",
        "pose": onnx_paths[0],
        "ball": model_root / "ball/pickleball-ball.pt",
        "court_line": model_root / "court-line/best.pt",
    }
    missing = [str(path) for path in models.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing models: " + ", ".join(missing))
    output_root = args.output_root or root / "cache/structured-v1"
    output_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(root / "environment/ultralytics"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    person_model = YOLO(str(models["person"]))
    ball_model = YOLO(str(models["ball"]))
    court_model = YOLO(str(models["court_line"]))
    pose_model = RTMPose(str(models["pose"]), model_input_size=(192, 256), backend="onnxruntime", device=device)

    results = []
    for take in manifest["takes"]:
        if args.only_session and take["source_session_id"] != args.only_session:
            continue
        for media in take["media"]:
            if args.only_camera and media["camera_role"] != args.only_camera:
                continue
            result = extract_media(
                dataset_root=root,
                dataset_manifest_id=manifest["manifest_id"],
                take=take,
                media=media,
                profile=profile,
                models=models,
                person_model=person_model,
                ball_model=ball_model,
                court_model=court_model,
                pose_model=pose_model,
                device=device,
                output_root=output_root,
                start_seconds=args.start_seconds,
                resume_partial=args.resume_partial,
                max_samples=args.max_samples,
            )
            print(json.dumps(result, ensure_ascii=False))
            results.append(result)
    run_report = {
        "schema_version": "match_state_structured_extraction_run.v1",
        "result_count": len(results),
        "results": results,
    }
    (output_root / "last-run.json").write_text(json.dumps(run_report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
