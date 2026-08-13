from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
from app.schemas.sync_anchor import SyncAnchor, SyncAnchorConfirmRequest, SyncAnchorDraftRequest
from app.schemas.video import VideoMetadata
from app.services.dual_camera_sync import build_dual_camera_sync_calibration
from app.services.sync_anchor_service import (
    ANCHORS_FILENAME,
    CALIBRATION_FILENAME,
    CONFIRMATION_FILENAME,
    SyncAnchorAssetService,
    SyncAnchorConflictError,
    SyncAnchorValidationError,
)


class _Query:
    def __init__(self, value: CaptureTake):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _Db:
    def __init__(self, take: CaptureTake):
        self.take = take

    def query(self, model):
        return _Query(self.take)


class _Videos:
    def __init__(self, values: dict[str, VideoMetadata | None]):
        self.values = values

    def get_video(self, video_id: str):
        return self.values.get(video_id)


def _take(tmp_path: Path, *, mode: CaptureMode = CaptureMode.dual) -> CaptureTake:
    session_dir = tmp_path / "take"
    (session_dir / "metadata").mkdir(parents=True)
    (session_dir / "timeline").mkdir()
    (session_dir / "metadata" / "recording_session.json").write_text(
        json.dumps(
            {
                "camera_slots": {
                    "cam_1": {"camera_id": "camera-a"},
                    "cam_2": {"camera_id": "camera-b"},
                },
                "registered_video_ids": {"cam_1": "video-a", "cam_2": "video-b"},
            }
        ),
        encoding="utf-8",
    )
    return CaptureTake(
        id="take-1",
        field_session_id="field-1",
        capture_mode=mode,
        source_session_type=SourceSessionType.sync_recording,
        source_session_id="sync-1",
        session_dir=str(session_dir),
        status=CaptureTakeStatus.completed,
    )


def _videos(tmp_path: Path) -> _Videos:
    values: dict[str, VideoMetadata] = {}
    for video_id, suffix in (("video-a", "a"), ("video-b", "b")):
        media = tmp_path / f"media-{suffix}.mp4"
        media.write_bytes(b"media-" + suffix.encode())
        sidecar = Path(f"{media}.pts.jsonl")
        sidecar.write_text(
            "\n".join(
                json.dumps({"frame_index": index, "pts_seconds": float(index * 50)})
                for index in range(3)
            )
            + "\n",
            encoding="utf-8",
        )
        values[video_id] = VideoMetadata(
            id=video_id,
            original_filename=f"{video_id}.mp4",
            content_type="video/mp4",
            size_bytes=media.stat().st_size,
            path=str(media),
            source="recording",
            uploaded_at=datetime.now(UTC),
        )
    return _Videos(values)


def _service(tmp_path: Path, *, mode: CaptureMode = CaptureMode.dual):
    take = _take(tmp_path, mode=mode)
    return take, SyncAnchorAssetService(_Db(take), video_service=_videos(tmp_path))


def _anchors() -> list[SyncAnchor]:
    return [
        SyncAnchor(id="a1", label="start", pts_by_camera={"camera-a": 10.0, "camera-b": 10.1}),
        SyncAnchor(id="a2", label="middle", pts_by_camera={"camera-a": 40.0, "camera-b": 40.1}),
        SyncAnchor(id="a3", label="end", pts_by_camera={"camera-a": 70.0, "camera-b": 70.1}),
    ]


def _draft(revision: int = 0, anchors: list[SyncAnchor] | None = None) -> SyncAnchorDraftRequest:
    return SyncAnchorDraftRequest(
        reference_camera="camera-a",
        cameras=["camera-a", "camera-b"],
        anchors=anchors or _anchors(),
        expected_revision=revision,
    )


def _confirm(revision: int = 0, anchors: list[SyncAnchor] | None = None, **overrides):
    payload = _draft(revision, anchors).model_dump()
    payload.update(overrides)
    return SyncAnchorConfirmRequest.model_validate(payload)


def test_confirm_publishes_versioned_assets_and_reuses_revision(tmp_path):
    take, service = _service(tmp_path)

    revision, draft_status = service.save_draft(take.id, _draft())
    result = service.confirm(take.id, _confirm(revision))
    status = result["status"]
    timeline = Path(take.session_dir) / "timeline"

    assert revision == 1
    assert draft_status.state == "draft"
    assert status.state == "confirmed"
    assert status.analysis_allowed is True
    assert status.source == "manual_anchors"
    assert status.revision == 1
    assert status.quality is not None
    assert status.quality.coverage_ratio >= 0.5
    assert (timeline / ANCHORS_FILENAME).exists()
    assert (timeline / CALIBRATION_FILENAME).exists()
    assert (timeline / CONFIRMATION_FILENAME).exists()
    assert (timeline / "sync_anchor_history" / "revision-1" / CONFIRMATION_FILENAME).exists()

    second = service.status(take.id)
    assert second.state == "confirmed"
    assert second.revision == status.revision


