"""Vidat 标注包的本地工作台 API。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.live_coding_state import LiveCodingState
from app.models.vidat_annotation import VidatAnnotationPackage
from app.services.vidat_annotation_service import (
    VidatPackageError,
    compare_annotation_packages,
    confirm_import_preview,
    create_annotation_package,
    create_import_preview,
    derive_annotation_package,
    logical_delete_annotation_package,
    package_display_name,
    purge_annotation_package,
    publish_annotation_package,
    update_annotation_package,
)
from app.services.vidat_server import (
    VidatServiceError,
    ensure_vidat_service,
    get_vidat_service_status,
    stop_vidat_service,
)

router = APIRouter(prefix="/api/vidat", tags=["vidat"])


def _vidat_dist() -> Path:
    """Resolve the local Vidat build, while allowing deployments to override it."""
    configured = os.getenv("PICKLEBALL_VIDAT_DIST")
    if configured:
        return Path(configured).expanduser()
    vidat_dir = Path(
        os.getenv(
            "PICKLEBALL_VIDAT_DIR",
            str(Path.home() / "Documents/大学/竞赛/大创/匹克球/摄像头录制/tennistest"),
        )
    ).expanduser()
    return vidat_dir / "dist"


class PackageResponse(BaseModel):
    id: str
    capture_take_id: str
    version: int
    package_dir: str
    manifest: dict
    imported_at: str | None
    name: str
    owner: str | None
    note: str | None
    provenance: str
    source_package_id: str | None
    created_at: str | None
    deleted_at: str | None
    is_active: bool


class PackageMetadataRequest(BaseModel):
    name: str | None = None
    owner: str | None = None
    note: str | None = None


class PackageMetadataPatch(BaseModel):
    name: str | None = None
    owner: str | None = None
    note: str | None = None


class PreviewRequest(BaseModel):
    annotation: dict


class ConfirmRequest(BaseModel):
    confirmation_token: str
    annotation: dict | None = None


def _serialize(package: VidatAnnotationPackage, db: Session) -> PackageResponse:
    live_state = db.get(LiveCodingState, package.capture_take_id)
    return PackageResponse(
        id=package.id,
        capture_take_id=package.capture_take_id,
        version=package.version,
        package_dir=package.package_dir,
        manifest=json.loads(package.manifest_json),
        imported_at=package.imported_at.isoformat() if package.imported_at else None,
        name=package_display_name(package),
        owner=package.owner,
        note=package.note,
        provenance=package.provenance or "generated",
        source_package_id=package.source_package_id,
        created_at=package.created_at.isoformat() if package.created_at else None,
        deleted_at=package.deleted_at.isoformat() if package.deleted_at else None,
        is_active=bool(live_state and live_state.active_vidat_package_id == package.id),
    )


@router.get("/capture-takes/{capture_take_id}/packages", response_model=list[PackageResponse])
def list_packages(
    capture_take_id: str,
    db: Session = Depends(get_db),
    include_deleted: bool = False,
) -> list[PackageResponse]:
    packages = (
        db.query(VidatAnnotationPackage)
        .filter(VidatAnnotationPackage.capture_take_id == capture_take_id)
        .filter(VidatAnnotationPackage.deleted_at.is_(None) if not include_deleted else True)
        .order_by(VidatAnnotationPackage.version.desc())
        .all()
    )
    return [_serialize(package, db) for package in packages]


@router.post("/capture-takes/{capture_take_id}/packages", response_model=PackageResponse, status_code=201)
def create_package(
    capture_take_id: str,
    db: Session = Depends(get_db),
    request: PackageMetadataRequest | None = None,
) -> PackageResponse:
    try:
        request = request or PackageMetadataRequest()
        package = create_annotation_package(
            db,
            capture_take_id,
            name=request.name,
            owner=request.owner,
            note=request.note,
        )
        db.commit()
        db.refresh(package)
        return _serialize(package, db)
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packages/{package_id}/open")
def open_package(package_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    if package.deleted_at is not None:
        raise HTTPException(status_code=409, detail="已删除的标注包不能打开")
    dist = _vidat_dist()
    try:
        query = publish_annotation_package(package, dist)
    except VidatPackageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        service = ensure_vidat_service()
    except VidatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"url": f"{service['url']}/{query}", "package_id": package.id}


@router.post("/service/start")
def start_service() -> dict[str, str | bool | int | float | None]:
    """Start Vidat's local static server without opening a second browser window."""
    try:
        return ensure_vidat_service()
    except VidatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/service/status")
def service_status() -> dict:
    return get_vidat_service_status()


@router.post("/service/stop")
def stop_service() -> dict:
    try:
        return stop_vidat_service()
    except VidatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/packages/{source_id}/versions", response_model=PackageResponse, status_code=201)
def derive_package(
    source_id: str,
    request: PackageMetadataRequest | None = None,
    db: Session = Depends(get_db),
) -> PackageResponse:
    source = db.get(VidatAnnotationPackage, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        request = request or PackageMetadataRequest()
        package = derive_annotation_package(
            db, source, name=request.name, owner=request.owner, note=request.note
        )
        db.commit()
        db.refresh(package)
        return _serialize(package, db)
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/packages/{package_id}", response_model=PackageResponse)
def patch_package(
    package_id: str,
    request: PackageMetadataPatch,
    db: Session = Depends(get_db),
) -> PackageResponse:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        update_annotation_package(
            package,
            name=request.name,
            owner=request.owner,
            note=request.note,
            update_name="name" in request.model_fields_set,
            update_owner="owner" in request.model_fields_set,
            update_note="note" in request.model_fields_set,
        )
        db.commit()
        db.refresh(package)
        return _serialize(package, db)
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/packages/{first_id}/compare/{second_id}")
def compare_packages(first_id: str, second_id: str, db: Session = Depends(get_db)) -> dict:
    first = db.get(VidatAnnotationPackage, first_id)
    second = db.get(VidatAnnotationPackage, second_id)
    if first is None or second is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        return compare_annotation_packages(db, first, second)
    except VidatPackageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/packages/{package_id}", response_model=PackageResponse)
def delete_package(package_id: str, db: Session = Depends(get_db)) -> PackageResponse:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        logical_delete_annotation_package(db, package)
        db.commit()
        db.refresh(package)
        return _serialize(package, db)
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packages/{package_id}/purge")
def purge_package(package_id: str, db: Session = Depends(get_db)) -> dict[str, str | bool]:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        purge_annotation_package(db, package)
        db.commit()
        return {"package_id": package_id, "purged": True}
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packages/{package_id}/import-previews")
def preview_import(package_id: str, request: PreviewRequest, db: Session = Depends(get_db)) -> dict:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    if package.deleted_at is not None:
        raise HTTPException(status_code=409, detail="已删除的标注包不能创建导入预览")
    try:
        preview = create_import_preview(db, package, request.annotation)
        db.commit()
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "preview_id": preview.id,
        "confirmation_token": preview.token,
        "expires_at": preview.expires_at.isoformat(),
        **json.loads(preview.preview_json),
    }


@router.post("/packages/{package_id}/import-confirmations")
def confirm_import(package_id: str, request: ConfirmRequest, db: Session = Depends(get_db)) -> dict:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        audit = confirm_import_preview(db, package, request.confirmation_token, request.annotation)
        db.commit()
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "audit_id": audit.id,
        "source_package_id": audit.package_id,
        "result_package_id": audit.result_package_id,
        "active_vidat_package_id": audit.result_package_id,
        "operations": json.loads(audit.operations_json),
    }
