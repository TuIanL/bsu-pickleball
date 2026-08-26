"""Real-data runner（球 3D：在已有双摄分析任务上做球路重建）。

复用现有系统的双摄分析任务产物：
  - 每视角球场标定（inverse_homography = court→image + 四角关键点 + courtOrientation）
  - 每视角视频（已 merge，帧对齐速度取两路各自 FPS）
新增内容仅为：球路检测跟踪（YoloBallDetector + BallTracker）→ 送进本包核心链。

用法（脚本）：
  python -m app.vision.multiview.ball_stereo.real_data_runner \
      --take_dir <take> --cam1_video 174_merged.mp4 --cam2_video 175_merged.mp4 \
      --cam1_calib <calib-*.json> --cam2_calib <calib-*.json> \
      --cam1_orientation identity --cam2_orientation rotate_180 \
      --window_start_s 5 --window_end_s 20

注意同步行：smoke 阶段假设两路 merged 视频时间轴对齐（同一 take 起始），
帧索引 = round(t * fps)。进阶应改用 CanonicalAnalysisClock。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings
from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.multiview.ball_stereo.artifact_builders import (
    build_stereo_evidence_v1,
    build_v3_trajectory,
)
from app.vision.multiview.ball_stereo.association import (
    BallViewCandidate,
    associate_views,
)
from app.vision.multiview.ball_stereo.landing_authority import resolve_landing
from app.vision.multiview.ball_stereo.metrics import compute_metrics
from app.vision.multiview.ball_stereo.segment_reconstruction import (
    Observation,
    Reconstructed3DSegment,
    Reconstructed3DSample,
    reconstruct_segment,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement, measure_stereo
from app.vision.multiview.ball_stereo.virtual_camera import decompose_virtual_camera
from app.vision.multiview.ball_stereo.net_assisted_camera import refine_virtual_camera_for_scene
from app.vision.detectors.ball_adapter import YoloBallDetectorAdapter
from app.vision.pickleball_game_analysis.ball_tracker import BallTracker, BallTrackerConfig


@dataclass(frozen=True)
class ViewConfig:
    video_path: str
    calibration_path: str
    orientation: str  # identity / rotate_180 / mirror_x / mirror_y
    camera_id: str


def _load_matrix(calib: dict, key: str) -> np.ndarray:
    return np.asarray(calib[key]["values"], dtype=float)


def _load_calib(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _view_observations(
    video_path: str,
    projection: np.ndarray,
    detector: YoloBallDetectorAdapter,
    tracker: BallTracker,
    start_s: float,
    end_s: float,
    frame_stride: int = 2,
    confidence: float = 0.18,
) -> tuple[list[dict], list[float]]:
    """对一段视频跑球检测跟踪，返回真实 source frame 对应的毫秒观测。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_idx = int(round(start_s * fps))
    end_idx = int(round(end_s * fps))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    end_idx = min(end_idx, frame_count - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_idx)
    observations: list[dict] = []
    times: list[float] = []
    idx = start_idx
    while idx <= end_idx:
        ok, frame = cap.read()
        if not ok:
            break
        # cap.read() 每次只推进一帧；stride 只决定哪些真实帧进入 detector，
        # 不能同时把逻辑 idx 按 stride 增长，否则 index/timestamp 会漂移。
        if (idx - start_idx) % max(1, frame_stride) == 0:
            t_ms = idx / fps * 1000.0
            sample = tracker.update(
                frame=frame, frame_index=int(idx), timestamp_sec=t_ms / 1000.0,
                homography=None,  # 我们在 3D 域处理，不需 tracker 的球场投影
            )
            if sample.image_xy is not None and sample.accepted:
                observations.append({"t_ms": t_ms, "u": float(sample.image_xy[0]), "v": float(sample.image_xy[1]), "paired": False})
                times.append(t_ms)
        idx += 1
    cap.release()
    return observations, times


