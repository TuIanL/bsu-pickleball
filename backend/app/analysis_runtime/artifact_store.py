"""既有 SQLite 控制面内的计划、证据与发布索引。

文件 finalize 与数据库不是一个事务；只有 DB 登记完成后才允许读取。
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from app.analysis_runtime.contracts import (
    AnalysisPlan, ArtifactManifest, ArtifactRef, ModelSnapshot, NodeRun,
    SourceSnapshot,
)
from app.analysis_runtime.hashing import AnalysisRuntimeError, canonical_json, digest, file_digest
from app.analysis_runtime.planner import model_identity, source_identity, verify_plan

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analysis_plans (
 plan_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL, contract_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_module_jobs (
 job_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, plan_hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_module_plan_hash ON analysis_module_jobs(plan_hash);
CREATE TABLE IF NOT EXISTS analysis_sources (
 source_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_models (
 implementation_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_storage_locations (
 storage_id TEXT PRIMARY KEY, root_path TEXT NOT NULL, device INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_node_attempts (
 job_id TEXT NOT NULL, node_key TEXT NOT NULL, job_attempt INTEGER NOT NULL,
 node_attempt INTEGER NOT NULL, run_json TEXT NOT NULL,
 PRIMARY KEY(job_id,node_key,job_attempt,node_attempt));
CREATE TABLE IF NOT EXISTS analysis_artifacts (
 artifact_id TEXT PRIMARY KEY, cache_key TEXT NOT NULL,
 manifest_json TEXT NOT NULL, integrity TEXT NOT NULL DEFAULT 'available');
CREATE INDEX IF NOT EXISTS ix_artifact_cache ON analysis_artifacts(cache_key);
CREATE TABLE IF NOT EXISTS analysis_cache_entries (
 cache_key TEXT PRIMARY KEY, current_artifact_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_job_artifact_refs (
 job_id TEXT NOT NULL, node_key TEXT NOT NULL, artifact_id TEXT NOT NULL,
 PRIMARY KEY(job_id,node_key,artifact_id));
CREATE TABLE IF NOT EXISTS analysis_artifact_edges (
 consumer_artifact_id TEXT NOT NULL, input_artifact_id TEXT NOT NULL,
 PRIMARY KEY(consumer_artifact_id,input_artifact_id));
CREATE TABLE IF NOT EXISTS analysis_source_refs (
 owner_type TEXT NOT NULL, owner_id TEXT NOT NULL, source_id TEXT NOT NULL,
 PRIMARY KEY(owner_type,owner_id,source_id));
CREATE TABLE IF NOT EXISTS analysis_module_results (
 job_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL);
"""


