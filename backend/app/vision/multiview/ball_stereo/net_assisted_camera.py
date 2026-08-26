"""Net-assisted refinement for the CaptureTake metric scene.

The court homography remains the deterministic initial estimate.  When the
manual net controls are available, this module fits the same pinhole camera
against both the ground-plane court points and non-planar net points.  The
principal point stays at the image centre, ``fx == fy`` and distortion is not
introduced, so the result remains compatible with the existing virtual-camera
and stereo code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .virtual_camera import VirtualCameraResult

try:
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation
except ImportError:  # pragma: no cover - the backend runtime normally bundles scipy
    least_squares = None
    Rotation = None


@dataclass(frozen=True)
class NetCameraQuality:
    status: str
    court_reprojection_error_px: float
    net_reprojection_error_px: float
    holdout_reprojection_error_px: float | None
    height_uncertainty_ft: float | None
    rejection_reasons: tuple[str, ...] = ()


def _as_world(points: Sequence[Sequence[float]], *, z: float = 0.0, minimum: int = 3) -> np.ndarray:
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[1] not in (2, 3):
        raise ValueError("world points must be an N x 2 or N x 3 array")
    if values.shape[1] == 2:
        values = np.column_stack([values, np.full(len(values), z, dtype=float)])
    if len(values) < minimum or not np.isfinite(values).all():
        raise ValueError(f"world points must contain at least {minimum} finite points")
    return values


def _as_image(points: Sequence[Sequence[float]], *, minimum: int = 3) -> np.ndarray:
    values = np.asarray(points, dtype=float)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < minimum or not np.isfinite(values).all():
        raise ValueError(f"image points must be an N x 2 array with at least {minimum} finite points")
    return values


def _normalized_dlt_projection(world: np.ndarray, image: np.ndarray) -> np.ndarray:
    """Fit a general projective camera for real footage that violates the pinhole prior.

    The primary solver intentionally keeps the product camera model constrained.  Real
    wide-angle capture can still have enough consistent 3D control points for a stable
    projective fit even when that constrained optimizer lands in a bad local minimum.
    Normalized DLT is used only as an explicit, quality-gated fallback.
    """
    world_centroid = np.mean(world, axis=0)
    world_delta = world - world_centroid
    world_scale = np.sqrt(3.0) / max(float(np.mean(np.linalg.norm(world_delta, axis=1))), 1e-9)
    world_transform = np.eye(4, dtype=float)
    world_transform[:3, :3] *= world_scale
    world_transform[:3, 3] = -world_scale * world_centroid
    normalized_world = (world_transform @ np.column_stack([world, np.ones(len(world))]).T).T

    image_centroid = np.mean(image, axis=0)
    image_delta = image - image_centroid
    image_scale = np.sqrt(2.0) / max(float(np.mean(np.linalg.norm(image_delta, axis=1))), 1e-9)
    image_transform = np.array(
        [
            [image_scale, 0.0, -image_scale * image_centroid[0]],
            [0.0, image_scale, -image_scale * image_centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    normalized_image = (image_transform @ np.column_stack([image, np.ones(len(image))]).T).T

    rows: list[np.ndarray] = []
    for point, projected in zip(normalized_world, normalized_image, strict=True):
        x, y, z, w = point
        u, v, image_w = projected
        rows.append(np.array([0.0, 0.0, 0.0, 0.0, -image_w * x, -image_w * y, -image_w * z, -image_w * w, v * x, v * y, v * z, v * w]))
        rows.append(np.array([image_w * x, image_w * y, image_w * z, image_w * w, 0.0, 0.0, 0.0, 0.0, -u * x, -u * y, -u * z, -u * w]))
    _, _, vh = np.linalg.svd(np.asarray(rows, dtype=float))
    normalized_projection = vh[-1].reshape(3, 4)
    return np.linalg.inv(image_transform) @ normalized_projection @ world_transform


def _project_with_matrix(projection: np.ndarray, world: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = (projection @ np.column_stack([world, np.ones(len(world))]).T).T
    depth = homogeneous[:, 2]
    safe_depth = np.where(np.abs(depth) > 1e-9, depth, np.nan)
    image = homogeneous[:, :2] / safe_depth[:, None]
    return image, depth


def _project(rotation: np.ndarray, translation: np.ndarray, focal_px: float, width: int, height: int, world: np.ndarray) -> np.ndarray:
    camera = (rotation @ world.T).T + translation
    if np.any(camera[:, 2] <= 1e-6):
        # Keep the optimizer finite while making behind-camera candidates expensive.
        depth = np.maximum(np.abs(camera[:, 2]), 1e-6)
    else:
        depth = camera[:, 2]
    return np.column_stack([
        focal_px * camera[:, 0] / depth + width / 2.0,
        focal_px * camera[:, 1] / depth + height / 2.0,
    ])


def _residuals(
    params: np.ndarray,
    *,
    width: int,
    height: int,
    court_world: np.ndarray,
    court_image: np.ndarray,
    net_world: np.ndarray,
    net_image: np.ndarray,
) -> np.ndarray:
    focal_px = float(np.exp(params[0]))
    rotation = Rotation.from_rotvec(params[1:4]).as_matrix()
    translation = params[4:7]
    court_error = (_project(rotation, translation, focal_px, width, height, court_world) - court_image).reshape(-1)
    net_error = (_project(rotation, translation, focal_px, width, height, net_world) - net_image).reshape(-1)
    # Slightly emphasize the non-planar net constraints: they are what
    # identifies height while the court points preserve the original frame.
    return np.concatenate([court_error, 1.5 * net_error])


def _error_px(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(predicted - observed, axis=1))) if len(observed) else math.inf


def refine_virtual_camera_with_net(
    initial: VirtualCameraResult,
    *,
    court_world: Sequence[Sequence[float]],
    court_image: Sequence[Sequence[float]],
    net_world: Sequence[Sequence[float]],
    net_image: Sequence[Sequence[float]],
    holdout_world: Sequence[Sequence[float]] | None = None,
    holdout_image: Sequence[Sequence[float]] | None = None,
    max_nfev: int = 300,
) -> VirtualCameraResult:
    """Refine an initial virtual camera using court and non-planar net points."""
    if not initial.available:
        return initial
    if least_squares is None or Rotation is None:
        return initial

    court_xyz = _as_world(court_world)
    court_uv = _as_image(court_image)
    net_xyz = _as_world(net_world)
    net_uv = _as_image(net_image)
    if len(court_xyz) != len(court_uv) or len(net_xyz) != len(net_uv):
        raise ValueError("world/image point counts must match")

    initial_focal = max(float(initial.focal_ft), 1.0)
    params = np.concatenate([
        [math.log(initial_focal)],
        Rotation.from_matrix(np.asarray(initial.rotation, dtype=float)).as_rotvec(),
        np.asarray(initial.translation, dtype=float),
    ])
    result = least_squares(
        lambda values: _residuals(
            values,
            width=initial.image_width,
            height=initial.image_height,
            court_world=court_xyz,
            court_image=court_uv,
            net_world=net_xyz,
            net_image=net_uv,
        ),
        params,
        bounds=(
            np.array([math.log(max(50.0, initial.image_width * 0.2)), -math.inf, -math.inf, -math.inf, -1e4, -1e4, -1e4]),
            np.array([math.log(max(100.0, initial.image_width * 12.0)), math.inf, math.inf, math.inf, 1e4, 1e4, 1e4]),
        ),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=max_nfev,
    )
    focal_px = float(np.exp(result.x[0]))
    rotation = Rotation.from_rotvec(result.x[1:4]).as_matrix()
    translation = result.x[4:7]
    projection = np.array([
        [focal_px, 0.0, initial.image_width / 2.0],
        [0.0, focal_px, initial.image_height / 2.0],
        [0.0, 0.0, 1.0],
    ]) @ np.hstack([rotation, translation.reshape(3, 1)])

    court_pred = _project(rotation, translation, focal_px, initial.image_width, initial.image_height, court_xyz)
    net_pred = _project(rotation, translation, focal_px, initial.image_width, initial.image_height, net_xyz)
    holdout_error = None
    if holdout_world is not None and holdout_image is not None:
        holdout_xyz = _as_world(holdout_world, minimum=1)
        holdout_uv = _as_image(holdout_image, minimum=1)
        if len(holdout_xyz) != len(holdout_uv):
            raise ValueError("holdout world/image point counts must match")
        holdout_error = _error_px(
            _project(rotation, translation, focal_px, initial.image_width, initial.image_height, holdout_xyz),
            holdout_uv,
        )

    all_world = np.vstack([court_xyz, net_xyz])
    camera_depth = (rotation @ all_world.T).T[:, 2] + 0.0
    # Translation is world→camera; preserve the same front-of-camera gate as
    # the homography solver.
    camera_depth = (rotation @ all_world.T).T[:, 2] + translation[2]
    available = bool(result.success and np.isfinite(projection).all() and np.min(camera_depth) > 1e-5)
    combined_error = float(np.mean(np.linalg.norm(np.vstack([court_pred - court_uv, net_pred - net_uv]), axis=1)))
    if combined_error > 100.0:
        available = False
    uncertainty = max(0.02, combined_error / max(focal_px, 1.0) * 10.0)

    refined = VirtualCameraResult(
        view_id=initial.view_id,
        image_width=initial.image_width,
        image_height=initial.image_height,
        focal_ft=focal_px,
        rotation=rotation,
        translation=translation,
        projection=projection,
        reprojection_error_px=combined_error,
        available=available,
        status="available" if available else "unavailable",
        source="net_refined_virtual",
        approximate=False,
        disambiguation={
            **initial.disambiguation,
            "refinement_success": bool(result.success),
            "court_reprojection_error_px": _error_px(court_pred, court_uv),
            "net_reprojection_error_px": _error_px(net_pred, net_uv),
            "holdout_reprojection_error_px": holdout_error,
            "height_uncertainty_ft": uncertainty,
        },
    )
    if refined.available:
        return refined

    # Real camera lenses can make the strict K[R|t] model fail even when the court
    # and net annotations are mutually consistent.  Keep that failure visible, but
    # allow a normalized projective fit when all controls remain well-conditioned.
    try:
        all_world = np.vstack([court_xyz, net_xyz])
        all_image = np.vstack([court_uv, net_uv])
        projection_dlt = _normalized_dlt_projection(all_world, all_image)
        predicted, depth = _project_with_matrix(projection_dlt, all_world)
        if np.nanmedian(depth) < 0.0:
            projection_dlt = -projection_dlt
            predicted, depth = _project_with_matrix(projection_dlt, all_world)
        residual = np.linalg.norm(predicted - all_image, axis=1)
        court_error_dlt = float(np.mean(residual[: len(court_xyz)]))
        net_error_dlt = float(np.mean(residual[len(court_xyz) :]))
        combined_error_dlt = float(np.mean(residual))
        if (
            not np.isfinite(projection_dlt).all()
            or not np.isfinite(residual).all()
            or np.any(depth <= 1e-5)
            or combined_error_dlt > 25.0
            or float(np.max(residual)) > 50.0
        ):
            return refined

        holdout_error_dlt = None
        if holdout_world is not None and holdout_image is not None:
            holdout_xyz = _as_world(holdout_world, minimum=1)
            holdout_uv = _as_image(holdout_image, minimum=1)
            holdout_predicted, holdout_depth = _project_with_matrix(projection_dlt, holdout_xyz)
            if len(holdout_xyz) != len(holdout_uv) or np.any(holdout_depth <= 1e-5):
                return refined
            holdout_error_dlt = _error_px(holdout_predicted, holdout_uv)

        return VirtualCameraResult(
            view_id=initial.view_id,
            image_width=initial.image_width,
            image_height=initial.image_height,
            focal_ft=initial.focal_ft,
            rotation=initial.rotation,
            translation=initial.translation,
            projection=projection_dlt,
            reprojection_error_px=combined_error_dlt,
            available=True,
            status="available",
            source="net_refined_virtual",
            # A normalized projective camera is useful for approximate 3D
            # projection, but it does not satisfy the metric K[R|t] gate.
            # Keep it explicit so callers cannot promote it to metric height.
            approximate=True,
            disambiguation={
                **initial.disambiguation,
                "solver": "normalized_dlt_fallback",
                "metric_qualified": False,
                "refinement_success": bool(result.success),
                "court_reprojection_error_px": court_error_dlt,
                "net_reprojection_error_px": net_error_dlt,
                "holdout_reprojection_error_px": holdout_error_dlt,
                "height_uncertainty_ft": None,
                "height_uncertainty_source": "projective_fallback_not_metric",
            },
        )
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return refined


def refine_virtual_camera_for_scene(
    initial: VirtualCameraResult,
    *,
    court_world: Sequence[Sequence[float]],
    court_image: Sequence[Sequence[float]],
    scene_calibration: object,
    view_id: str,
    court_orientation: object | None = None,
) -> VirtualCameraResult:
    """Refine one camera from a persisted scene revision.

    The first manual UI stored endpoint labels in screen order.  The scene
    contract stores endpoint world coordinates in canonical order, so both
    endpoint assignments are evaluated and the quality-gated best one wins.
    This keeps historical drafts readable while newer canonical annotations
    use the direct assignment.
    """
    if not initial.available:
        return initial
    scene_views = getattr(scene_calibration, "views", []) or []
    scene_view = next((view for view in scene_views if getattr(view, "view_id", None) == view_id), None)
    controls = list(getattr(getattr(scene_calibration, "net_profile", None), "control_points", []) or [])
    controls_by_id = {str(getattr(control, "id", "")): control for control in controls}
    ordered_controls = [controls_by_id.get(control_id) for control_id in ("left", "center", "right")]
    if scene_view is None or any(control is None for control in ordered_controls):
        return initial

    annotations: dict[str, object | None] = {}
    for control_id in ("left", "center", "right"):
        control = controls_by_id[control_id]
        image_by_view = getattr(control, "image_by_view", {}) or {}
        image = image_by_view.get(view_id)
        if image is None:
            image = (getattr(scene_view, "net_annotations", {}) or {}).get(control_id)
        annotations[control_id] = image
    if any(image is None for image in annotations.values()):
        return initial

    holdout_points: list[tuple[str, list[float], list[float]]] = []
    holdout_controls = list(getattr(scene_calibration, "holdout_control_points", []) or [])
    for control in holdout_controls:
        image_by_view = getattr(control, "image_by_view", {}) or {}
        image = image_by_view.get(view_id)
        if image is None:
            image = (getattr(scene_view, "holdout_annotations", {}) or {}).get(str(getattr(control, "id", "")))
        world = getattr(control, "world", None)
        if image is None or world is None:
            continue
        holdout_points.append(
            (
                str(getattr(control, "id", "")),
                [float(world.x), float(world.y), float(world.z)],
                [float(image.x), float(image.y)],
            )
        )

    candidates: list[tuple[str, VirtualCameraResult]] = []
    holdout_image_by_id = {point_id: image for point_id, _world, image in holdout_points}
    legacy_holdout_mirror = {
        "holdout_left_quarter": "holdout_right_quarter",
        "holdout_right_quarter": "holdout_left_quarter",
    }
    for mapping_name, image_ids in (
        ("direct", ("left", "center", "right")),
        ("endpoint_swapped_legacy_compat", ("right", "center", "left")),
    ):
        net_world = [
            [float(getattr(control, "world").x), float(getattr(control, "world").y), float(getattr(control, "world").z)]
            for control in ordered_controls
        ]
        net_image = [
            [float(getattr(annotations[image_id], "x")), float(getattr(annotations[image_id], "y"))]
            for image_id in image_ids
        ]
        holdout_world = [world for _point_id, world, _image in holdout_points]
        holdout_image = [
            holdout_image_by_id.get(legacy_holdout_mirror.get(point_id, point_id), image)
            if mapping_name == "endpoint_swapped_legacy_compat"
            else image
            for point_id, _world, image in holdout_points
        ]
        refined = refine_virtual_camera_with_net(
            initial,
            court_world=court_world,
            court_image=court_image,
            net_world=net_world,
            net_image=net_image,
            holdout_world=holdout_world or None,
            holdout_image=holdout_image or None,
        )
        if refined.available and refined.source == "net_refined_virtual":
            quality = evaluate_net_camera_quality(refined, require_holdout=True)
            refined.disambiguation.update(
                {
                    "quality_status": quality.status,
                    "quality_rejection_reasons": list(quality.rejection_reasons),
                    "metric_qualified": quality.status == "ready" and not refined.approximate,
                    "height_uncertainty_ft": quality.height_uncertainty_ft,
                }
            )
            candidates.append((mapping_name, refined))

    if not candidates:
        return initial

    def candidate_key(item: tuple[str, VirtualCameraResult]) -> tuple[int, float]:
        _mapping, camera = item
        return (
            int(not camera.approximate and bool(camera.disambiguation.get("metric_qualified", True))),
            -float(camera.reprojection_error_px),
        )

    mapping_name, refined = max(candidates, key=candidate_key)
    refined.disambiguation["net_annotation_mapping"] = mapping_name
    if court_orientation is not None:
        refined.disambiguation["court_orientation"] = str(getattr(court_orientation, "value", court_orientation))
    return refined


def evaluate_net_camera_quality(
    camera: VirtualCameraResult,
    *,
    min_ray_angle_deg: float = 1.0,
    max_court_error_px: float = 8.0,
    max_net_error_px: float = 8.0,
    max_holdout_error_px: float = 12.0,
    require_holdout: bool = False,
) -> NetCameraQuality:
    """Map refinement diagnostics to a structured ready/degraded/invalidated gate."""
    details = camera.disambiguation
    court_error = float(details.get("court_reprojection_error_px", camera.reprojection_error_px))
    net_error = float(details.get("net_reprojection_error_px", math.inf))
    holdout = details.get("holdout_reprojection_error_px")
    holdout_error = float(holdout) if holdout is not None else None
    raw_uncertainty = details.get("height_uncertainty_ft")
    uncertainty = (
        float(raw_uncertainty)
        if isinstance(raw_uncertainty, (int, float)) and math.isfinite(float(raw_uncertainty))
        else math.inf
    )
    reasons: list[str] = []
    if not camera.available:
        reasons.append("camera_refinement_unavailable")
    if court_error > max_court_error_px:
        reasons.append("court_reprojection_error_high")
    if net_error > max_net_error_px:
        reasons.append("net_reprojection_error_high")
    if holdout_error is not None and holdout_error > max_holdout_error_px:
        reasons.append("holdout_reprojection_error_high")
    if require_holdout and holdout_error is None:
        reasons.append("holdout_control_points_missing")
    if not math.isfinite(uncertainty):
        reasons.append("height_uncertainty_missing")
    if camera.approximate:
        reasons.append("camera_model_approximate")
    if camera.disambiguation.get("ray_angle_deg") is not None and float(camera.disambiguation["ray_angle_deg"]) < min_ray_angle_deg:
        reasons.append("ray_angle_too_small")
    if reasons:
        status = "invalidated" if not camera.available or "net_reprojection_error_high" in reasons else "degraded"
    else:
        status = "ready"
    return NetCameraQuality(status, court_error, net_error, holdout_error, uncertainty, tuple(reasons))