def _group_into_segments(obs_cam1: list[dict], times_cam1: list[float],
                         obs_cam2: list[dict], times_cam2: list[float],
                         gap_ms: float = 400.0,
                         max_pairing_error_ms: float = 40.0) -> list[tuple[list[dict], list[dict]]]:
    """把双路观测按时间聚成若干段（用 cam1 时间轴上 > gap 的间断切分）。"""
    pa = sorted(zip(times_cam1, obs_cam1), key=lambda x: x[0])
    segments: list[tuple[list[dict], list[dict]]] = []
    current_a: list[dict] = []
    current_b: list[dict] = []
    last: float | None = None
    used_cam2: set[int] = set()
    for t, o in pa:
        if last is not None and (t - last) > gap_ms and current_a:
            segments.append((current_a, current_b))
            current_a, current_b = [], []
        current_a.append(o)
        # cam2 在同一时间窗 ±tolerance 内的观测加入
        candidates = [
            (index, bt, b)
            for index, (bt, b) in enumerate(zip(times_cam2, obs_cam2))
            if index not in used_cam2 and abs(bt - t) <= max_pairing_error_ms
        ]
        if candidates:
            index, _bt, best = min(candidates, key=lambda item: abs(item[1] - t))
            used_cam2.add(index)
            current_b.append(best)
        last = t
    if current_a:
        segments.append((current_a, current_b))
    return segments


def _video_size(video_path: str) -> tuple[int, int]:
    cap = cv2.VideoCapture(video_path)
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()


def _write_artifacts_to_job(doc: dict, evidence: dict, job_id: str) -> dict:
    """把 v3 轨迹 + 立体证据写入正式 job 的产物路径（任务 4.3 / 8.4 发布侧）。

    复用 StorageService 的 artifact 路径，composer 据此继承到 Parent、routes 据此读取。
    """
    from app.services.storage_service import StorageService

    storage = StorageService()
    v3_path = storage.reconstructed_ball_trajectory_json_path(job_id)
    evidence_path = storage.multiview_ball_stereo_evidence_path(job_id)
    v3_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    v3_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"v3": str(v3_path), "evidence": str(evidence_path)}


