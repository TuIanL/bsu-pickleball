"""Vidat 标注包的本地工作台 API。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vidat_annotation import VidatAnnotationPackage
from app.services.vidat_annotation_service import VidatPackageError, confirm_import_preview, create_annotation_package, create_import_preview, publish_annotation_package
from app.services.vidat_server import VidatServiceError, ensure_vidat_service

router = APIRouter(prefix="/api/vidat", tags=["vidat"])


def _vidat_dist() -> Path:
    """Resolve the local Vidat build, while allowing deployments to override it."""
    configured = os.getenv("PICKLEBALL_VIDAT_DIST")
    if configured:
        return Path(configured).expanduser()
    vidat_dir = Path(os.getenv(
        "PICKLEBALL_VIDAT_DIR",
        str(Path.home() / "Documents/大学/竞赛/大创/匹克球/摄像头录制/tennistest"),
    )).expanduser()
    return vidat_dir / "dist"


class PackageResponse(BaseModel):
    id: str
    capture_take_id: str
    version: int
    package_dir: str
    manifest: dict
    imported_at: str | None


class PreviewRequest(BaseModel):
    annotation: dict


class ConfirmRequest(BaseModel):
    confirmation_token: str
    annotation: dict | None = None


def _serialize(package: VidatAnnotationPackage) -> PackageResponse:
    return PackageResponse(id=package.id, capture_take_id=package.capture_take_id, version=package.version,
        package_dir=package.package_dir, manifest=json.loads(package.manifest_json),
        imported_at=package.imported_at.isoformat() if package.imported_at else None)


@router.get("/capture-takes/{capture_take_id}/packages", response_model=list[PackageResponse])
def list_packages(capture_take_id: str, db: Session = Depends(get_db)) -> list[PackageResponse]:
    packages = db.query(VidatAnnotationPackage).filter(
        VidatAnnotationPackage.capture_take_id == capture_take_id).order_by(VidatAnnotationPackage.version.desc()).all()
    return [_serialize(package) for package in packages]


@router.post("/capture-takes/{capture_take_id}/packages", response_model=PackageResponse, status_code=201)
def create_package(capture_take_id: str, db: Session = Depends(get_db)) -> PackageResponse:
    try:
        package = create_annotation_package(db, capture_take_id)
        db.commit()
        db.refresh(package)
        return _serialize(package)
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/packages/{package_id}/open")
def open_package(package_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
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
def start_service() -> dict[str, str | bool]:
    """Start Vidat's local static server without opening a second browser window."""
    try:
        return ensure_vidat_service()
    except VidatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/packages/{package_id}/import-previews")
def preview_import(package_id: str, request: PreviewRequest, db: Session = Depends(get_db)) -> dict:
    package = db.get(VidatAnnotationPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="标注包不存在")
    try:
        preview = create_import_preview(db, package, request.annotation)
        db.commit()
    except VidatPackageError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"preview_id": preview.id, "confirmation_token": preview.token,
            "expires_at": preview.expires_at.isoformat(), **json.loads(preview.preview_json)}


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
    return {"audit_id": audit.id, "package_id": package.id, "operations": json.loads(audit.operations_json)}