class ArtifactStore:
    def __init__(self, control_plane, root: Path):
        # 构造器和 read 方法均不迁移/写库；schema 在既有控制面启动边界创建。
        self.control_plane = control_plane
        self.root = Path(root).resolve()
        self.storage_id = "shared-" + digest(str(self.root))[:24]

    @contextmanager
    def read_connection(self):
        if not self.control_plane.path.is_file():
            raise AnalysisRuntimeError("preparation_required", "尚未建立模块来源索引，请先显式准备来源")
        connection = sqlite3.connect(self.control_plane.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        connection = self.control_plane._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _read_json(self, table: str, key: str, value: str, column: str):
        with self.read_connection() as connection:
            row = connection.execute(f"SELECT {column} FROM {table} WHERE {key}=?", (value,)).fetchone()
            return json.loads(row[0]) if row else None

    def source(self, source_id: str) -> SourceSnapshot | None:
        value = self._read_json("analysis_sources", "source_id", source_id, "snapshot_json")
        return SourceSnapshot.model_validate(value) if value else None

    def model(self, implementation_id: str) -> ModelSnapshot | None:
        value = self._read_json("analysis_models", "implementation_id", implementation_id, "snapshot_json")
        return ModelSnapshot.model_validate(value) if value else None

    def register_source(self, source: SourceSnapshot):
        with self.transaction() as connection:
            old = connection.execute("SELECT snapshot_json FROM analysis_sources WHERE source_id=?", (source.source_id,)).fetchone()
            if old and json.loads(old[0]) != source.model_dump(mode="json"):
                raise AnalysisRuntimeError("source_identity_conflict", source.source_id)
            connection.execute("INSERT OR IGNORE INTO analysis_sources VALUES (?,?)",
                               (source.source_id, source.model_dump_json()))

    def register_model(self, model: ModelSnapshot):
        with self.transaction() as connection:
            connection.execute("INSERT INTO analysis_models VALUES (?,?) ON CONFLICT(implementation_id) DO UPDATE SET snapshot_json=excluded.snapshot_json",
                               (model.implementation_id, model.model_dump_json()))

    def submit(self, plan: AnalysisPlan, job_payload: dict, *, new_version=False) -> dict:
        verify_plan(plan)
        with self.transaction() as connection:
            previous = connection.execute(
                "SELECT j.payload_json FROM analysis_module_jobs m JOIN analysis_jobs j ON j.job_id=m.job_id WHERE m.plan_hash=? ORDER BY j.created_at DESC LIMIT 1",
                (plan.plan_hash,)).fetchone()
            if new_version and previous:
                old = json.loads(previous[0])
                job_payload.update(previousJobId=old["id"], analysisVersion=int(old.get("analysisVersion", 1))+1)
            if not new_version:
                row = connection.execute(
                    "SELECT j.payload_json FROM analysis_module_jobs m JOIN analysis_jobs j ON j.job_id=m.job_id "
                    "WHERE m.plan_hash=? AND j.canonical_status IN ('queued','running','succeeded') ORDER BY j.created_at LIMIT 1",
                    (plan.plan_hash,)).fetchone()
                if row:
                    return json.loads(row[0])
            connection.execute("INSERT INTO analysis_plans VALUES (?,?,?)",
                               (plan.plan_id, plan.plan_hash, plan.model_dump_json()))
            self.control_plane._upsert_in_connection(connection, job_payload)
            connection.execute("INSERT INTO analysis_module_jobs VALUES (?,?,?)", (job_payload["id"], plan.plan_id, plan.plan_hash))
            connection.executemany("INSERT OR IGNORE INTO analysis_source_refs VALUES ('job',?,?)",
                                   [(job_payload["id"], s.source_id) for s in plan.sources])
        return job_payload

    def plan(self, plan_id: str) -> AnalysisPlan | None:
        value = self._read_json("analysis_plans", "plan_id", plan_id, "contract_json")
        if value is None:
            return None
        plan = AnalysisPlan.model_validate(value)
        verify_plan(plan)
        return plan

    def manifest(self, artifact_id: str) -> ArtifactManifest | None:
        value = self._read_json("analysis_artifacts", "artifact_id", artifact_id, "manifest_json")
        return ArtifactManifest.model_validate(value) if value else None

    def path(self, manifest: ArtifactManifest) -> Path:
        root = self.location_root(manifest.storage_id)
        key = Path(manifest.relative_key)
        if key.is_absolute() or ".." in key.parts:
            raise AnalysisRuntimeError("unsafe_artifact_path", "无效产物位置")
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            raise AnalysisRuntimeError("unsafe_artifact_path", "产物路径越界")
        return path

    def location_root(self, storage_id):
        if storage_id == "local_shared_v1":
            return self.root
        with self.read_connection() as connection:
            row = connection.execute("SELECT root_path,device FROM analysis_storage_locations WHERE storage_id=?", (storage_id,)).fetchone()
        if row is None:
            raise AnalysisRuntimeError("location_unavailable", "存储位置未登记")
        root = Path(row[0])
        if not root.is_dir() or root.stat().st_dev != row[1]:
            raise AnalysisRuntimeError("location_unavailable", "存储位置离线或设备已变化")
        return root

    def prepare_publish_location(self):
        with self.transaction() as connection:
            row = connection.execute("SELECT device FROM analysis_storage_locations WHERE storage_id=?", (self.storage_id,)).fetchone()
            if row:
                if not self.root.is_dir() or self.root.stat().st_dev != row[0]:
                    raise AnalysisRuntimeError("location_unavailable", "已登记的存储位置不可用")
            else:
                if not self.root.parent.is_dir():
                    raise AnalysisRuntimeError("location_unavailable", "存储根的父目录不可用")
                self.root.mkdir(exist_ok=True)
                connection.execute("INSERT INTO analysis_storage_locations VALUES (?,?,?)", (self.storage_id,str(self.root),self.root.stat().st_dev))

    def availability(self, manifest: ArtifactManifest) -> str:
        try:
            path = self.path(manifest)
        except AnalysisRuntimeError as exc:
            if exc.code != "location_unavailable":
                raise
            return "location_unavailable"
        if not path.is_file():
            return "missing"
        try:
            return "available" if file_digest(path) == manifest.content_sha256 else "corrupt"
        except OSError:
            return "location_unavailable"

    def cached(self, key: str) -> ArtifactManifest | None:
        with self.read_connection() as connection:
            row = connection.execute("SELECT current_artifact_id FROM analysis_cache_entries WHERE cache_key=?", (key,)).fetchone()
        manifest = self.manifest(row[0]) if row else None
        return manifest if manifest and self.availability(manifest) == "available" else None

    def payload(self, ref: ArtifactRef):
        manifest = self.manifest(ref.artifact_id)
        if manifest is None or manifest.ref != ref:
            raise AnalysisRuntimeError("artifact_missing", ref.artifact_id)
        availability = self.availability(manifest)
        if availability != "available":
            raise AnalysisRuntimeError(availability, "产物不可读", details={"artifact_id": ref.artifact_id})
        return json.loads(self.path(manifest).read_text())

    @staticmethod
    def check_lease(connection, job_id: str, worker_run_id: str, attempt: int):
        row = connection.execute("SELECT canonical_status,worker_run_id,attempt,cancel_requested_at FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or row[0] != "running" or row[1] != worker_run_id or row[2] != attempt:
            from app.services.job_orchestration import WorkerLeaseLostError
            raise WorkerLeaseLostError("module publication lease lost")
        if row[3]:
            from app.services.job_orchestration import JobCanceledError
            raise JobCanceledError("module publication canceled")

    def record_node(self, job, run: NodeRun):
        with self.transaction() as connection:
            self.check_lease(connection, job.id, job.workerRunId, job.attempt)
            self._node_row(connection, job, run)

    @staticmethod
    def _node_row(connection, job, run):
        connection.execute(
            "INSERT INTO analysis_node_attempts VALUES (?,?,?,?,?) "
            "ON CONFLICT(job_id,node_key,job_attempt,node_attempt) DO UPDATE SET run_json=excluded.run_json",
            (job.id, run.node_key, job.attempt, run.node_attempt, run.model_dump_json()))

    def bind_cached(self, job, run: NodeRun):
        manifest = self.manifest(run.artifact.artifact_id)
        if manifest is None or self.availability(manifest) != "available":
            raise AnalysisRuntimeError("cache_disappeared", "缓存已失效")
        with self.transaction() as connection:
            self.check_lease(connection, job.id, job.workerRunId, job.attempt)
            connection.execute("INSERT OR IGNORE INTO analysis_job_artifact_refs VALUES (?,?,?)",
                               (job.id, run.node_key, manifest.ref.artifact_id))
            self._node_row(connection, job, run)

    def publish(self, job, plan: AnalysisPlan, node, key: str, payload: dict, run: NodeRun, *, actual_inputs=None, fault=None):
        self.prepare_publish_location()
        if not isinstance(payload, dict) or any(field not in payload for field in node.implementation.output_required_fields):
            raise AnalysisRuntimeError("artifact_schema_error", "缺少声明的输出字段")
        if "observations" in node.implementation.output_required_fields and not isinstance(payload["observations"], list):
            raise AnalysisRuntimeError("artifact_schema_error", "observations 必须为数组")
        artifact_id = "artifact-" + uuid4().hex
        if not re.fullmatch(r"job-[A-Za-z0-9_-]+", job.id):
            raise AnalysisRuntimeError("unsafe_job_id", "无效任务标识")
        stage = self.root / ".staging" / job.id / f"{job.attempt}-{run.node_attempt}-{uuid4().hex}"
        stage.mkdir(parents=True)
        staged = stage / "payload.json"
        staged.write_text(canonical_json(payload) + "\n")
        content_hash = file_digest(staged)
        destination = self.root / artifact_id
        stage.rename(destination)
        manifest = ArtifactManifest(
            ref=ArtifactRef(artifact_id=artifact_id, artifact_type=node.implementation.output_type, schema_version=node.implementation.output_schema),
            cache_key=key, content_sha256=content_hash, storage_id=self.storage_id,
            relative_key=artifact_id + "/payload.json", created_by_job_id=job.id,
            node_key=node.node_key, implementation_id=node.implementation.implementation_id,
            implementation_version=node.implementation.version,
            inputs=tuple(m.ref for _, m in sorted((actual_inputs or {}).items())),
            quality=("insufficient_evidence" if run.counters.get("secondary_degraded") else "truncated" if node.truncated else "no_candidates" if "observations" in payload and not any(o.get("subjects") or o.get("candidates") for o in payload["observations"]) else "sufficient"),
            coordinates=node.implementation.coordinate_system, units=node.implementation.units,
            provenance={
                "sources": [source_identity(s) for s in plan.sources], "sampling": plan.sampling.model_dump(),
                "compute_window": node.compute_window.model_dump(), "output_window": node.output_window.model_dump(),
                "consumed_context": node.consumed_context, "parameters": node.parameters,
                "model": model_identity(node.model), "selector": node.output_selector,
            }, diagnostics=run.counters,
        )
        if fault:
            fault("after_finalize")
        completed = run.model_copy(update={"status": "completed", "artifact": manifest.ref})
        with self.transaction() as connection:
            self.check_lease(connection, job.id, job.workerRunId, job.attempt)
            connection.execute("INSERT INTO analysis_artifacts VALUES (?,?,?,'available')",
                               (artifact_id, key, manifest.model_dump_json()))
            previous = connection.execute("SELECT current_artifact_id FROM analysis_cache_entries WHERE cache_key=?", (key,)).fetchone()
            if previous is None:
                connection.execute("INSERT INTO analysis_cache_entries VALUES (?,?)", (key, artifact_id))
            else:
                old_row = connection.execute("SELECT manifest_json FROM analysis_artifacts WHERE artifact_id=?", (previous[0],)).fetchone()
                old = ArtifactManifest.model_validate_json(old_row[0]) if old_row else None
                if old is None or self.availability(old) != "available":
                    if old:
                        connection.execute("UPDATE analysis_artifacts SET integrity=? WHERE artifact_id=?", (self.availability(old), old.ref.artifact_id))
                    connection.execute("UPDATE analysis_cache_entries SET current_artifact_id=? WHERE cache_key=? AND current_artifact_id=?", (artifact_id, key, previous[0]))
            connection.execute("INSERT INTO analysis_job_artifact_refs VALUES (?,?,?)", (job.id, node.node_key, artifact_id))
            connection.executemany("INSERT OR IGNORE INTO analysis_artifact_edges VALUES (?,?)",
                                   [(artifact_id, ref.artifact_id) for ref in manifest.inputs])
            connection.executemany("INSERT OR IGNORE INTO analysis_source_refs VALUES ('artifact',?,?)",
                                   [(artifact_id, source.source_id) for source in plan.sources])
            self._node_row(connection, job, completed)
            if fault:
                fault("before_commit")
        return completed

    def used_manifest(self, job_id: str, node_key: str):
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT artifact_id FROM analysis_job_artifact_refs WHERE job_id=? AND node_key=? ORDER BY rowid DESC LIMIT 1",
                (job_id, node_key)).fetchone()
        return self.manifest(row[0]) if row else None

    def save_result(self, job, manifest):
        with self.transaction() as connection:
            self.check_lease(connection, job.id, job.workerRunId, job.attempt)
            connection.execute("INSERT INTO analysis_module_results VALUES (?,?) ON CONFLICT(job_id) DO UPDATE SET manifest_json=excluded.manifest_json",
                               (job.id, manifest.model_dump_json()))

    def result(self, job_id: str):
        return self._read_json("analysis_module_results", "job_id", job_id, "manifest_json")

    def node_runs(self, job_id: str):
        with self.read_connection() as connection:
            rows = connection.execute("SELECT run_json FROM analysis_node_attempts WHERE job_id=? ORDER BY job_attempt,node_attempt", (job_id,)).fetchall()
        latest = {}
        for row in rows:
            run = NodeRun.model_validate_json(row[0])
            latest[run.node_key] = run
        return list(latest.values())

    def source_pins(self, path: Path, *, excluding_job: str | None = None) -> list[str]:
        resolved = Path(path).resolve()
        with self.read_connection() as connection:
            rows = connection.execute(
                "SELECT r.owner_type,r.owner_id,s.snapshot_json FROM analysis_source_refs r JOIN analysis_sources s ON s.source_id=r.source_id").fetchall()
        return sorted({row[0] + ":" + row[1] for row in rows
                       if (row[0], row[1]) != ("job", excluding_job)
                       and any(Path(value).resolve() == resolved or Path(value).resolve().is_relative_to(resolved)
                               for key, value in json.loads(row[2]).items()
                               if key in {"media_path", "sidecar_path", "timing_path"} and value)})

    def unlink_job(self, job_id: str):
        with self.transaction() as connection:
            connection.execute("DELETE FROM analysis_job_artifact_refs WHERE job_id=?", (job_id,))
            connection.execute("DELETE FROM analysis_source_refs WHERE owner_type='job' AND owner_id=?", (job_id,))
            connection.execute("DELETE FROM analysis_module_results WHERE job_id=?", (job_id,))

    def retention(self):
        with self.read_connection() as connection:
            ids = {r[0] for r in connection.execute("SELECT artifact_id FROM analysis_artifacts")}
            roots = {r[0] for r in connection.execute("SELECT artifact_id FROM analysis_job_artifact_refs")}
            edges = list(connection.execute("SELECT consumer_artifact_id,input_artifact_id FROM analysis_artifact_edges"))
        live = set(roots)
        while True:
            expanded = live | {r[1] for r in edges if r[0] in live}
            if expanded == live:
                break
            live = expanded
        physical = {p.name for p in self.root.glob("artifact-*")} if self.root.exists() else set()
        return {"referenced": sorted(live), "eligible_unreferenced": sorted(ids-live),
                "orphans": sorted(physical-ids), "policy": "retain_shared_v1"}