def run_real_data(
    *,
    cam1: ViewConfig,
    cam2: ViewConfig,
    window_start_s: float,
    window_end_s: float,
    frame_stride: int = 2,
    output_path: str | None = None,
    take_id: str = "real",
    job_id: str = "ball3d",
    dump_obs_path: str | None = None,
    write_evidence_to_job: bool = False,
    scene_calibration: object | None = None,
) -> dict:
    settings = get_settings()
    assert settings.ball_model_path, "PICKLEBALL_BALL_MODEL_PATH 未配置"
    detector1 = YoloBallDetectorAdapter(model_path=settings.ball_model_path, confidence_threshold=0.18)
    detector2 = YoloBallDetectorAdapter(model_path=settings.ball_model_path, confidence_threshold=0.18)
    tracker1 = BallTracker(detector=detector1, config=BallTrackerConfig())
    tracker2 = BallTracker(detector=detector2, config=BallTrackerConfig())

    c1 = _load_calib(cam1.calibration_path)
    c2 = _load_calib(cam2.calibration_path)
    inv1 = _load_matrix(c1, "inverse_homography")
    inv2 = _load_matrix(c2, "inverse_homography")

    ori1 = CourtOrientation(cam1.orientation)
    ori2 = CourtOrientation(cam2.orientation)

    # corner 配对必须在同一次序：把每个标定 keypoint 的 local-court 坐标经 orientation 转 canonical，
    # 保证 canonical 点与对应 image 点顺序一致（rotate_180 / mirror 视角会翻转顺序）。
    def _corners(calib: dict, ori) -> tuple[list, list]:
        canon, img = [], []
        for k in calib["keypoints"]:
            cx_, cy_ = local_to_canonical(float(k["court"]["x"]), float(k["court"]["y"]), ori)
            canon.append([cx_, cy_])
            img.append([k["image"]["x"], k["image"]["y"]])
        return canon, img

    corner_canon1, corner_img1 = _corners(c1, ori1)
    corner_canon2, corner_img2 = _corners(c2, ori2)

    cam1_width, cam1_height = _video_size(cam1.video_path)
    cam2_width, cam2_height = _video_size(cam2.video_path)
    cam1_proj = decompose_virtual_camera(
        view_id="cam_1", inverse_homography=inv1,
        image_width=cam1_width, image_height=cam1_height,
        orientation=ori1, corner_canonical=corner_canon1, corner_image=corner_img1,
    )
    cam2_proj = decompose_virtual_camera(
        view_id="cam_2", inverse_homography=inv2,
        image_width=cam2_width, image_height=cam2_height,
        orientation=ori2, corner_canonical=corner_canon2, corner_image=corner_img2,
    )
    if not cam1_proj.available or not cam2_proj.available:
        return {"status": "unavailable",
                "cam1_status": cam1_proj.status, "cam2_status": cam2_proj.status,
                "reason": "virtual camera unavailable"}

    if scene_calibration is not None:
        cam1_proj = refine_virtual_camera_for_scene(
            cam1_proj,
            court_world=corner_canon1,
            court_image=corner_img1,
            scene_calibration=scene_calibration,
            view_id="cam_1",
            court_orientation=ori1,
        )
        cam2_proj = refine_virtual_camera_for_scene(
            cam2_proj,
            court_world=corner_canon2,
            court_image=corner_img2,
            scene_calibration=scene_calibration,
            view_id="cam_2",
            court_orientation=ori2,
        )

    projection_sources = [cam1_proj.source, cam2_proj.source]
    metric_qualified = all(
        camera.source == "net_refined_virtual"
        and not camera.approximate
        and bool(camera.disambiguation.get("metric_qualified", True))
        for camera in (cam1_proj, cam2_proj)
    )
    metric_qualified = metric_qualified and (
        scene_calibration is None or getattr(scene_calibration, "status", None) == "ready"
    )
    camera_model_source = (
        "net_refined_virtual"
        if all(source == "net_refined_virtual" for source in projection_sources)
        else "homography_constrained_virtual"
        if all(source == "homography_constrained_virtual" for source in projection_sources)
        else "mixed_virtual"
    )
    metric_validity = "metric_multiview" if metric_qualified else "approximate_multiview"
    height_uncertainties = [
        float(camera.disambiguation["height_uncertainty_ft"])
        for camera in (cam1_proj, cam2_proj)
        if isinstance(camera.disambiguation.get("height_uncertainty_ft"), (int, float))
        and math.isfinite(float(camera.disambiguation["height_uncertainty_ft"]))
    ]
    scene_quality = {
        "scene_status": getattr(scene_calibration, "status", "missing") if scene_calibration is not None else "missing",
        "effective_status": "ready" if metric_qualified else "degraded",
        "camera_model_sources": projection_sources,
        "camera_diagnostics": {
            "cam_1": dict(cam1_proj.disambiguation),
            "cam_2": dict(cam2_proj.disambiguation),
        },
        "metric_qualified": metric_qualified,
        "rejection_reasons": sorted({
            str(reason)
            for camera in (cam1_proj, cam2_proj)
            for reason in camera.disambiguation.get("quality_rejection_reasons", [])
        }),
    }
    scene_revision = getattr(scene_calibration, "revision", None) if scene_calibration is not None else None
    source_context = {
        "job_id": job_id,
        "clock": "RealDataRunner",
        "scene_calibration_revision": scene_revision,
        "camera_model_source": camera_model_source,
        "metric_validity": metric_validity,
        "height_uncertainty_ft": max(height_uncertainties) if height_uncertainties else None,
        "scene_quality": scene_quality,
    }

    print(f"[cam1] focal={cam1_proj.focal_ft:.1f} reproj={cam1_proj.reprojection_error_px:.2f}px")
    print(f"[cam2] focal={cam2_proj.focal_ft:.1f} reproj={cam2_proj.reprojection_error_px:.2f}px")

    obs1, t1 = _view_observations(cam1.video_path, cam1_proj.projection, detector1, tracker1,
                                  window_start_s, window_end_s, frame_stride)
    obs2, t2 = _view_observations(cam2.video_path, cam2_proj.projection, detector2, tracker2,
                                  window_start_s, window_end_s, frame_stride)
    print(f"[cam1] {len(obs1)} accepted ball obs; [cam2] {len(obs2)} accepted ball obs")
    if dump_obs_path:
        dump_path = Path(dump_obs_path)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "window_start_s": window_start_s, "window_end_s": window_end_s, "frame_stride": frame_stride,
            "cam1_calib": cam1.calibration_path, "cam2_calib": cam2.calibration_path,
            "cam1_orientation": cam1.orientation, "cam2_orientation": cam2.orientation,
            "obs_cam1": obs1, "obs_cam2": obs2, "t_cam1": t1, "t_cam2": t2,
        }
        dump_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"dumped observations -> {dump_path}")
        return {"status": "dumped", "obs_cam1": len(obs1), "obs_cam2": len(obs2)}

    # 组装观测 + 测量证据
    measurements: list[BallStereoMeasurement] = []
    segment_obs_list = []  # (cam_index, t_ms, u, v, projection)
    used_cam2: set[int] = set()
    max_time_gate_ms = 40.0
    for o in obs1:
        candidates = [
            (index, b)
            for index, (bt, b) in enumerate(zip(t2, obs2))
            if index not in used_cam2 and abs(bt - o["t_ms"]) <= max_time_gate_ms
        ]
        if candidates:
            best_index, b = min(candidates, key=lambda item: abs(o["t_ms"] - item[1]["t_ms"]))
            used_cam2.add(best_index)
            m = measure_stereo(
                projection_cam1=cam1_proj.projection, projection_cam2=cam2_proj.projection,
                image_xy1=(o["u"], o["v"]), image_xy2=(b["u"], b["v"]),
                cam1_timestamp_ms=o["t_ms"], cam2_timestamp_ms=b["t_ms"],
                take_timestamp_ms=o["t_ms"], sync_error_ms=abs(o["t_ms"] - b["t_ms"]),
                max_time_delta_ms=max_time_gate_ms,
                scene_calibration_revision=scene_revision,
                camera_model_source=camera_model_source,
                metric_validity=metric_validity,
                height_uncertainty_ft=max(height_uncertainties) if height_uncertainties else None,
                scene_quality=scene_quality,
            )
            if not m.depth_valid:
                # 错误深度只进入诊断，不进入权威 stereo evidence；保留两路单视角观测供
                # 段级重建判断是否可以降级为 PARTIAL_3D。
                segment_obs_list.append(Observation(o["t_ms"] / 1000.0, 0, o["u"], o["v"], cam1_proj.projection, paired=False))
                segment_obs_list.append(Observation(b["t_ms"] / 1000.0, 1, b["u"], b["v"], cam2_proj.projection, paired=False))
                continue
            measurements.append(m)
            segment_obs_list.append(Observation(o["t_ms"] / 1000.0, 0, o["u"], o["v"], cam1_proj.projection, paired=True))
            segment_obs_list.append(Observation(b["t_ms"] / 1000.0, 1, b["u"], b["v"], cam2_proj.projection, paired=True))
        else:
            segment_obs_list.append(Observation(o["t_ms"] / 1000.0, 0, o["u"], o["v"], cam1_proj.projection, paired=False))
    for b in obs2:
        if not any(abs(bt - b["t_ms"]) <= max_time_gate_ms for bt in t1):
            segment_obs_list.append(Observation(b["t_ms"] / 1000.0, 1, b["u"], b["v"], cam2_proj.projection, paired=False))

    # 段重建（smoke：全部观测作为一条段）
    duration = max((window_end_s - window_start_s), 1.0)
    if segment_obs_list:
        all_t = [o.t_sec for o in segment_obs_list]
        duration = max(max(all_t) - min(all_t), 0.3)
    seg = reconstruct_segment(
        segment_id="seg_real_1", observations=segment_obs_list,
        landing_xy=None, bounce_end=False, max_control_points=8,
    )
    # 落点权威（smoke：各视角球亚班候选未做 bounce 判定，落点仅在有明显近地观测时给单视角）
    landing = None

    metrics = compute_metrics(seg, duration_sec=duration) if seg.samples else None
    doc = build_v3_trajectory(
        job_id=job_id, take_id=take_id, bounce_source="reference_view_confirmed",
        segments=[seg], landing=landing,
        metrics_by_segment={"seg_real_1": metrics} if metrics else {},
        duration_by_segment={"seg_real_1": duration},
        scene_calibration_revision=scene_revision,
        metric_validity=metric_validity,
        height_uncertainty_ft=max(height_uncertainties) if height_uncertainties else None,
        diagnostics={
            "camera_model_source": camera_model_source,
            "scene_quality": scene_quality,
        },
    )
    evidence = build_stereo_evidence_v1(
        take_id=take_id,
        measurements=measurements,
        pairings=[],
        diagnostics={
            "camera_model_source": camera_model_source,
            "metric_validity": metric_validity,
            "scene_quality": scene_quality,
        },
        source_context=source_context,
    )

    written = None
    if write_evidence_to_job:
        written = _write_artifacts_to_job(doc, evidence, job_id)
        print(f"wrote artifacts to job {job_id}: {written}")

    result = {
        "status": "ok",
        "cam1_focal_ft": cam1_proj.focal_ft,
        "cam2_focal_ft": cam2_proj.focal_ft,
        "cam1_reproj_px": cam1_proj.reprojection_error_px,
        "cam2_reproj_px": cam2_proj.reprojection_error_px,
        "scene_calibration_revision": scene_revision,
        "camera_model_source": camera_model_source,
        "metric_validity": metric_validity,
        "scene_quality": scene_quality,
        "ball_obs_cam1": len(obs1),
        "ball_obs_cam2": len(obs2),
        "stereo_measurements": len(measurements),
        "segment_status": seg.status,
        "stereo_coverage": seg.stereo_coverage,
        "reprojection_error_px": seg.reprojection_error_px,
        "overall_status": doc["overall_status"],
        "v3_trajectory": doc,
        "stereo_evidence": evidence,
    }
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # 只写 v3（evidence v1 另有路径由 composer 管理）
        Path(output_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote v3 artifact -> {output_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-data ball 3D reconstruction")
    parser.add_argument("--take_dir", required=True)
    parser.add_argument("--cam1_video", default="174_merged.mp4")
    parser.add_argument("--cam2_video", default="175_merged.mp4")
    parser.add_argument("--cam1_calib", required=True)
    parser.add_argument("--cam2_calib", required=True)
    parser.add_argument("--cam1_orientation", default="identity")
    parser.add_argument("--cam2_orientation", default="rotate_180")
    parser.add_argument("--window_start_s", type=float, default=0.0)
    parser.add_argument("--window_end_s", type=float, default=15.0)
    parser.add_argument("--frame_stride", type=int, default=2)
    parser.add_argument("--output", default=None)
    parser.add_argument("--dump_obs", default=None)
    parser.add_argument("--job_id", default=None)
    parser.add_argument("--write_evidence_to_job", action="store_true")
    args = parser.parse_args()

    cam1 = ViewConfig(video_path=str(Path(args.take_dir) / args.cam1_video),
                      calibration_path=args.cam1_calib, orientation=args.cam1_orientation, camera_id="174")
    cam2 = ViewConfig(video_path=str(Path(args.take_dir) / args.cam2_video),
                      calibration_path=args.cam2_calib, orientation=args.cam2_orientation, camera_id="175")
    result = run_real_data(
        cam1=cam1, cam2=cam2,
        window_start_s=args.window_start_s, window_end_s=args.window_end_s,
        frame_stride=args.frame_stride, output_path=args.output,
        dump_obs_path=args.dump_obs,
        job_id=args.job_id or "ball3d",
        write_evidence_to_job=args.write_evidence_to_job,
    )
    summary = {k: v for k, v in result.items() if k not in ("v3_trajectory", "stereo_evidence")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
