from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes_vidat import create_package, list_packages
from app.database import Base
from app.models.capture_coding_action import CaptureCodingAction
from app.models.capture_segment import CaptureSegment
from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
from app.models.capture_track import CaptureTrack, CaptureTrackSlot, TrackRole
from app.models.field_session import CaptureMode as FieldCaptureMode
from app.models.field_session import FieldSession, MatchFormat
from app.models.media_fragment import MediaFragment
from app.models.timeline_event import SessionTimelineEvent, TimelineEventSource, TimelineEventType
from app.models.vidat_annotation import VidatAnnotationPackage
from app.services import vidat_annotation_service as service


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _take_with_video(db: Session, tmp_path: Path) -> CaptureTake:
    video = tmp_path / "match.mp4"
    video.write_bytes(b"sample-video")
    field_session = FieldSession(
        id="fs_vidat", title="比赛", capture_mode=FieldCaptureMode.match, match_format=MatchFormat.doubles
    )
    take = CaptureTake(
        id="ct_vidat",
        field_session_id=field_session.id,
        capture_mode=CaptureMode.single,
        source_session_type=SourceSessionType.recording,
        source_session_id="rec_vidat",
        status=CaptureTakeStatus.completed,
    )
    track = CaptureTrack(
        id="trk_vidat", capture_take_id=take.id, camera_id="cam", role=TrackRole.primary, slot=CaptureTrackSlot.cam_1
    )
    fragment = MediaFragment(
        id="frag_vidat",
        capture_take_id=take.id,
        capture_track_id=track.id,
        fragment_index=0,
        rotation_index=0,
        file_path=str(video),
    )
    db.add_all([field_session, take, track, fragment])
    db.commit()
    return take


