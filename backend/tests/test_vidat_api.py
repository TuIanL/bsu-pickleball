import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.api import routes_vidat
from app.main import app
from app.database import Base
from app.api.routes_vidat import (
    ConfirmRequest,
    PackageMetadataPatch,
    PackageMetadataRequest,
    PreviewRequest,
    compare_packages,
    confirm_import,
    create_package,
    delete_package,
    derive_package,
    patch_package,
    purge_package,
    service_status,
)
from app.models.vidat_annotation import VidatAnnotationPackage
from app.services import vidat_annotation_service as annotation_service

from test_vidat_annotation_service import _take_with_video


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_vidat_version_routes_cover_metadata_compare_delete_purge_and_import(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    take = _take_with_video(db, tmp_path)
    monkeypatch.setattr(
        annotation_service,
        "_probe_video",
        lambda _: {"fps": 30.0, "duration": 2.0, "width": 1920, "height": 1080},
    )
    monkeypatch.setattr(
        annotation_service,
        "get_settings",
        lambda: type("Settings", (), {"data_dir": tmp_path, "resolve_path": lambda self, p: p})(),
    )

    source = create_package(
        take.id,
        db,
        PackageMetadataRequest(name="主标注", owner="教练 A", note="初始版本"),
    )
    assert source.name == "主标注"

    derived = derive_package(
        source.id,
        PackageMetadataRequest(name="复核版本", owner="队员 B"),
        db,
    )
    assert derived.provenance == "derived"
    assert derived.source_package_id == source.id

    patched = patch_package(
        derived.id,
        PackageMetadataPatch(note="完成一轮复核"),
        db,
    )
    assert patched.note == "完成一轮复核"
    assert patched.manifest["package_id"] == derived.id

    comparison = compare_packages(source.id, derived.id, db)
    assert comparison["before"]["name"] == "主标注"
    assert comparison["after"]["name"] == "复核版本"
    assert "changes" in comparison

    deleted = delete_package(derived.id, db)
    assert deleted.deleted_at is not None
    assert [item.id for item in routes_vidat.list_packages(take.id, db)] == [source.id]
    purged = purge_package(derived.id, db)
    assert purged["purged"] is True
    assert db.get(VidatAnnotationPackage, derived.id) is None

    annotation = json.loads(db.get(VidatAnnotationPackage, source.id).annotation_json)
    preview = routes_vidat.preview_import(source.id, PreviewRequest(annotation=annotation), db)
    confirmation = confirm_import(
        source.id,
        ConfirmRequest(
            confirmation_token=preview["confirmation_token"],
            annotation=annotation,
        ),
        db,
    )
    assert confirmation["source_package_id"] == source.id
    assert confirmation["result_package_id"] != source.id
    assert confirmation["active_vidat_package_id"] == confirmation["result_package_id"]

    monkeypatch.setattr(routes_vidat, "get_vidat_service_status", lambda: {"status": "uncontrolled"})
    assert service_status()["status"] == "uncontrolled"


def test_start_service_accepts_pid_and_timestamp_fields(monkeypatch):
    monkeypatch.setattr(
        routes_vidat,
        "ensure_vidat_service",
        lambda: {
            "url": "http://localhost:8888",
            "status": "running",
            "running": True,
            "controlled": True,
            "started": False,
            "pid": 65605,
            "started_at": 1787459105.6,
        },
    )
    response = TestClient(app).post("/api/vidat/service/start")
    assert response.status_code == 200
    assert response.json()["pid"] == 65605
