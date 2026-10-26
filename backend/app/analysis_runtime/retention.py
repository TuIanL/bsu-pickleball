"""源与共享证据删除保护。只读索引，不扫描历史 Job，也不创建数据库。"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from app.analysis_runtime.hashing import AnalysisRuntimeError


def references(settings, *, path: Path | None = None, video_ids=(), excluding_job=None) -> list[str]:
    database = settings.resolve_path(settings.analysis_control_database_path) if settings.analysis_control_database_path else settings.resolved_outputs_dir.parent / "analysis_control.sqlite3"
    if not database.is_file():
        return []
    target = Path(path).resolve() if path is not None else None
    connection = sqlite3.connect(database.resolve().as_uri()+"?mode=ro", uri=True)
    result = set()
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "analysis_source_refs" not in tables:
            return []
        for owner_type, owner_id, raw in connection.execute(
                "SELECT r.owner_type,r.owner_id,s.snapshot_json FROM analysis_source_refs r JOIN analysis_sources s ON s.source_id=r.source_id"):
            if (owner_type,owner_id)==("job",excluding_job):
                continue
            source = json.loads(raw)
            matches_video = source.get("video_id") in set(video_ids)
            matches_path = target is not None and any(
                Path(value).resolve()==target or Path(value).resolve().is_relative_to(target)
                for key,value in source.items() if key in {"media_path","sidecar_path","timing_path"} and value)
            if matches_video or matches_path:
                result.add(owner_type+":"+owner_id)
        if target is not None and "analysis_artifacts" in tables:
            root = settings.resolve_path(settings.modular_artifacts_dir) if settings.modular_artifacts_dir else settings.resolved_outputs_dir/"_artifacts"
            locations = dict(connection.execute("SELECT storage_id,root_path FROM analysis_storage_locations")) if "analysis_storage_locations" in tables else {}
            for artifact_id, raw in connection.execute("SELECT artifact_id,manifest_json FROM analysis_artifacts"):
                manifest = json.loads(raw)
                artifact_root = Path(locations.get(manifest["storage_id"],root))
                artifact_path = (artifact_root/manifest["relative_key"]).resolve()
                if artifact_path==target or artifact_path.is_relative_to(target):
                    result.add("artifact:"+artifact_id)
        return sorted(result)
    finally:
        connection.close()


def assert_unpinned(settings, path: Path):
    pins = references(settings,path=path)
    if pins:
        raise AnalysisRuntimeError("source_or_artifact_pinned", "文件仍被存活分析证据引用，不能删除", details={"references":pins})
