"""评分校准标注工作台 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.scoring_calibration_annotation import (
    AnnotationPackageCreateRequest,
    AnnotationPackageRevisionRequest,
    AnnotationPackageSummary,
    AnnotationUpdateRequest,
    AnnotationUpsertRequest,
    CandidateDecisionRequest,
    GoldSetResponse,
)
from app.services import scoring_calibration_annotation_service as service


router = APIRouter(prefix="/api", tags=["scoring-calibration-annotation"])


def _summary(payload: dict) -> AnnotationPackageSummary:
    return AnnotationPackageSummary.model_validate(payload)


def _committed_summary(db: Session, payload: dict) -> AnnotationPackageSummary:
    """Mutating annotation endpoints must survive the request-scoped session closing."""
    db.commit()
    return _summary(payload)


def _error(exc: service.ScoringCalibrationError) -> HTTPException:
    if exc.code in {"capture_take_not_found", "annotation_not_found", "candidate_not_found", "package_not_found"}:
        status = 404
    elif exc.code in {"package_locked", "package_not_locked"}:
        status = 409
    elif exc.code == "annotation_validation_failed":
        issues = getattr(exc, "issues", [])
        return HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "issues": [issue.model_dump(mode="json") for issue in issues]},
        )
    elif exc.code == "gold_set_not_ready":
        status = 409
    else:
        status = 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


def _get_package_or_404(db: Session, revision_id: str):
    package = service.get_package(db, revision_id)
    if package is None:
        raise HTTPException(status_code=404, detail={"code": "package_not_found", "message": "标注包 revision 不存在"})
    return package


def _get_take_bound_package_or_404(db: Session, capture_take_id: str, revision_id: str):
    package = _get_package_or_404(db, revision_id)
    if package.capture_take_id != capture_take_id:
        raise HTTPException(status_code=404, detail={"code": "package_not_found", "message": "标注包不属于当前 CaptureTake"})
    return package


@router.get("/capture-takes/{capture_take_id}/scoring-calibration/packages", response_model=list[AnnotationPackageSummary])
def list_packages(capture_take_id: str, db: Session = Depends(get_db)):
    return [_summary(item) for item in service.list_packages(db, capture_take_id)]


@router.get("/capture-takes/{capture_take_id}/scoring-calibration/gold-set-status")
def gold_set_status(capture_take_id: str, db: Session = Depends(get_db)):
    return service.gold_set_status(db, capture_take_id)


@router.post("/capture-takes/{capture_take_id}/scoring-calibration/packages", response_model=AnnotationPackageSummary, status_code=201)
def create_package(
    capture_take_id: str,
    request: AnnotationPackageCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return _committed_summary(db, service.create_package(db, capture_take_id, request))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.get("/scoring-calibration/packages/{revision_id}", response_model=AnnotationPackageSummary)
def get_package(revision_id: str, db: Session = Depends(get_db)):
    package = _get_package_or_404(db, revision_id)
    return _summary(service._package_summary(db, package))


@router.post("/scoring-calibration/packages/{revision_id}/revisions", response_model=AnnotationPackageSummary, status_code=201)
def create_revision(
    revision_id: str,
    request: AnnotationPackageRevisionRequest,
    db: Session = Depends(get_db),
):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.create_revision(db, package, request))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.post("/scoring-calibration/packages/{revision_id}/annotations", response_model=AnnotationPackageSummary, status_code=201)
def create_annotation(
    revision_id: str,
    request: AnnotationUpsertRequest,
    db: Session = Depends(get_db),
):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.create_annotation(db, package, request))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.patch("/scoring-calibration/packages/{revision_id}/annotations/{annotation_id}", response_model=AnnotationPackageSummary)
def update_annotation(
    revision_id: str,
    annotation_id: str,
    request: AnnotationUpdateRequest,
    db: Session = Depends(get_db),
):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.update_annotation(db, package, annotation_id, request))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.delete("/scoring-calibration/packages/{revision_id}/annotations/{annotation_id}", response_model=AnnotationPackageSummary)
def revoke_annotation(revision_id: str, annotation_id: str, db: Session = Depends(get_db)):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.revoke_annotation(db, package, annotation_id))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.post("/scoring-calibration/packages/{revision_id}/candidates/{candidate_id}/decision", response_model=AnnotationPackageSummary)
def decide_candidate(
    revision_id: str,
    candidate_id: str,
    request: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.decide_candidate(db, package, candidate_id, request))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.post("/scoring-calibration/packages/{revision_id}/review", response_model=AnnotationPackageSummary)
def mark_reviewed(revision_id: str, db: Session = Depends(get_db)):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.mark_reviewed(db, package))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.post("/scoring-calibration/packages/{revision_id}/lock", response_model=AnnotationPackageSummary)
def lock_package(revision_id: str, db: Session = Depends(get_db)):
    package = _get_package_or_404(db, revision_id)
    try:
        return _committed_summary(db, service.lock_package(db, package))
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc


@router.get("/scoring-calibration/packages/{revision_id}/gold-set", response_model=GoldSetResponse)
def get_gold_set(revision_id: str, db: Session = Depends(get_db)):
    package = _get_package_or_404(db, revision_id)
    try:
        return service.get_gold_set(db, package)
    except service.ScoringCalibrationError as exc:
        raise _error(exc) from exc
