"""证据对象的严格解析；关系不反写源产物，也不按最近时间猜配。"""
from __future__ import annotations

from app.analysis_runtime.contracts import Association, ObjectRef
from app.analysis_runtime.hashing import AnalysisRuntimeError


def resolve_object(store, reference: ObjectRef):
    manifest = store.manifest(reference.artifact_id)
    if manifest is None:
        raise AnalysisRuntimeError("association_source_missing", "证据源不存在")
    payload = store.payload(manifest.ref)
    if reference.subject_scope == "observation":
        sources = manifest.provenance.get("sources", [])
        if not any(s["view_id"]==reference.view_id and s["media_sha256"]==reference.epoch for s in sources):
            raise AnalysisRuntimeError("association_scope_mismatch", "主体来源/机位作用域不符")
    candidates = []
    for row in payload.get("observations", []):
        if reference.view_id is not None and row.get("view_id") != reference.view_id:
            continue
        candidates.extend(row.get("subjects", []))
        candidates.extend(row.get("candidates", []))
    candidates.extend(payload.get("objects", []))
    exact = [obj for obj in candidates if obj.get("observation_id", obj.get("local_id", obj.get("event_id"))) == reference.local_id
             and obj.get("object_type", reference.object_type) == reference.object_type]
    if len(exact) != 1:
        raise AnalysisRuntimeError("association_object_unresolved", "对象引用缺失或不唯一")
    return exact[0]


def validate_association(store, association: Association) -> Association:
    for candidate in association.candidates:
        resolve_object(store, candidate.source)
        resolve_object(store, candidate.target)
        limit = candidate.constraints.get("max_delta_ms")
        if limit is not None and abs(candidate.temporal_delta_ms) > limit:
            raise AnalysisRuntimeError("association_time_constraint", "候选超出声明的时间容差")
    return association
