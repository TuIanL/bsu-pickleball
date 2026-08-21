"""Court-constrained virtual camera（球 3D：虚拟相机分解）。

D2：不做真实内参标定。由球场平面 Homography（court→image 方向，即 inverse_homography）
在 pinhole 假设（cx/cy=中心、fx=fy=f、skew=0）下，用 `cv2.decomposeHomographyMat`
解出近似外参 (R,t)，得到 P_virtual = K[R|t]。焦距通过网格搜索最小化角点回投误差求取，
比闭式正交约束更稳健（透视畸变相机下闭式解不可靠）。

坐标系：H 作用的 court 平面是 **local camera court frame**（inverse_homography 的既定语义）。
为满足"统一 CanonicalCourt3DFrame"硬不变量，分解在每个视角的 local 帧进行后，
调用方通过 `orientation`（canonical→local）把所有视角的 XYZ 统一到 canonical 帧再联合三角测量；
本模块在 identity orientation 下投影即 canonical 帧坐标。

姿态消歧门：corner 在相机前方（相机 z_cam>0）/ R 近正交 vs 前方性冲突；
不满足 → virtual_camera_status=unavailable（调用方据此降级 LANDING_ONLY）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class VirtualCameraResult:
    """一次虚拟相机解算结果（失败时 available=False）。"""

    view_id: str
    image_width: int
    image_height: int
    focal_ft: float
    rotation: np.ndarray  # 3x3 R（local/被统一 canonical court frame → camera frame）
    translation: np.ndarray  # 3，camera 坐标系下世界原点位置
    projection: np.ndarray  # 3x4 P = K[R|t]，世界 (x,y,z=0) → 图像
    reprojection_error_px: float
    available: bool = False
    status: str = "unavailable"  # available / unavailable
    source: str = "homography_constrained_virtual"
    approximate: bool = True
    disambiguation: dict = field(default_factory=dict)

    def project_xy(self, x: float, y: float) -> tuple[float, float]:
        """把世界 (x,y)（z=0）投影到图像（px）。"""
        return self.project_xyz(x, y, 0.0)

    def project_xyz(self, x: float, y: float, z: float) -> tuple[float, float]:
        h = self.projection @ np.array([x, y, z, 1.0])
        w = float(h[2])
        if abs(w) < 1e-9:
            raise ValueError("virtual camera projection degenerates at w~0")
        return float(h[0] / w), float(h[1] / w)

    def point_in_front(self, x: float, y: float, z: float) -> bool:
        """世界 3D 点是否位于相机前方（相机 z_cam > 0）。"""
        cdepth = self.rotation[2, 0] * x + self.rotation[2, 1] * y + self.rotation[2, 2] * z + self.translation[2]
        return float(cdepth) > 0


def _reproj_and_infront(
    rotation: np.ndarray,
    translation: np.ndarray,
    focal: float,
    cx: float,
    cy: float,
    local_pts: np.ndarray,
    img_pts: np.ndarray,
) -> tuple[float, float]:
    """返回 (回投误差 px, 最小相机深度)。"""
    if len(local_pts) == 0:
        return math.inf, math.inf
    k = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]])
    proj = k @ np.hstack([rotation, translation.reshape(3, 1)])
    xyz = np.hstack([local_pts, np.zeros((len(local_pts), 1))])
    cam = (rotation @ xyz.T).T + translation
    depth = cam[:, 2]
    z_safe = np.where(np.abs(depth) < 1e-9, 1e-9, depth)
    u = focal * cam[:, 0] / z_safe + cx
    v = focal * cam[:, 1] / z_safe + cy
    err = float(np.mean(np.hypot(u - img_pts[:, 0], v - img_pts[:, 1])))
    return err, float(depth.min())


def _decompose_for_focal(
    h: np.ndarray,
    focal: float,
    cx: float,
    cy: float,
    local_pts: np.ndarray,
    img_pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float] | None:
    """对给定焦距，由 H=K[r1 r2 t] 闭式构造 pose。

    r1 = normalize(K^-1 h1)，r2 = normalize(K^-1 h2)，r3 = r1×r2，
    t = K^-1 h3 / λ（λ=|K^-1 h1|）。此构造使 R 恒正交；焦距只影响 t 尺度与回投。
    返回 (R, t, 回投误差, 焦距)。若角点不在相机前方则返回 None。
    """
    kinv = np.array([[1.0 / focal, 0.0, -cx / focal],
                     [0.0, 1.0 / focal, -cy / focal],
                     [0.0, 0.0, 1.0]])
    r1 = kinv @ h[:, 0]
    r2 = kinv @ h[:, 1]
    n1 = float(np.linalg.norm(r1))
    n2 = float(np.linalg.norm(r2))
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    lamb = (n1 + n2) / 2.0
    r1 = r1 / lamb
    r2 = r2 / lamb
    r3 = np.cross(r1, r2)
    rotation = np.stack([r1, r2, r3], axis=1)
    translation = kinv @ h[:, 2] / lamb
    if float(np.linalg.det(rotation)) < 0:
        rotation = -rotation
        translation = -translation
    ortho_err = float(np.max(np.abs(rotation.T @ rotation - np.eye(3))))
    if ortho_err > 0.2:
        return None  # 非近正交 → 焦距不匹配（正确焦距下 r1,r2 才正交）
    err, min_depth = _reproj_and_infront(rotation, translation, focal, cx, cy, local_pts, img_pts)
    if min_depth <= 1e-3:
        return None  # 前方性消歧：角点必须在相机前方（留一个极小正余量拒绝退化）
    return rotation, translation, err, focal


def _orientation_matrix(orientation: object) -> np.ndarray:
    """CourtOrientation 的 canonical→local 2D 仿射（z=0 平面）扩展成 3x3。"""
    name = getattr(orientation, "value", orientation)
    if name == "identity":
        return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    if name == "rotate_180":
        return np.array([[-1.0, 0.0, 20.0], [0.0, -1.0, 44.0], [0.0, 0.0, 1.0]])
    if name == "mirror_x":
        return np.array([[-1.0, 0.0, 20.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    if name == "mirror_y":
        return np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 44.0], [0.0, 0.0, 1.0]])
    raise ValueError(f"unsupported court orientation: {name}")


def decompose_virtual_camera(
    *,
    view_id: str,
    inverse_homography: Sequence[Sequence[float]],
    image_width: int,
    image_height: int,
    orientation: object,  # CourtOrientation（canonical → local）
    corner_canonical: Sequence[Sequence[float]] | None = None,
    corner_image: Sequence[Sequence[float]] | None = None,
    focal_min: float | None = None,
    focal_max: float | None = None,
) -> VirtualCameraResult:
    """由 court→image 方向的 H 解算近似虚拟相机（焦距网格搜索 + 前方性消歧）。

    D2 hard invariant：把 orientation 合成进 Homography（H_canon = H @ M_orientation），
    用 canonical 四角直接分解，使 Cam1/Cam2 的 P_virtual 落在**同一 CanonicalCourt3DFrame**，
    避免"一台把 y=0 当近端、另一台当远端"导致的联合三角测量错误。
    """
    h = np.asarray(inverse_homography, dtype=float)
    if h.shape != (3, 3):
        raise ValueError("inverse_homography must be 3x3")
    cx = image_width / 2.0
    cy = image_height / 2.0
    h /= h[2, 2]
    # canonical → local → image 合成：世界点用 canonical 坐标，H_canon 作用其上
    m_orient = _orientation_matrix(orientation)
    h_canon = (h @ m_orient) / (h @ m_orient)[2, 2]

    world_pts = None
    img_pts = None
    if corner_canonical is not None and corner_image is not None and len(corner_canonical) >= 3:
        world_pts = np.asarray(corner_canonical, dtype=float)
        img_pts = np.asarray(corner_image, dtype=float)

    worst = VirtualCameraResult(
        view_id=view_id, image_width=image_width, image_height=image_height,
        focal_ft=0.0, rotation=np.zeros((3, 3)), translation=np.zeros(3),
        projection=np.zeros((3, 4)), reprojection_error_px=math.inf,
        available=False, status="unavailable", disambiguation={"reason": "focal_decomposition_failed"},
    )

    if world_pts is None or img_pts is None:
        return worst

    f_min = focal_min if focal_min is not None else max(100.0, image_width * 0.5 * 1.0)
    f_max = focal_max if focal_max is not None else max(1000.0, image_width * 4.0)
    fl = np.geomspace(f_min, f_max, num=48)

    best = None
    best_err = math.inf
    for f in fl:
        cand = _decompose_for_focal(h_canon, float(f), cx, cy, world_pts, img_pts)
        if cand is None:
            continue
        _r, _t, err, _f = cand
        if err < best_err:
            best_err = err
            best = cand

    if best is None:
        return worst

    rotation, translation, reproj, focal = best
    ortho_err = float(np.max(np.abs(rotation.T @ rotation - np.eye(3))))
    projection = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]]) @ np.hstack(
        [rotation, translation.reshape(3, 1)]
    )

    if best_err > 1e6:
        return worst  # 回投离谱，判定失败

    # 姿态消歧门（R 近正交 + 前方性已在分解阶段强制）
    if ortho_err > 0.2:
        return VirtualCameraResult(
            view_id=view_id, image_width=image_width, image_height=image_height,
            focal_ft=focal, rotation=rotation, translation=translation,
            projection=projection, reprojection_error_px=reproj,
            available=False, status="unavailable",
            disambiguation={"reason": f"rotation_not_orthogonal_{ortho_err:.3f}"},
        )

    return VirtualCameraResult(
        view_id=view_id, image_width=image_width, image_height=image_height,
        focal_ft=focal, rotation=rotation, translation=translation,
        projection=projection, reprojection_error_px=reproj,
        available=True, status="available",
        disambiguation={"det_R": float(np.linalg.det(rotation)), "reprojection_error_px": reproj},
    )