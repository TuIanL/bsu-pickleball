"""Deterministic formal segmentation artifact and immutable window plan."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class AnalysisWindowPlan:
    run_id: str
    windows: tuple[dict[str, Any], ...]
    plan_hash: str

    @classmethod
    def create(cls, run_id: str, windows: Iterable[dict[str, Any]]) -> "AnalysisWindowPlan":
        normalized_items = []
        for item in windows:
            start_ms = int(item["start_ms"])
            end_ms = int(item["end_ms"])
            if start_ms < 0 or end_ms <= start_ms:
                raise ValueError(f"invalid segmentation window: [{start_ms}, {end_ms})")
            normalized = {"segment_id": str(item["segment_id"]), "start_ms": start_ms, "end_ms": end_ms}
            # 与分析回合上下文的源引用。它们**刻意不参与 plan_hash 计算**：
            # 计划身份只由其几何窗口决定，这样挂上/去掉源引用都不会让既有任务的
            # windowPlanHash 失配（历史 artifact 仍按旧算法校验通过）。
            if item.get("source_rally_segment_id"):
                normalized["source_rally_segment_id"] = str(item["source_rally_segment_id"])
            if item.get("source_start_event_id"):
                normalized["source_start_event_id"] = str(item["source_start_event_id"])
            if item.get("context_rally_id"):
                normalized["context_rally_id"] = str(item["context_rally_id"])
            if item.get("context_hash"):
                normalized["context_hash"] = str(item["context_hash"])
            if item.get("binding_method"):
                normalized["binding_method"] = str(item["binding_method"])
            if item.get("binding_diagnostics"):
                normalized["binding_diagnostics"] = [str(value) for value in item["binding_diagnostics"]]
            normalized_items.append(normalized)
        normalized = tuple(sorted(normalized_items, key=lambda value: (value["start_ms"], value["segment_id"])))
        hash_material = tuple(
            {"segment_id": item["segment_id"], "start_ms": item["start_ms"], "end_ms": item["end_ms"]}
            for item in normalized
        )
        payload = {"run_id": run_id, "windows": hash_material}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(run_id, normalized, digest)

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "windows": list(self.windows), "plan_hash": self.plan_hash}


@dataclass(frozen=True)
class SegmentationArtifact:
    schema_version: str
    planning_job_id: str
    capture_take_id: str
    run_id: str
    status: str
    model: dict[str, Any]
    input_provenance: dict[str, Any]
    decoder: dict[str, Any]
    state_summary: dict[str, Any]
    state_timeline: tuple[dict[str, Any], ...]
    algorithm_segments: tuple[dict[str, Any], ...]
    window_plan: AnalysisWindowPlan

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["algorithm_segments"] = list(self.algorithm_segments)
        payload["state_timeline"] = list(self.state_timeline)
        payload["window_plan"] = self.window_plan.to_dict()
        return payload


def build_segmentation_artifact(
    *, planning_job_id: str, capture_take_id: str, run_id: str, status: str,
    model: dict[str, Any], input_provenance: dict[str, Any], decoder: dict[str, Any],
    state_summary: dict[str, Any], segments: Iterable[dict[str, Any]],
    state_timeline: Iterable[dict[str, Any]] = (),
) -> SegmentationArtifact:
    normalized = tuple(dict(segment) for segment in segments)
    plan = AnalysisWindowPlan.create(run_id, normalized)
    return SegmentationArtifact(
        schema_version="match_state_segmentation.v1", planning_job_id=planning_job_id,
        capture_take_id=capture_take_id, run_id=run_id, status=status,
        model=dict(model), input_provenance=dict(input_provenance), decoder=dict(decoder),
        state_summary=dict(state_summary), state_timeline=tuple(dict(item) for item in state_timeline),
        algorithm_segments=normalized, window_plan=plan,
    )
