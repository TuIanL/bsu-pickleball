from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.metric_court_scene import MetricCourtSceneDraftRequest, NetProfileControlPoint, ScenePoint3D, SceneViewCalibration
from app.services.metric_court_scene_service import MetricCourtSceneService
from app.services.storage_service import StorageService
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition, load_canonical_court_frame, write_canonical_court_frame
from app.vision.multiview.metric_court_scene import (
    NET_CENTER_HEIGHT_FT,
    NET_ENDPOINT_HEIGHT_FT,
    build_standard_net_profile,
)


def _take_dir(tmp_path: Path) -> Path:
    path = tmp_path / "captures" / "2026-08-25" / "take-1"
    path.mkdir(parents=True)
    return path


def _draft_request() -> MetricCourtSceneDraftRequest:
    profile = build_standard_net_profile()
    profile = profile.model_copy(
        update={
            "control_points": [
                point.model_copy(update={"confirmed": True})
                for point in profile.control_points
            ]
        }
    )
    return MetricCourtSceneDraftRequest(
        canonical_frame_id="ccf_test",
        net_profile=profile,
        views=[SceneViewCalibration(
            view_id="cam_1",
            camera_id="camera-a",
            video_id="video-a",
            net_annotations={
                "left": {"x": 100, "y": 200},
                "center": {"x": 320, "y": 180},
                "right": {"x": 540, "y": 200},
            },
            holdout_annotations={
                "holdout_left_quarter": {"x": 210, "y": 190},
                "holdout_right_quarter": {"x": 430, "y": 190},
            },
        )],
        holdout_control_points=[
            NetProfileControlPoint(
                id="holdout_left_quarter",
                world=ScenePoint3D(x=5, y=22, z=2.9),
                image_by_view={"cam_1": {"x": 210, "y": 190}},
                provenance="manual_verified",
                confirmed=True,
            ),
            NetProfileControlPoint(
                id="holdout_right_quarter",
                world=ScenePoint3D(x=15, y=22, z=2.9),
                image_by_view={"cam_1": {"x": 430, "y": 190}},
                provenance="manual_verified",
                confirmed=True,
            ),
        ],
    )


def test_standard_net_profile_uses_project_heights() -> None:
    profile = build_standard_net_profile()

    assert profile.control_points[0].world.z == pytest.approx(NET_ENDPOINT_HEIGHT_FT)
    assert profile.control_points[1].world.z == pytest.approx(NET_CENTER_HEIGHT_FT)
    assert profile.control_points[-1].world.z == pytest.approx(NET_ENDPOINT_HEIGHT_FT)
    assert profile.sampled_top_profile[0].z == pytest.approx(NET_ENDPOINT_HEIGHT_FT)
    assert profile.sampled_top_profile[len(profile.sampled_top_profile) // 2].z == pytest.approx(NET_CENTER_HEIGHT_FT)


def test_scene_draft_validate_publish_and_list_revisions(tmp_path: Path) -> None:
    service = MetricCourtSceneService(StorageService())
    take_dir = _take_dir(tmp_path)

    draft = service.save_draft(take_dir, "take-1", _draft_request())
    assert draft.status == "draft"
    assert [point.id for point in draft.holdout_control_points] == ["holdout_left_quarter", "holdout_right_quarter"]
    assert draft.views[0].holdout_annotations["holdout_left_quarter"].x == 210
    assert service.get_draft(take_dir) is not None

    validation = service.validate(take_dir, "take-1")
    assert validation.status == "ready"
    assert validation.rejection_reasons == []

    published = service.publish(take_dir, "take-1")
    assert published.status == "ready"
    assert published.revision == 1
    current = service.get_current(take_dir)
    assert current is not None
    assert current.revision == 1
    assert len(current.holdout_control_points) == 2
    assert service.list_revisions(take_dir)[0].revision == 1

    # Publishing again creates a new immutable revision rather than rewriting
    # revision-1.json.
    service.save_draft(take_dir, "take-1", _draft_request())
    published_again = service.publish(take_dir, "take-1")
    assert published_again.revision == 2
    assert service.get_revision(take_dir, 1).revision == 1
    current = service.get_current(take_dir)
    assert current is not None
    assert current.revision == 2


def test_scene_validation_reports_missing_required_inputs(tmp_path: Path) -> None:
    service = MetricCourtSceneService(StorageService())
    take_dir = _take_dir(tmp_path)
    service.save_draft(
        take_dir,
        "take-1",
        MetricCourtSceneDraftRequest(canonical_frame_id=None, views=[]),
    )

    validation = service.validate(take_dir, "take-1")
    assert validation.status == "degraded"
    assert "no_views" in validation.rejection_reasons
    assert "canonical_frame_missing" in validation.rejection_reasons
    assert "net_controls_must_be_manually_confirmed" in validation.rejection_reasons


def test_scene_draft_reuses_the_actual_take_canonical_frame_id(tmp_path: Path) -> None:
    service = MetricCourtSceneService(StorageService())
    take_dir = _take_dir(tmp_path)
    canonical = CanonicalCourtFrameDefinition.create(
        "take-1",
        "north baseline",
        "south baseline",
        orientation_by_view={"cam_1": "identity", "cam_2": "rotate_180"},
    )
    write_canonical_court_frame(take_dir, canonical)

    draft = service.save_draft(
        take_dir,
        "take-1",
        _draft_request().model_copy(update={"canonical_frame_id": "capture-take:take-1"}),
    )

    assert draft.canonical_frame_id == canonical.frame_id
    assert load_canonical_court_frame(take_dir).frame_id == canonical.frame_id


def test_scene_draft_bootstraps_a_ccf_id_when_no_frame_exists(tmp_path: Path) -> None:
    service = MetricCourtSceneService(StorageService())
    take_dir = _take_dir(tmp_path)

    draft = service.save_draft(
        take_dir,
        "take-1",
        _draft_request().model_copy(update={"canonical_frame_id": "capture-take:take-1"}),
    )

    assert draft.canonical_frame_id is not None
    assert draft.canonical_frame_id.startswith("ccf_")
    assert load_canonical_court_frame(take_dir).frame_id == draft.canonical_frame_id


def test_historical_take_without_scene_assets_remains_read_only_compatible(tmp_path: Path) -> None:
    service = MetricCourtSceneService(StorageService())
    take_dir = _take_dir(tmp_path)

    assert service.get_current(take_dir) is None
    assert service.list_revisions(take_dir) == []

    with pytest.raises(FileNotFoundError):
        service.get_revision(take_dir, 1)
