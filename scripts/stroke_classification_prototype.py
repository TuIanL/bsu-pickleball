"""动作分类离线原型：pose_overlay.json → 尺度归一 → 挥拍切窗 → 41 维特征。

只读分析产物，不写产品代码、不产生任何 commit 级副作用。
产物：一份逐挥拍 CSV（窗口、球员、尺度、特征）+ 一份 summary JSON。

用法：
    python scripts/stroke_classification_prototype.py \
        --pose "/Volumes/.../analysis/job-96a28d6ff0/pose_overlay.json" \
        --out /tmp/stroke_proto
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import statistics as st
import sys
import types
from collections import defaultdict
from pathlib import Path

import numpy as np

# 训练侧特征定义所在仓库（只读引用，不复制）
DATASET_REPO = Path("/Users/tuian/Documents/大学/竞赛/大创/匹克球/动作分类/pickleball-action-dataset")

# 训练参考尺度：947 条训练素材的人体框高中位数
TRAIN_REFERENCE_BBOX_PX = 254.0

# 挥拍检测默认参数（任务 1.4 会据实调整）
NMS_SECONDS = 0.6
SPEED_PERCENTILE = 99.0
# 训练集 right_wrist_max_speed 的 p5 = 640 / p10 = 787（已处于 254 px 参考尺度）。
# 连续视频里真实挥拍的归一化峰值不应低于其 p5，故以此作为绝对下限。
MIN_NORMALIZED_PEAK = 600.0
# 峰值相对本 track 自身速度水平的倍数（排除走位、抬手这类慢动作）
PROMINENCE_RATIO = 2.0


def load_feature_module():
    """加载训练侧 features.py，绕开其包初始化（只需要 extract_features 与特征名）。"""

    class RawPoseSample:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    for name in ("pb_action_dataset", "pb_action_dataset.action_classification"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    stub = types.ModuleType("pb_action_dataset.action_classification.datasets")
    stub.RawPoseSample = RawPoseSample
    stub.REPO = DATASET_REPO
    stub.ActionClassificationDataset = object
    stub.TemporalPoseSample = object
    sys.modules[stub.__name__] = stub

    path = DATASET_REPO / "src/pb_action_dataset/action_classification/features.py"
    spec = importlib.util.spec_from_file_location(
        "pb_action_dataset.action_classification.features", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, RawPoseSample


def load_pose(path: Path):
    """读 pose_overlay.json → 按 track 分组的时序。"""
    payload = json.loads(path.read_text())
    frames = payload.get("frames") or []
    if not frames:
        raise SystemExit(f"pose_overlay 没有 frames：{path}")

    names = None
    tracks: dict[str, dict[str, list]] = defaultdict(
        lambda: {"t": [], "frame": [], "bbox": [], "kp": [], "visible": []}
    )
    for frame in frames:
        fi = int(frame["frame_index"])
        ts = float(frame["timestamp_seconds"])
        for subject in frame.get("subjects") or []:
            keypoints = subject.get("keypoints") or []
            if not keypoints:
                continue
            if names is None:
                names = [k["name"] for k in keypoints]
            track_id = str(subject.get("track_id"))
            bucket = tracks[track_id]
            bucket["t"].append(ts)
            bucket["frame"].append(fi)
            bucket["bbox"].append(subject.get("bbox") or [math.nan] * 4)
            bucket["kp"].append([[k["x"], k["y"], k["confidence"]] for k in keypoints])
            bucket["visible"].append([bool(k.get("visible")) for k in keypoints])

    if names is None:
        raise SystemExit("pose_overlay 里没有任何带关键点的主体")
    return payload, names, tracks


def estimate_fps(frame_index: np.ndarray, t: np.ndarray) -> float:
    """由 frame_index 与时间戳反推源视频 fps（采样步长不影响换算）。"""
    if len(t) < 2:
        return 30.0
    di = np.diff(frame_index.astype(float))
    dt = np.diff(t)
    mask = (dt > 1e-6) & (di > 0)
    if not mask.any():
        return 30.0
    return float(np.median(di[mask] / dt[mask]))


def wrist_speed_series(kp: np.ndarray, visible: np.ndarray, t: np.ndarray, idx: int, fps: float, frame_index: np.ndarray):
    """腕部速度序列 px/s；缺失帧为 NaN。dt 用真实时间而非帧序。"""
    n = len(t)
    speed = np.full(n, np.nan)
    for i in range(1, n):
        if not (visible[i][idx] and visible[i - 1][idx]):
            continue
        p0, p1 = kp[i - 1][idx][:2], kp[i][idx][:2]
        if not (np.isfinite(p0).all() and np.isfinite(p1).all()):
            continue
        dt = (frame_index[i] - frame_index[i - 1]) / fps
        if dt <= 0:
            continue
        speed[i] = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / dt
    return speed


def detect_swings(speed: np.ndarray, t: np.ndarray, threshold: float, prominence_floor: float):
    """局部极大 + 显著度 + 非极大抑制，返回 (时间, 峰值) 列表。"""
    peaks = []
    for i in range(1, len(speed) - 1):
        s = speed[i]
        if not np.isfinite(s) or s < threshold:
            continue
        left = speed[i - 1] if np.isfinite(speed[i - 1]) else -1.0
        right = speed[i + 1] if np.isfinite(speed[i + 1]) else -1.0
        if s < left or s < right:
            continue
        # 显著度：峰值须明显高于邻域低谷，排除持续匀速移动
        lo = max(0, i - 15)
        hi = min(len(speed), i + 16)
        local = speed[lo:hi]
        local = local[np.isfinite(local)]
        if len(local) and (s - float(local.min())) < prominence_floor:
            continue
        peaks.append((t[i], float(s)))
    peaks.sort(key=lambda item: item[1], reverse=True)
    kept = []
    for ts, value in peaks:
        if all(abs(ts - k[0]) > NMS_SECONDS for k in kept):
            kept.append((ts, value))
    kept.sort(key=lambda item: item[0])
    return kept


def build_window_sample(RawPoseSample, bucket, names, idx, t0, t1, fps, label_id):
    """截窗口 → 按框高缩放 → 构造训练侧可消费的样本。"""
    ts = np.array(bucket["t"], dtype=float)
    sel = np.where((ts >= t0) & (ts <= t1))[0]
    if len(sel) < 4:
        return None

    kp_all = bucket["kp"]
    bbox_all = bucket["bbox"]
    visible_all = bucket["visible"]

    kp = np.array([[kp_all[i][j] for j in range(len(names))] for i in sel], dtype=float)
    vis = np.array([visible_all[i] for i in sel], dtype=bool)
    bbox = np.array([bbox_all[i] for i in sel], dtype=float)

    heights = bbox[:, 3] - bbox[:, 1]
    heights = heights[np.isfinite(heights) & (heights > 1)]
    if not len(heights):
        return None
    bbox_h = float(np.median(heights))

    # 按训练参考尺度缩放坐标（角度与比例类特征不变，像素量纲特征回到训练分布）
    scale = TRAIN_REFERENCE_BBOX_PX / bbox_h
    kp[:, :, :2] *= scale
    bbox = bbox * scale

    kp26 = np.zeros((len(sel), 26, 3), dtype=float)
    pres26 = np.zeros((len(sel), 26), dtype=bool)
    for j, name in enumerate(names):
        target = idx.get(name)
        if target is None:
            continue
        kp26[:, target] = kp[:, j]
        pres26[:, target] = vis[:, j] & np.isfinite(kp[:, j, :2]).all(axis=1)

    sample = RawPoseSample(
        sample_id=f"{label_id}",
        keypoints=kp26,
        presence_mask=pres26,
        source_frame_index=np.array([bucket["frame"][i] for i in sel], dtype=int),
        source_fps=(fps, 1),
        tube_bbox=bbox,
        target_side=None,
        stroke_type="unknown",
    )
    return sample, scale, bbox_h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pose", required=True, help="pose_overlay.json 路径")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--pre", type=float, default=0.6, help="触球前缓冲秒数")
    ap.add_argument("--post", type=float, default=0.4, help="触球后缓冲秒数")
    ap.add_argument("--min-bbox-height", type=float, default=150.0, help="最小可用人体框高 px")
    ap.add_argument("--min-peak", type=float, default=MIN_NORMALIZED_PEAK,
                    help="归一化腕速峰值下限 px/s")
    args = ap.parse_args()

    features_mod, RawPoseSample = load_feature_module()
    feature_names = features_mod.load_feature_names()
    halpe_index = {name: i for i, name in enumerate(
        ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder",
         "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
         "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
         "head", "neck", "hip", "left_big_toe", "right_big_toe", "left_small_toe",
         "right_small_toe", "left_heel", "right_heel"])}

    payload, names, tracks = load_pose(Path(args.pose))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    diagnostics = []
    for track_id, bucket in tracks.items():
        frame_index = np.array(bucket["frame"], dtype=int)
        ts = np.array(bucket["t"], dtype=float)
        kp = np.array(bucket["kp"], dtype=float)
        vis = np.array(bucket["visible"], dtype=bool)
        if len(ts) < 8:
            diagnostics.append({"track_id": track_id, "skipped": "too_few_frames", "n": len(ts)})
            continue
        fps = estimate_fps(frame_index, ts)

        heights = np.array([b[3] - b[1] for b in bucket["bbox"]], dtype=float)
        heights = heights[np.isfinite(heights) & (heights > 1)]
        track_h = float(np.median(heights)) if len(heights) else 0.0
        if track_h < args.min_bbox_height:
            diagnostics.append({"track_id": track_id, "skipped": "bbox_too_small",
                                "bbox_height_median": round(track_h, 1)})
            continue

        # 两个腕都算，按训练参考尺度归一后逐帧取较大者（不假设持拍手）
        norm = TRAIN_REFERENCE_BBOX_PX / track_h
        series = {}
        for side in ("left_wrist", "right_wrist"):
            if side in names:
                raw = wrist_speed_series(kp, vis, ts, names.index(side), fps, frame_index)
                series[side] = raw * norm
        if not series:
            diagnostics.append({"track_id": track_id, "skipped": "no_wrist_keypoint"})
            continue
        stack = np.vstack(list(series.values()))
        valid = np.isfinite(stack).any(axis=0)
        combined = np.full(stack.shape[1], np.nan)
        if valid.any():
            combined[valid] = np.nanmax(stack[:, valid], axis=0)
        finite = combined[np.isfinite(combined)]
        if not len(finite):
            diagnostics.append({"track_id": track_id, "skipped": "no_finite_speed",
                                "bbox_height_median": round(track_h, 1)})
            continue
        thr = max(float(np.percentile(finite, SPEED_PERCENTILE)), args.min_peak)
        prominence = PROMINENCE_RATIO * float(np.nanmedian(finite))
        peaks = detect_swings(combined, ts, thr, prominence)
        if not peaks:
            diagnostics.append({"track_id": track_id, "skipped": "no_swing_detected",
                                "bbox_height_median": round(track_h, 1),
                                "threshold_norm_px_s": round(thr, 1)})
            continue

        for k, (contact_t, peak_speed) in enumerate(peaks):
            t0 = max(ts[0], contact_t - args.pre)
            t1 = min(ts[-1], contact_t + args.post)
            built = build_window_sample(RawPoseSample, bucket, names, halpe_index,
                                        t0, t1, fps, f"{track_id}-{k}")
            if built is None:
                continue
            sample, scale, bbox_h = built
            feats = features_mod.extract_features(sample)
            i_peak = int(np.argmin(np.abs(ts - contact_t)))
            side = max(series, key=lambda s: series[s][i_peak] if np.isfinite(series[s][i_peak]) else -1.0)
            row = {
                "track_id": track_id,
                "window_index": k,
                "contact_s": round(contact_t, 3),
                "start_s": round(t0, 3),
                "end_s": round(t1, 3),
                "side": side,
                "threshold_norm_px_s": round(thr, 1),
                "peak_speed_norm_px_s": round(peak_speed, 1),
                "bbox_height_px": round(bbox_h, 1),
                "scale_factor": round(scale, 4),
                "n_frames": int(sample.keypoints.shape[0]),
            }
            row.update({name: feats.get(name) for name in feature_names})
            rows.append(row)

    if not rows:
        print("没有产生任何挥拍窗口", flush=True)
        (out_dir / "summary.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2))
        return 1

    with (out_dir / "swings.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    scales = np.array([r["scale_factor"] for r in rows], dtype=float)
    bbox_hs = np.array([r["bbox_height_px"] for r in rows], dtype=float)
    summary = {
        "pose_file": str(args.pose),
        "job_id": payload.get("job_id"),
        "video_id": payload.get("video_id"),
        "source": payload.get("source"),
        "n_tracks": len(tracks),
        "n_windows": len(rows),
        "n_tracks_with_windows": len({r["track_id"] for r in rows}),
        "windows_per_track": {str(k): v for k, v in
                              __import__("collections").Counter(r["track_id"] for r in rows).items()},
        "bbox_height_px": {"median": round(float(np.median(bbox_hs)), 1),
                           "p25": round(float(np.percentile(bbox_hs, 25)), 1),
                           "p75": round(float(np.percentile(bbox_hs, 75)), 1)},
        "scale_factor": {"median": round(float(np.median(scales)), 3),
                         "min": round(float(scales.min()), 3),
                         "max": round(float(scales.max()), 3)},
        "params": {"pre_s": args.pre, "post_s": args.post, "nms_s": NMS_SECONDS,
                   "speed_percentile": SPEED_PERCENTILE, "min_normalized_peak": MIN_NORMALIZED_PEAK,
                   "prominence_ratio": PROMINENCE_RATIO, "min_bbox_height": args.min_bbox_height,
                   "train_reference_bbox_px": TRAIN_REFERENCE_BBOX_PX},
        "diagnostics": diagnostics,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: summary[k] for k in
                      ("n_tracks", "n_windows", "n_tracks_with_windows",
                       "bbox_height_px", "scale_factor")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
