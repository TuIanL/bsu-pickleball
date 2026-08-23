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
from app.models.live_coding_state import LiveCodingState
from app.models.media_fragment import MediaFragment
from app.models.timeline_event import SessionTimelineEvent, TimelineEventSource, TimelineEventType
from app.models.vidat_annotation import VidatAnnotationPackage, VidatImportAudit
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
    assert created.name == "第 1 版"
    assert created.provenance == "generated"
    stored = db.get(VidatAnnotationPackage, created.id)
    stored.name = None
    stored.provenance = None
    db.flush()
    compatible = list_packages(take.id, db)[0]
    assert compatible.name == "第 1 版"
    assert compatible.provenance == "generated"


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
    result = db.get(VidatAnnotationPackage, audit.result_package_id)
    assert result is not None
    assert result.id != package.id
    assert result.provenance == "derived"
    assert db.query(CaptureCodingAction).filter_by(annotation_package_id=result.id).count() == 2
    assert db.query(CaptureSegment).filter_by(annotation_package_id=result.id).one().vidat_import_audit_id == audit.id
    assert db.get(VidatImportAudit, audit.id).result_package_id == result.id
    assert package.annotation_json != result.annotation_json
    assert db.get(LiveCodingState, package.capture_take_id).active_vidat_package_id == result.id
    with pytest.raises(service.VidatPackageError, match="已使用"):
        service.confirm_import_preview(db, package, preview.token, annotation)


def test_derive_package_rewrites_identity_and_keeps_source(db, tmp_path, monkeypatch):
    source = _package(db, tmp_path, monkeypatch)
    source_annotation = source.annotation_json
    derived = service.derive_annotation_package(db, source, name="交给小王", owner="小王", note="复核胜者")
    db.flush()
    annotation = service.json.loads(derived.annotation_json)
    manifest = service.json.loads(derived.manifest_json)
    assert derived.version == source.version + 1
    assert derived.name == "交给小王"
    assert derived.owner == "小王"
    assert derived.source_package_id == source.id
    assert annotation["pickleball_manifest"]["package_id"] == derived.id
    assert manifest["package_id"] == derived.id
    assert manifest["version"] == derived.version
    assert source.annotation_json == source_annotation
    assert service.parse_vidat_annotation(derived, annotation) == service.parse_vidat_annotation(source, service.json.loads(source_annotation))


def test_compare_packages_returns_event_level_changes(db, tmp_path, monkeypatch):
    source = _package(db, tmp_path, monkeypatch)
    changed = service.json.loads(source.annotation_json)
    changed["annotation"]["actionAnnotationList"] = [_action("rally_start", 0, 5, {"winner": "A"})]
    derived = service.derive_annotation_package(db, source)
    changed["pickleball_manifest"]["package_id"] = derived.id
    derived.annotation_json = service.json.dumps(changed)
    db.flush()
    comparison = service.compare_annotation_packages(db, source, derived)
    assert comparison["before"]["version"] == source.version
    assert comparison["after"]["version"] == derived.version
    assert comparison["changes"]
    assert comparison["changes"][0]["kind"] == "added"


def test_compare_packages_rejects_cross_take(db, tmp_path, monkeypatch):
    source = _package(db, tmp_path, monkeypatch)
    other = VidatAnnotationPackage(
        id="vap_other_take",
        capture_take_id="ct_other",
        version=1,
        package_dir=source.package_dir,
        manifest_json=source.manifest_json,
        annotation_json=source.annotation_json,
    )
    with pytest.raises(service.VidatPackageError, match="同一 CaptureTake"):
        service.compare_annotation_packages(db, source, other)


def test_logical_delete_hides_package_but_purge_protects_audit(db, tmp_path, monkeypatch):
    package = _package(db, tmp_path, monkeypatch)
    service.create_import_preview(db, package, service.json.loads(package.annotation_json))
    service.logical_delete_annotation_package(db, package)
    db.flush()
    assert package.deleted_at is not None
    assert service.package_display_name(package).startswith("第 ")
    with pytest.raises(service.VidatPackageError, match="预览"):
        service.purge_annotation_package(db, package)


def test_failed_import_cleans_result_directory_and_allows_transaction_rollback(db, tmp_path, monkeypatch):
    package = _package(db, tmp_path, monkeypatch)
    db.commit()
    annotation = service.json.loads(package.annotation_json)
    preview = service.create_import_preview(db, package, annotation)
    db.commit()
    before = {row.id for row in db.query(VidatAnnotationPackage).all()}

    def fail_apply(*_args, **_kwargs):
        raise service.VidatPackageError("模拟投影失败")

    monkeypatch.setattr(service, "_apply_import_plan", fail_apply)
    with pytest.raises(service.VidatPackageError, match="模拟投影失败"):
        service.confirm_import_preview(db, package, preview.token, annotation)
    db.rollback()
    assert {row.id for row in db.query(VidatAnnotationPackage).all()} == before
    assert db.get(type(preview), preview.id).consumed is False