def test_create_package_is_versioned_and_keeps_prior_snapshot(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    monkeypatch.setattr(
        service, "_probe_video", lambda _: {"fps": 30.0, "duration": 2.0, "width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    first = service.create_annotation_package(db, take.id)
    db.commit()
    second = service.create_annotation_package(db, take.id)
    db.commit()
    assert (first.version, second.version) == (1, 2)
    assert Path(first.package_dir, "manifest.json").is_file()
    assert Path(first.package_dir, "annotation.json").is_file()
    assert Path(first.package_dir, "video.mp4").is_symlink()
    assert db.query(VidatAnnotationPackage).filter_by(capture_take_id=take.id).count() == 2


def test_package_rejects_take_without_ready_video(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    fragment = db.get(MediaFragment, "frag_vidat")
    Path(fragment.file_path).unlink()
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    with pytest.raises(service.VidatPackageError, match="主机位视频尚未就绪"):
        service.create_annotation_package(db, take.id)


def test_probe_video_falls_back_to_recording_sidecar_on_external_volume_timeout(tmp_path, monkeypatch):
    video = tmp_path / "174_merged.mp4"
    video.write_bytes(b"placeholder")
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "recording_session.json").write_text(
        service.json.dumps({"duration_sec": 698.808333, "fps": 60, "resolution": "1920x1080"}),
        encoding="utf-8",
    )

    def timeout(*_args, **_kwargs):
        raise service.subprocess.TimeoutExpired("ffprobe", 15)

    monkeypatch.setattr(service.subprocess, "run", timeout)
    assert service._probe_video(video) == {
        "duration": 698.808333,
        "fps": 60.0,
        "width": 1920,
        "height": 1080,
    }


def test_publish_package_links_only_managed_artifacts(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    monkeypatch.setattr(
        service, "_probe_video", lambda _: {"fps": 30.0, "duration": 2.0, "width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    package = service.create_annotation_package(db, take.id)
    legacy_annotation = service.json.loads(package.annotation_json)
    legacy_annotation["annotation"]["actionAnnotationList"] = [
        action for action in legacy_annotation["annotation"]["actionAnnotationList"] if action["action"] != 0
    ]
    package.annotation_json = service.json.dumps(legacy_annotation)
    dist = tmp_path / "vidat-dist"
    dist.mkdir()
    (dist / "index.html").write_text("ok")
    query = service.publish_annotation_package(package, dist)
    assert package.id in query
    assert f"annotation/{package.id}.json" in query
    assert f"config/{package.id}.json" in query
    assert f"video/{package.id}.mp4" in query
    assert "decoder=v2" in query
    assert "defaultfps=30" in query
    assert (dist / "video" / f"{package.id}.mp4").is_symlink()
    assert (dist / "annotation" / f"{package.id}.json").is_file()
    assert (dist / "config" / f"{package.id}.json").is_file()
    config = service.json.loads((dist / "config" / f"{package.id}.json").read_text())
    assert config["actionLabelData"][0]["name"] == "default"
    published_annotation = service.json.loads((dist / "annotation" / f"{package.id}.json").read_text())
    assert published_annotation["annotation"]["actionAnnotationList"][0]["action"] == 0


def test_export_pairs_rally_boundaries_and_keeps_winner_metadata(db, tmp_path):
    take = _take_with_video(db, tmp_path)
    db.add_all(
        [
            SessionTimelineEvent(
                id="evt_start",
                field_session_id="fs_vidat",
                capture_take_id=take.id,
                timestamp_ms=1000,
                event_type=TimelineEventType.rally_start,
                source=TimelineEventSource.manual,
            ),
            SessionTimelineEvent(
                id="evt_end",
                field_session_id="fs_vidat",
                capture_take_id=take.id,
                timestamp_ms=3500,
                event_type=TimelineEventType.rally_end,
                source=TimelineEventSource.manual,
                payload_json='{"winner":"A","validity":"valid"}',
            ),
        ]
    )
    db.commit()
    actions = service._event_actions(db, take.id, 10.0)
    assert len(actions) == 1
    assert (actions[0]["start"], actions[0]["end"]) == (1.0, 3.5)
    assert service.json.loads(actions[0]["description"])["payload"]["winner"] == "A"


def test_package_api_creates_and_lists_versions(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    monkeypatch.setattr(
        service, "_probe_video", lambda _: {"fps": 30.0, "duration": 2.0, "width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    created = create_package(take.id, db)
    packages = list_packages(take.id, db)
    assert created.capture_take_id == take.id
    assert [package.id for package in packages] == [created.id]


def test_import_preview_detects_rally_winner_change(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    db.add_all(
        [
            SessionTimelineEvent(
                id="rally_start",
                field_session_id="fs_vidat",
                capture_take_id=take.id,
                timestamp_ms=0,
                event_type=TimelineEventType.rally_start,
                source=TimelineEventSource.manual,
            ),
            SessionTimelineEvent(
                id="rally_end",
                field_session_id="fs_vidat",
                capture_take_id=take.id,
                timestamp_ms=1000,
                event_type=TimelineEventType.rally_end,
                source=TimelineEventSource.manual,
                payload_json='{"winner":"A"}',
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        service, "_probe_video", lambda _: {"fps": 10.0, "duration": 2.0, "width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    package = service.create_annotation_package(db, take.id)
    changed = service.json.loads(package.annotation_json)
    first_action = next(action for action in changed["annotation"]["actionAnnotationList"] if action["action"] != 0)
    metadata = service.json.loads(first_action["description"])
    metadata["payload"]["winner"] = "B"
    first_action["description"] = service.json.dumps(metadata)
    preview = service.create_import_preview(db, package, changed)
    payload = service.json.loads(preview.preview_json)
    assert payload["changes"][0]["kind"] == "winner_changed"
    assert payload["changes"][0]["winner_changed"] is True


def _package(db, tmp_path, monkeypatch):
    take = _take_with_video(db, tmp_path)
    monkeypatch.setattr(
        service, "_probe_video", lambda _: {"fps": 10.0, "duration": 10.0, "width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )
    return service.create_annotation_package(db, take.id)


def _action(event_type, start, end, payload=None, index=0):
    return {
        "start": start,
        "end": end,
        "action": service.EVENT_LABELS[event_type][0],
        "object": 0,
        "description": service.json.dumps(
            {"event_type": event_type, "event_ids": [f"e{index}"], "payload": payload or {}}
        ),
    }


def test_parser_rejects_malformed_metadata_fps_bounds_and_hierarchy(db, tmp_path, monkeypatch):
    package = _package(db, tmp_path, monkeypatch)
    base = service.json.loads(package.annotation_json)
    base["annotation"]["video"]["fps"] = 30
    with pytest.raises(service.VidatPackageError, match="FPS"):
        service.parse_vidat_annotation(package, base)
    base = service.json.loads(package.annotation_json)
    base["annotation"]["actionAnnotationList"] = [_action("rally_start", 0, 101)]
    with pytest.raises(service.VidatPackageError, match="时间边界"):
        service.parse_vidat_annotation(package, base)
    base["annotation"]["actionAnnotationList"] = [_action("rally_start", 0, 2), _action("rally_start", 1, 3, index=1)]
    with pytest.raises(service.VidatPackageError, match="同层重叠"):
        service.parse_vidat_annotation(package, base)
    base["annotation"]["actionAnnotationList"] = [{**_action("rally_start", 0, 10), "description": "broken"}]
    with pytest.raises(service.VidatPackageError, match="metadata"):
        service.parse_vidat_annotation(package, base)


def test_score_anchor_maps_to_coding_action_and_summary(db, tmp_path, monkeypatch):
    package = _package(db, tmp_path, monkeypatch)
    annotation = service.json.loads(package.annotation_json)
    annotation["annotation"]["actionAnnotationList"] = [
        _action("score_correction", 5, 6, {"score_a": 7, "score_b": 4, "server_team": "B", "reason": "review"})
    ]
    preview = service.create_import_preview(db, package, annotation)
    payload = service.json.loads(preview.preview_json)
    assert payload["coding_actions"][0]["action"] == "correct_score"
    assert payload["score_summary"]["final"]["score_a"] == 7


def test_confirm_checks_content_hash_and_writes_provenance(db, tmp_path, monkeypatch):
    package = _package(db, tmp_path, monkeypatch)
    annotation = service.json.loads(package.annotation_json)
    annotation["annotation"]["actionAnnotationList"] = [_action("rally_start", 0, 10, {"winner": "A"})]
    preview = service.create_import_preview(db, package, annotation)
    changed = service.json.loads(service.json.dumps(annotation))
    changed["annotation"]["actionAnnotationList"][0]["end"] = 9
    with pytest.raises(service.VidatPackageError, match="内容与预览不一致"):
        service.confirm_import_preview(db, package, preview.token, changed)
    audit = service.confirm_import_preview(db, package, preview.token, annotation)
    db.flush()
    assert db.query(CaptureCodingAction).filter_by(annotation_package_id=package.id).count() == 2
    assert db.query(CaptureSegment).filter_by(annotation_package_id=package.id).one().vidat_import_audit_id == audit.id
    with pytest.raises(service.VidatPackageError, match="已使用"):
        service.confirm_import_preview(db, package, preview.token, annotation)
