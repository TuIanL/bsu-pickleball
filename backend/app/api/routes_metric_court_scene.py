"""CaptureTake-scoped metric court scene calibration API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.database import get_session_factory
from app.models.capture_take import CaptureTake
from app.schemas.metric_court_scene import (
    MetricCourtSceneCalibration,
    MetricCourtSceneDraftRequest,
    MetricCourtSceneRevisionSummary,
    MetricCourtSceneValidationResponse,
)
from app.services.metric_court_scene_service import (
    MetricCourtSceneNotFoundError,
    metric_court_scene_service,
)

router = APIRouter(prefix="/api/capture-takes", tags=["metric-court-scene"])


def _take_dir(capture_take_id: str) -> Path:
    db = get_session_factory()()
    try:
        take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
        if take is None or not take.session_dir:
            raise HTTPException(status_code=404, detail="CaptureTake session directory not found")
        return Path(take.session_dir)
    finally:
        db.close()


@router.get("/{capture_take_id}/metric-court-scene/draft", response_model=MetricCourtSceneCalibration | None)
def read_metric_court_scene_draft(capture_take_id: str) -> MetricCourtSceneCalibration | None:
    return metric_court_scene_service.get_draft(_take_dir(capture_take_id))


@router.put("/{capture_take_id}/metric-court-scene/draft", response_model=MetricCourtSceneCalibration)
def save_metric_court_scene_draft(
    capture_take_id: str,
    payload: MetricCourtSceneDraftRequest,
) -> MetricCourtSceneCalibration:
    return metric_court_scene_service.save_draft(_take_dir(capture_take_id), capture_take_id, payload)


@router.post("/{capture_take_id}/metric-court-scene/validate", response_model=MetricCourtSceneValidationResponse)
def validate_metric_court_scene(capture_take_id: str) -> MetricCourtSceneValidationResponse:
    try:
        return metric_court_scene_service.validate(_take_dir(capture_take_id), capture_take_id)
    except MetricCourtSceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{capture_take_id}/metric-court-scene/publish", response_model=MetricCourtSceneCalibration)
def publish_metric_court_scene(capture_take_id: str) -> MetricCourtSceneCalibration:
    try:
        return metric_court_scene_service.publish(_take_dir(capture_take_id), capture_take_id)
    except MetricCourtSceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{capture_take_id}/metric-court-scene/current", response_model=MetricCourtSceneCalibration | None)
def read_current_metric_court_scene(capture_take_id: str) -> MetricCourtSceneCalibration | None:
    return metric_court_scene_service.get_current(_take_dir(capture_take_id))


@router.get(
    "/{capture_take_id}/metric-court-scene/revisions",
    response_model=list[MetricCourtSceneRevisionSummary],
)
def list_metric_court_scene_revisions(capture_take_id: str) -> list[MetricCourtSceneRevisionSummary]:
    return metric_court_scene_service.list_revisions(_take_dir(capture_take_id))


@router.get(
    "/{capture_take_id}/metric-court-scene/revisions/{revision}",
    response_model=MetricCourtSceneCalibration,
)
def read_metric_court_scene_revision(capture_take_id: str, revision: int) -> MetricCourtSceneCalibration:
    try:
        return metric_court_scene_service.get_revision(_take_dir(capture_take_id), revision)
    except MetricCourtSceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
