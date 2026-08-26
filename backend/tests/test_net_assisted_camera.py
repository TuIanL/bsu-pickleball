from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.schemas.metric_court_scene import (
    MetricCourtSceneCalibration,
    NetProfile,
    NetProfileControlPoint,
    ScenePoint3D,
    SceneViewCalibration,
)
from app.vision.multiview.ball_stereo.net_assisted_camera import (
    evaluate_net_camera_quality,
    refine_virtual_camera_for_scene,
    refine_virtual_camera_with_net,
)
from app.vision.multiview.ball_stereo.virtual_camera import VirtualCameraResult


def _projection(focal: float, rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    return np.array([[focal, 0.0, 640.0], [0.0, focal, 360.0], [0.0, 0.0, 1.0]]) @ np.hstack(
        [rotation, translation.reshape(3, 1)]
    )


def _project(projection: np.ndarray, world: np.ndarray) -> np.ndarray:
    values = (projection @ np.column_stack([world, np.ones(len(world))]).T).T
    return values[:, :2] / values[:, 2:3]


@pytest.mark.skipif(
    pytest.importorskip("scipy", reason="net refinement requires scipy") is None,
    reason="scipy unavailable",
)
def test_net_assisted_refinement_uses_non_planar_height_constraints() -> None:
    true_rotation = np.eye(3)
    true_translation = np.array([0.5, -0.8, 38.0])
    true_projection = _projection(980.0, true_rotation, true_translation)
    court_world = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [20.0, 44.0, 0.0], [0.0, 44.0, 0.0]])
    net_world = np.array([[0.0, 22.0, 3.0], [5.0, 22.0, 2.9], [10.0, 22.0, 2.833333333], [15.0, 22.0, 2.9], [20.0, 22.0, 3.0]])
    court_image = _project(true_projection, court_world)
    net_image = _project(true_projection, net_world)
    holdout_world = np.array([[2.5, 22.0, 2.95], [17.5, 22.0, 2.95]])
    holdout_image = _project(true_projection, holdout_world)

    initial_rotation = np.eye(3)
    initial_translation = np.array([2.0, -1.5, 34.0])
    initial = VirtualCameraResult(
        view_id="cam_1",
        image_width=1280,
        image_height=720,
        focal_ft=860.0,
        rotation=initial_rotation,
        translation=initial_translation,
        projection=_projection(860.0, initial_rotation, initial_translation),
        reprojection_error_px=20.0,
        available=True,
        status="available",
    )

    refined = refine_virtual_camera_with_net(
        initial,
        court_world=court_world,
        court_image=court_image,
        net_world=net_world,
        net_image=net_image,
        holdout_world=holdout_world,
        holdout_image=holdout_image,
    )

    assert refined.available
    assert refined.source == "net_refined_virtual"
    assert refined.disambiguation["net_reprojection_error_px"] < 0.05
    assert refined.disambiguation["holdout_reprojection_error_px"] < 0.05
    quality = evaluate_net_camera_quality(refined)
    assert quality.status == "ready"
    assert quality.height_uncertainty_ft >= 0.02


@pytest.mark.skipif(
    pytest.importorskip("scipy", reason="net refinement requires scipy") is None,
    reason="scipy unavailable",
)
def test_legacy_endpoint_swap_also_swaps_quarter_holdout_annotations() -> None:
    true_rotation = np.eye(3)
    true_translation = np.array([0.5, -0.8, 38.0])
    true_projection = _projection(980.0, true_rotation, true_translation)
    court_world = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [20.0, 44.0, 0.0], [0.0, 44.0, 0.0]])
    net_world = np.array([[0.0, 22.0, 3.0], [10.0, 22.0, 2.833333333], [20.0, 22.0, 3.0]])
    holdout_world = np.array([[5.0, 22.0, 2.875], [15.0, 22.0, 2.875]])
    court_image = _project(true_projection, court_world)
    net_image = _project(true_projection, net_world)
    holdout_image = _project(true_projection, holdout_world)

    initial = VirtualCameraResult(
        view_id="cam_2",
        image_width=1280,
        image_height=720,
        focal_ft=860.0,
        rotation=np.eye(3),
        translation=np.array([2.0, -1.5, 34.0]),
        projection=_projection(860.0, np.eye(3), np.array([2.0, -1.5, 34.0])),
        reprojection_error_px=20.0,
        available=True,
        status="available",
    )
    scene = MetricCourtSceneCalibration(
        capture_take_id="take-1",
        status="ready",
        net_profile=NetProfile(control_points=[
            NetProfileControlPoint(id="left", world=ScenePoint3D(x=0, y=22, z=3), confirmed=True),
            NetProfileControlPoint(id="center", world=ScenePoint3D(x=10, y=22, z=2.833333333), confirmed=True),
            NetProfileControlPoint(id="right", world=ScenePoint3D(x=20, y=22, z=3), confirmed=True),
        ]),
        holdout_control_points=[
            NetProfileControlPoint(id="holdout_left_quarter", world=ScenePoint3D(x=5, y=22, z=2.875), confirmed=True),
            NetProfileControlPoint(id="holdout_right_quarter", world=ScenePoint3D(x=15, y=22, z=2.875), confirmed=True),
        ],
        # Legacy drafts stored canonical left/right labels in screen order.
        views=[SceneViewCalibration(
            view_id="cam_2",
            net_annotations={
                "left": {"x": net_image[2, 0], "y": net_image[2, 1]},
                "center": {"x": net_image[1, 0], "y": net_image[1, 1]},
                "right": {"x": net_image[0, 0], "y": net_image[0, 1]},
            },
            holdout_annotations={
                "holdout_left_quarter": {"x": holdout_image[1, 0], "y": holdout_image[1, 1]},
                "holdout_right_quarter": {"x": holdout_image[0, 0], "y": holdout_image[0, 1]},
            },
        )],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    refined = refine_virtual_camera_for_scene(
        initial,
        court_world=court_world,
        court_image=court_image,
        scene_calibration=scene,
        view_id="cam_2",
    )

    assert refined.disambiguation["net_annotation_mapping"] == "endpoint_swapped_legacy_compat"
    assert refined.disambiguation["holdout_reprojection_error_px"] < 0.05