def test_revision_conflict_does_not_overwrite_draft(tmp_path):
    take, service = _service(tmp_path)
    service.save_draft(take.id, _draft())

    with pytest.raises(SyncAnchorConflictError) as error:
        service.save_draft(take.id, _draft(0))

    assert error.value.current_revision == 1
    assert service.status(take.id).revision == 1


@pytest.mark.parametrize(
    ("anchors", "overrides", "expected_code"),
    [
        (_anchors()[:2], {}, "anchor_validation"),
        (_anchors(), {"cameras": ["camera-a", "other-camera"]}, "camera_identity_mismatch"),
        (_anchors(), {"reference_camera": "other-camera"}, "reference_camera_mismatch"),
        (
            [
                SyncAnchor(id="a1", pts_by_camera={"camera-a": 1.0, "camera-b": 1.1}),
                SyncAnchor(id="a2", pts_by_camera={"camera-a": 2.0, "camera-b": 2.1}),
                SyncAnchor(id="a3", pts_by_camera={"camera-a": 3.0, "camera-b": 3.1}),
            ],
            {},
            "coverage_threshold",
        ),
    ],
)
def test_confirm_rejects_structured_validation_failures(tmp_path, anchors, overrides, expected_code):
    take, service = _service(tmp_path)

    with pytest.raises(SyncAnchorValidationError) as error:
        service.confirm(take.id, _confirm(anchors=anchors, **overrides))

    assert expected_code in {issue.code for issue in error.value.issues}
    assert service.status(take.id).state == "required"


def test_auto_degraded_and_single_camera_policy_states(tmp_path):
    take, service = _service(tmp_path)
    timeline = Path(take.session_dir) / "timeline"
    calibration = {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": "camera-a",
        "source": "auto_degraded_from_recording_timing",
        "mappings": {},
    }
    (timeline / CALIBRATION_FILENAME).write_text(json.dumps(calibration), encoding="utf-8")

    assert service.status(take.id).state == "auto_degraded"
    assert service.status(take.id, require_manual=True).analysis_allowed is False

    single_take, single_service = _service(tmp_path / "single", mode=CaptureMode.single)
    single_status = single_service.status(single_take.id, require_manual=True)
    assert single_status.state == "not_required"
    assert single_status.analysis_allowed is True


def test_provenance_change_invalidates_confirmation_but_keeps_history(tmp_path):
    take, service = _service(tmp_path)
    revision, _ = service.save_draft(take.id, _draft())
    service.confirm(take.id, _confirm(revision))
    media = tmp_path / "media-b.mp4"
    media.write_bytes(b"replacement-media-with-a-different-size")

    status = service.status(take.id)
    assert status.state == "invalidated"
    assert status.analysis_allowed is False
    assert status.revision == 1
    assert (Path(take.session_dir) / "timeline" / "sync_anchor_history" / "revision-1").is_dir()


def test_legacy_manual_anchors_are_lazy_migrated_only_with_matching_provenance(tmp_path):
    take, service = _service(tmp_path)
    current = service.current_provenance(take.id)
    provenance = [item.model_dump(mode="json") for item in current]
    payload = {
        "reference_camera": "camera-a",
        "cameras": ["camera-a", "camera-b"],
        "anchors": [anchor.pts_by_camera for anchor in _anchors()],
        "provenance": provenance,
    }
    calibration = build_dual_camera_sync_calibration(payload)
    calibration.update({"revision": 7, "provenance": provenance})
    timeline = Path(take.session_dir) / "timeline"
    (timeline / CALIBRATION_FILENAME).write_text(json.dumps(calibration), encoding="utf-8")
    (timeline / "manual_anchors.json").write_text(json.dumps(payload), encoding="utf-8")

    status = service.status(take.id)
    assert status.state == "confirmed"
    assert status.revision == 7
    confirmation = json.loads((timeline / CONFIRMATION_FILENAME).read_text(encoding="utf-8"))
    assert confirmation["migration"] == "legacy_manual_anchors"


def test_missing_video_does_not_fingerprint_current_directory(tmp_path):
    take = _take(tmp_path)
    service = SyncAnchorAssetService(_Db(take), video_service=_Videos({"video-a": None, "video-b": None}))

    provenance = service.current_provenance(take.id)

    assert len(provenance) == 2
    assert provenance[0].media_identity["path"] is None
    assert provenance[0].media_identity["exists"] is False
    assert provenance[0].timing_sidecar_identity["path"] is None
