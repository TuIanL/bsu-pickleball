"""Real-data flight analyzer（球 3D debug 工具，非产物）。

读取 real_data_runner --dump_obs 的观测，重算双路投影，三角测量每对观测，
按时间+空间连续性切飞行段，对每段用**原始图像观测**跑 segment_reconstruction，
报告各段质量，用于在真实双摄数据上定位干净飞行段（无需重跑 YOLO）。

用法：
  python -m app.vision.multiview.ball_stereo.real_data_analyze --obs /tmp/ball3d_obs.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.vision.multiview.ball_stereo.bundle_refine import (
    BAPlaneAnchor,
    CameraInit,
    bundle_refine,
)
from app.vision.multiview.ball_stereo.segment_reconstruction import Observation, reconstruct_segment
from app.vision.multiview.ball_stereo.stereo_measurement import triangulate_linear
from app.vision.multiview.ball_stereo.virtual_camera import decompose_virtual_camera
from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical


def _matrix(calib: dict, key: str) -> np.ndarray:
    return np.asarray(calib[key]["values"], dtype=float)


def _corners(calib: dict, ori) -> tuple[list, list]:
    canon, img = [], []
    for k in calib["keypoints"]:
        cx_, cy_ = local_to_canonical(float(k["court"]["x"]), float(k["court"]["y"]), ori)
        canon.append([cx_, cy_])
        img.append([k["image"]["x"], k["image"]["y"]])
    return canon, img


def _projection(calib_path: str, orientation: str, view_id: str):
    calib = json.loads(Path(calib_path).read_text(encoding="utf-8"))
    inv = _matrix(calib, "inverse_homography")
    ori = CourtOrientation(orientation)
    canon, img = _corners(calib, ori)
    result = decompose_virtual_camera(
        view_id=view_id, inverse_homography=inv, image_width=1920, image_height=1080,
        orientation=ori, corner_canonical=canon, corner_image=img,
    )
    anchor = BAPlaneAnchor(canonical_xy=canon, image_xy=img)
    return result, anchor


def _triangulate_row(p1, p2, o1, used2, obs2, t2, max_time_gate_ms: float = 40.0) -> dict | None:
    best, besti, best_o2, best_tt, bd = None, None, None, None, 1e9
    for j, (o2, tt) in enumerate(zip(obs2, t2)):
        if abs(tt - o1["t_ms"]) > max_time_gate_ms or used2[j]:
            continue
        try:
            xyz = triangulate_linear(p1.projection, p2.projection, (o1["u"], o1["v"]), (o2["u"], o2["v"]))
        except Exception:
            continue
        h = p1.projection @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
        h2 = p2.projection @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
        if abs(h[2]) < 1e-9 or abs(h2[2]) < 1e-9:
            continue
        d1 = np.hypot(h[0] / h[2] - o1["u"], h[1] / h[2] - o1["v"])
        d2 = np.hypot(h2[0] / h2[2] - o2["u"], h2[1] / h2[2] - o2["v"])
        if d1 + d2 < bd:
            bd = d1 + d2
            best, besti, best_o2, best_tt = (xyz, d1 + d2), j, o2, tt
    if best is None:
        return None
    used2[besti] = True
    xyz, reproj = best
    return {"t1_ms": o1["t_ms"], "t2_ms": best_tt, "u1": o1["u"], "v1": o1["v"],
            "u2": best_o2["u"], "v2": best_o2["v"], "x": float(xyz[0]), "y": float(xyz[1]),
            "z": float(xyz[2]), "reproj": float(reproj)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--obs", required=True)
    parser.add_argument("--max_reproj", type=float, default=40.0)
    args = parser.parse_args()
    d = json.loads(Path(args.obs).read_text(encoding="utf-8"))
    res1, anc1 = _projection(d["cam1_calib"], d["cam1_orientation"], "cam1")
    res2, anc2 = _projection(d["cam2_calib"], d["cam2_orientation"], "cam2")
    p1, p2 = res1, res2
    obs1, obs2, t1, t2 = d["obs_cam1"], d["obs_cam2"], d["t_cam1"], d["t_cam2"]
    cam1_init = CameraInit(res1.focal_ft, res1.rotation, res1.translation, res1.image_width / 2.0, res1.image_height / 2.0)
    cam2_init = CameraInit(res2.focal_ft, res2.rotation, res2.translation, res2.image_width / 2.0, res2.image_height / 2.0)

    used2 = [False] * len(obs2)
    rows = []
    for o1 in obs1:
        r = _triangulate_row(p1, p2, o1, used2, obs2, t2, max_time_gate_ms=40.0)
        if r is not None:
            rows.append(r)
    rows.sort(key=lambda r: r["t1_ms"])

    # up 校正：球场上方相机的 canonical +z 应朝上（球/球员高度为正）。
    # 若球场内观测的中位高度为负，说明双路虚拟相机的 up 约定落在下方，统一翻转 z（平面 z=0 上不变）。
    in_court = [r for r in rows if -5.0 <= r["x"] <= 25.0 and -5.0 <= r["y"] <= 49.0]
    if in_court:
        med_z = np.median([r["z"] for r in in_court])
        if med_z < 0.0:
            for r in rows:
                r["z"] = -r["z"]
            print("up correction applied: flipped canonical z sign (median z < 0)")

    # 切段：用 3D 时空连续性把短促飞行连成轨迹。真实球在 ~33ms 内移动有界；
    # 孤立误检（球员球拍/背景）会在 3D 上跳变，无法连成平滑短轨迹。
    max_step_ft = 5.0
    max_gap_ms = 120.0
    min_len = 5
    tracks: list[list[dict]] = []
    open_tracks: list[dict] = []  # {last_t, last_xyz, pts}
    for r in rows:
        best, bi, bd = None, None, 1e9
        for i, tr in enumerate(open_tracks):
            dt = r["t1_ms"] - tr["last_t"]
            if 0 <= dt <= max_gap_ms:
                dist = float(np.sqrt((r["x"] - tr["last_xyz"][0]) ** 2 + (r["y"] - tr["last_xyz"][1]) ** 2
                              + (r["z"] - tr["last_xyz"][2]) ** 2))
                if dist <= max_step_ft and dist < bd:
                    bd, best, bi = dist, tr, i
        if best is None:
            open_tracks.append({"last_t": r["t1_ms"], "last_xyz": (r["x"], r["y"], r["z"]), "pts": [r]})
        else:
            best["last_t"] = r["t1_ms"]; best["last_xyz"] = (r["x"], r["y"], r["z"]); best["pts"].append(r)
            # 由 best 成为 open_tracks[bi] 的新头部：我们把追到最近者作为扩展焦点
    # 结束所有 open tracks
    for tr in open_tracks:
        if len(tr["pts"]) >= min_len:
            tracks.append(tr["pts"])

    print(f"paired 3D rows: {len(rows)}  continuity tracks(≥{min_len}, ≤{max_step_ft}ft step): {len(tracks)}")
    for si, pts in enumerate(tracks):
        pts.sort(key=lambda r: r["t1_ms"])
        obs = []
        for r in pts:
            obs.append(Observation(r["t1_ms"] / 1000.0, 0, r["u1"], r["v1"], p1.projection, paired=True))
            obs.append(Observation(r["t2_ms"] / 1000.0, 1, r["u2"], r["v2"], p2.projection, paired=True))
        t0, t1s = pts[0]["t1_ms"], pts[-1]["t1_ms"]
        span = max(t1s - t0, 1.0) / 1000.0

        # 固定相机重建 + Bundle Adjustment（联合优化双相机焦距/微小外参+曲线）
        res = reconstruct_segment(segment_id=f"tf{si}", observations=obs, max_control_points=6)
        ba = bundle_refine(
            cam1=cam1_init, cam2=cam2_init, observations=obs,
            plane_anchor_1=anc1, plane_anchor_2=anc2, n_control=6,
            focal_rel_range=1.5, max_outlier_reproj_px=45.0,
        )
        heights = [s.z_ft for s in (ba.samples if ba.samples else res.samples)]
        print(f"  tf{si}: {t0:.0f}-{t1s:.0f}ms n={len(pts)} dur={span:.2f}s "
              f"[fixed] status={res.status} reproj={res.reprojection_error_px:.1f} "
              f"| [BA] status={ba.status} reproj={ba.reprojection_error_px:.1f} "
              f"f1={ba.cam1.focal:.0f}/f2={ba.cam2.focal:.0f} "
              f"peak_z={max(heights) if heights else 0:.1f}")


if __name__ == "__main__":
    main()
