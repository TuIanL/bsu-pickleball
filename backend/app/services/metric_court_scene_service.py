"""CaptureTake-scoped metric court scene calibration service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas.metric_court_scene import (
    MetricCourtSceneCalibration,
    MetricCourtSceneDraftRequest,
    MetricCourtSceneRevisionSummary,
    MetricCourtSceneValidationResponse,
    SceneCameraQuality,
)
from app.services.capture_storage_service import capture_storage_plan_from_dir
from app.services.storage_service import StorageService
from app.vision.multiview.court_frame import load_canonical_court_frame, resolve_or_create_canonical_court_frame
from app.vision.multiview.metric_court_scene import (
    build_standard_net_profile,
    sample_net_top_profile,
)


class MetricCourtSceneNotFoundError(FileNotFoundError):
    pass


class MetricCourtSceneService:
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def scene_root(self, take_dir: str | Path) -> Path:
        # Resolve through the same CaptureTake layout used by recording and
        # keep path construction centralized in StorageService.
        capture_storage_plan_from_dir(take_dir)
        return self.storage.metric_court_scene_root(take_dir)

    def draft_path(self, take_dir: str | Path) -> Path:
        return self.storage.metric_court_scene_draft_path(take_dir)

    def revision_path(self, take_dir: str | Path, revision: int) -> Path:
        return self.storage.metric_court_scene_revision_path(take_dir, revision)

    def current_path(self, take_dir: str | Path) -> Path:
        return self.storage.metric_court_scene_current_path(take_dir)

    def _read(self, path: Path) -> MetricCourtSceneCalibration:
        if not path.exists():
            raise MetricCourtSceneNotFoundError(str(path))
        return MetricCourtSceneCalibration.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def get_draft(self, take_dir: str | Path) -> MetricCourtSceneCalibration | None:
        path = self.draft_path(take_dir)
        return self._read(path) if path.exists() else None

    def save_draft(
        self,
        take_dir: str | Path,
        capture_take_id: str,
        payload: MetricCourtSceneDraftRequest,
    ) -> MetricCourtSceneCalibration:
        # Scene calibration and Parent artifacts must reference the same
        # take-scoped ccf_* definition. Do not persist a capture-take:* UI
        # placeholder as if it were a canonical frame id.
        canonical = load_canonical_court_frame(take_dir)
        # The calibration flow has views and can safely bootstrap its
        # take-scoped canonical frame; a completely empty payload must remain
        # degraded so validation still reports the missing canonical input.
        if canonical is None and payload.views:
            canonical = resolve_or_create_canonical_court_frame(
                take_dir,
                capture_take_id,
                "end_a",
                "end_b",
                orientation_by_view={
                    view.view_id: view.court_orientation
                    for view in payload.views
                    if view.court_orientation is not None
                },
            )
        existing = self.get_draft(take_dir)
        now = self._now()
        net_profile = payload.net_profile
        if net_profile.control_points and not net_profile.sampled_top_profile:
            net_profile = net_profile.model_copy(
                update={"sampled_top_profile": sample_net_top_profile(net_profile.control_points)}
            )

        scene = MetricCourtSceneCalibration(
            schema_version="metric_court_scene.v1",
            capture_take_id=capture_take_id,
            revision=existing.revision if existing else 0,
            status="draft",
            canonical_frame_id=canonical.frame_id if canonical else payload.canonical_frame_id,
            net_profile=net_profile,
            holdout_control_points=payload.holdout_control_points,
            views=payload.views,
            provenance=payload.provenance,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        if not scene.net_profile.control_points:
            scene.net_profile = build_standard_net_profile()
        self.storage.write_json_atomic(self.draft_path(take_dir), scene.model_dump(mode="json"))
        return scene

    def validate(
        self,
        take_dir: str | Path,
        capture_take_id: str,
        scene: MetricCourtSceneCalibration | None = None,
    ) -> MetricCourtSceneValidationResponse:
        candidate = scene or self.get_draft(take_dir)
        if candidate is None:
            raise MetricCourtSceneNotFoundError("scene calibration draft not found")
        reasons: list[str] = []
        if candidate.capture_take_id != capture_take_id:
            reasons.append("capture_take_id_mismatch")
        if len(candidate.views) < 1:
            reasons.append("no_views")
        if len(candidate.net_profile.control_points) < 3:
            reasons.append("net_control_points_incomplete")
        if not all(point.confirmed for point in candidate.net_profile.control_points):
            reasons.append("net_controls_must_be_manually_confirmed")
        expected_control_ids = {"left", "center", "right"}
        actual_control_ids = {point.id for point in candidate.net_profile.control_points}
        if not expected_control_ids.issubset(actual_control_ids):
            reasons.append("net_control_points_incomplete")
        for view in candidate.views:
            missing = sorted(expected_control_ids - set(view.net_annotations))
            if missing:
                reasons.append(f"view_net_annotations_incomplete:{view.view_id}")
        if candidate.canonical_frame_id is None:
            reasons.append("canonical_frame_missing")
        if not candidate.net_profile.sampled_top_profile:
            reasons.append("net_profile_not_sampled")
        status = "ready" if not reasons else "degraded"
        quality = SceneCameraQuality(
            status="ok" if status == "ready" else "warning",
            rejection_reasons=reasons,
        )
        validated = candidate.model_copy(
            update={
                "status": status,
                "updated_at": self._now(),
                "quality": quality,
                "rejection_reasons": reasons,
                "fallback_metric_validity": "metric_multiview" if status == "ready" else "unavailable",
            }
        )
        return MetricCourtSceneValidationResponse(
            capture_take_id=capture_take_id,
            status=status,
            quality=quality,
            rejection_reasons=reasons,
            scene=validated,
        )

    def publish(self, take_dir: str | Path, capture_take_id: str) -> MetricCourtSceneCalibration:
        validation = self.validate(take_dir, capture_take_id)
        if validation.status != "ready":
            raise ValueError("scene calibration quality gate failed: " + ", ".join(validation.rejection_reasons))

        scene_root = self.scene_root(take_dir)
        scene_root.mkdir(parents=True, exist_ok=True)
        current = self.current_path(take_dir)
        previous_revision = 0
        if current.exists():
            previous_revision = self._read(current).revision
        revision = previous_revision + 1
        now = self._now()
        published = validation.scene.model_copy(
            update={"revision": revision, "status": "ready", "updated_at": now, "published_at": now}
        )
        revision_path = self.revision_path(take_dir, revision)
        if revision_path.exists():
            raise FileExistsError(f"scene calibration revision already exists: {revision}")
        self.storage.write_json_atomic(revision_path, published.model_dump(mode="json"))
        self.storage.write_json_atomic(current, published.model_dump(mode="json"))
        return published

    def get_current(self, take_dir: str | Path) -> MetricCourtSceneCalibration | None:
        path = self.current_path(take_dir)
        return self._read(path) if path.exists() else None

    def get_revision(self, take_dir: str | Path, revision: int) -> MetricCourtSceneCalibration:
        return self._read(self.revision_path(take_dir, revision))

    def list_revisions(self, take_dir: str | Path) -> list[MetricCourtSceneRevisionSummary]:
        root = self.scene_root(take_dir) / "revisions"
        if not root.exists():
            return []
        summaries: list[MetricCourtSceneRevisionSummary] = []
        for path in sorted(root.glob("revision-*.json")):
            scene = self._read(path)
            summaries.append(
                MetricCourtSceneRevisionSummary(
                    revision=scene.revision,
                    status=scene.status,
                    provenance=scene.provenance,
                    created_at=scene.created_at,
                    published_at=scene.published_at,
                )
            )
        return summaries


metric_court_scene_service = MetricCourtSceneService()
