"""模块合同/规划/发布的纯 fixture 验证，不作为真实推理证据。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis_runtime.artifact_store import ArtifactStore
from app.analysis_runtime.contracts import (
    AnalysisRequest, CapabilitySpec, ImplementationSpec, InputSpec, ModelSnapshot,
    NodeRun, SourceSnapshot, Window,
)
from app.analysis_runtime.hashing import AnalysisRuntimeError, file_digest
from app.analysis_runtime.planner import Planner, cache_key, verify_plan
from app.analysis_runtime.registry import builtin_registry
from app.analysis_runtime.windows import selected
from app.services.analysis_control_plane import AnalysisControlPlane


@pytest.fixture
def runtime(tmp_path):
    control = AnalysisControlPlane(tmp_path / "control.sqlite")
    store = ArtifactStore(control, tmp_path / "shared")
    media = tmp_path / "fixture.media"
    media.write_bytes(b"fixture, not real video")
    timing = tmp_path / "timing.json"
    timing.write_text("[]\n")
    source = SourceSnapshot(
        source_id="source-fixture", view_id="cam_1", camera_id="camera-1",
        media_path=str(media), media_sha256=file_digest(media),
        timing_path=str(timing), timing_sha256=file_digest(timing),
        timing_authority="legacy_nominal_fps", frame_count=900, fps=30,
        duration_ms=30000, width=640, height=360,
    )
    store.register_source(source)
    registry = builtin_registry()
    for impl_id in registry.implementations:
        store.register_model(ModelSnapshot(implementation_id=impl_id))
    planner = Planner(registry, store.source, store.model, store.manifest, store.cached)
    return store, registry, planner, source


def request(**updates):
    data = {"source_ids": ["source-fixture"], "targets": ["ball.detect"], "window": {"start_ms": 2000, "end_ms": 4000}}
    data.update(updates)
    return AnalysisRequest.model_validate(data)


def running_job(store, plan, job_id="job-fixture", run_id="worker-1"):
    job = SimpleNamespace(id=job_id, workerRunId=run_id, attempt=1)
    store.control_plane.upsert({
        "id": job_id, "canonicalStatus": "running", "workerRunId": run_id, "attempt": 1,
    })
    return job


def test_minimal_closure_stable_hash_and_unused_context(runtime):
    _store, _registry, planner, _source = runtime
    a, b = planner.plan(request()), planner.plan(request(context={"values": {"score": "new", "roster": {"P1": "different"}}}))
    assert [n.capability_id for n in a.nodes] == ["ball.detect"]
    assert a.plan_id != b.plan_id and a.created_at != b.created_at
    assert a.plan_hash == b.plan_hash
    assert a.nodes[0].compute_window == a.requested_window
    verify_plan(a)
    with pytest.raises(AnalysisRuntimeError, match="冻结"):
        verify_plan(a.model_copy(update={"failure_policy": "best_effort"}))


def test_parameter_sampling_and_policy_invalidate_only_affected_node(runtime):
    _store, _registry, planner, _source = runtime
    targets = ["ball.detect", "pose.sequence"]
    a = planner.plan(request(targets=targets))
    b = planner.plan(request(targets=targets, parameters={"pose.sequence": {"confidence": 0.45}}))
    nodes_a, nodes_b = {n.node_key: n for n in a.nodes}, {n.node_key: n for n in b.nodes}
    assert a.plan_hash != b.plan_hash
    for cap in ["ball.detect", "player.detect"]:
        assert cache_key(a, nodes_a[cap], {}) == cache_key(b, nodes_b[cap], {})
    assert nodes_a["pose.sequence"].parameters != nodes_b["pose.sequence"].parameters
    assert planner.plan(request(sampling={"stride": 2, "phase": 0})).plan_hash != planner.plan(request(sampling={"stride": 2, "phase": 1})).plan_hash
    assert planner.plan(request(failure_policy="best_effort")).plan_hash != planner.plan(request()).plan_hash


def test_missing_preparation_and_planned_target_are_explicit(runtime):
    store, registry, planner, _source = runtime
    for cap in ["racket.detect", "shot.semantic"]:
        with pytest.raises(AnalysisRuntimeError) as error:
            planner.plan(request(targets=[cap]))
        assert error.value.code == "capability_not_implemented"
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(source_ids=["unknown"]))
    assert error.value.code == "preparation_required"
    assert len(registry.capabilities) == 24


def test_window_backpropagation_cumulative_budget_and_selection(runtime):
    store, registry, planner, _source = runtime
    pose = ImplementationSpec(
        implementation_id="fixture.swing.pose", capability_id="swing.segment", output_type="swing",
        inputs=(InputSpec(name="pose", capability_id="pose.sequence", artifact_type="pose.observations"),),
        pre_roll_ms=1500, post_roll_ms=500, selector="contact_time.v1", resources=(),
    )
    # fixture 替换 planned 声明，生产 Registry 保持 planned。
    registry.capabilities.pop("swing.segment")
    registry.register(CapabilitySpec(capability_id="swing.segment", status="implemented", implementations=(pose.implementation_id,)), (pose,))
    plan = planner.plan(request(targets=["swing.segment"], window={"start_ms": 4200, "end_ms": 7200}))
    upstream = {n.node_key: n for n in plan.nodes}
    assert upstream["pose.sequence"].output_window.start_ms == 2700
    assert upstream["player.detect"].effective_window.start_ms == 2700
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(targets=["swing.segment"], context_budget={"before_ms": 1000, "after_ms": 1000}))
    assert error.value.code == "window_budget_exceeded"
    assert selected({"start_ms": 41000, "contact_ms": 43000, "end_ms": 44000}, Window(start_ms=42000, end_ms=72000), "contact_time.v1")


def test_cycle_schema_and_unknown_parameter_rejected(runtime):
    _store, registry, planner, _source = runtime
    impl = registry.implementations["player.yolo.v1"]
    registry.implementations[impl.implementation_id] = impl.model_copy(update={"inputs": (InputSpec(name="self", capability_id="player.detect", artifact_type="player.observations"),)})
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(targets=["player.detect"]))
    assert error.value.code == "dependency_cycle"
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(parameters={"ball.detect": {"unknown": 1}}))
    assert error.value.code == "unknown_parameter"


def publish_fixture(store, planner, job_id="job-fixture"):
    plan = planner.plan(request())
    node = plan.nodes[0]
    job = running_job(store, plan, job_id)
    run = NodeRun(node_key=node.node_key, capability_id=node.capability_id, status="running", node_attempt=1)
    key = cache_key(plan, node, {})
    completed = store.publish(job, plan, node, key, {"observations": []}, run)
    return plan, job, node, key, completed


def test_no_candidates_cache_shared_references_and_corrupt_rebuild(runtime):
    store, _registry, planner, _source = runtime
    plan, job, node, key, completed = publish_fixture(store, planner)
    a = store.manifest(completed.artifact.artifact_id)
    assert a.quality == "no_candidates"
    assert store.cached(key).ref == a.ref
    second_job = running_job(store, plan, "job-second")
    cached = completed.model_copy(update={"status": "cached", "node_attempt": 0})
    store.bind_cached(second_job, cached)
    store.unlink_job(job.id)
    assert store.payload(a.ref) == {"observations": []}
    assert a.ref.artifact_id in store.retention()["referenced"]
    store.path(a).write_text("damaged")
    assert store.cached(key) is None
    rebuilt = store.publish(second_job, plan, node, key, {"observations": []}, completed.model_copy(update={"node_attempt": 2}))
    assert rebuilt.artifact != a.ref
    assert store.cached(key).ref == rebuilt.artifact
    assert store.manifest(a.ref.artifact_id).ref == a.ref


def test_atomic_publication_orphan_and_late_lease(runtime):
    store, _registry, planner, _source = runtime
    plan = planner.plan(request())
    node = plan.nodes[0]
    job = running_job(store, plan)
    run = NodeRun(node_key=node.node_key, capability_id=node.capability_id, status="running", node_attempt=1)
    key = cache_key(plan, node, {})

    def crash(where):
        if where == "after_finalize":
            raise RuntimeError("fixture crash")
    with pytest.raises(RuntimeError, match="fixture crash"):
        store.publish(job, plan, node, key, {"observations": []}, run, fault=crash)
    assert store.cached(key) is None
    assert len(store.retention()["orphans"]) == 1
    store.control_plane.upsert({"id": job.id, "canonicalStatus": "running", "workerRunId": "new-lease", "attempt": 2})
    from app.services.job_orchestration import WorkerLeaseLostError
    with pytest.raises(WorkerLeaseLostError):
        store.publish(job, plan, node, key, {"observations": []}, run)
    assert store.cached(key) is None


def test_preview_does_not_write_or_load_models(runtime, monkeypatch):
    store, _registry, planner, _source = runtime
    def forbidden(*args, **kwargs):
        raise AssertionError("preview mutated state")
    monkeypatch.setattr(store, "transaction", forbidden)
    plan = planner.plan(request())
    assert plan.cache_hints["ball.detect"]["decision"] == "miss"
    with store.read_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM analysis_plans").fetchone()[0] == 0


def test_source_replacement_rejected(runtime):
    from app.analysis_runtime.sources import verify_sources
    _store, _registry, _planner, source = runtime
    verify_sources((source,))
    Path(source.media_path).write_bytes(b"same path, replaced")
    with pytest.raises(AnalysisRuntimeError) as error:
        verify_sources((source,))
    assert error.value.code == "source_revision_mismatch"

def module_jobs(runtime, isolated_settings):
    from app.services.job_orchestration import JobStore
    from app.services.storage_service import StorageService
    store, _registry, _planner, _source = runtime
    settings = isolated_settings.model_copy(update={
        "analysis_control_database_path": store.control_plane.path,
        "modular_artifacts_dir": store.root,
        "analysis_worker_heartbeat_interval_seconds": 1,
    })
    return JobStore(StorageService(settings))


def metadata():
    from app.schemas.analysis import AnalysisUploadMetadata
    return AnalysisUploadMetadata(fileName="fixture",matchTitle="fixture",venue="",matchDate="2026-10-17",
                                  matchFormat="doubles",cameraAngle="unknown",athleteLabel="",level="")


def make_worker(jobs, monkeypatch, calls, *, fail=None, cancel=None):
    from app.services.job_orchestration import AnalysisWorkerRuntime
    from app.analysis_capabilities import runner as adapters
    def fixture_runner(plan, node, inputs, counters, check):
        calls.append(node.node_key)
        if cancel and cancel(node):
            job_id = jobs.list()[-1].id
            jobs.cancel(job_id)
            check()
        if fail and fail(node):
            raise RuntimeError("fixture failure")
        counters["model_executions"] += 1
        return {"observations": []}
    monkeypatch.setattr(adapters, "run_capability", fixture_runner)
    def forbidden(*a, **kw):
        raise AssertionError("legacy pipeline/report invoked")
    worker = AnalysisWorkerRuntime(jobs, pipeline_factory=forbidden, on_completed=forbidden)
    worker.settings = jobs.storage.settings
    return worker


def test_worker_completion_cache_narrow_rerun_and_trace(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime.service import submit, inspect_run
    jobs = module_jobs(runtime, isolated_settings)
    calls = []
    worker = make_worker(jobs, monkeypatch, calls)
    req = request(targets=["ball.detect","pose.sequence"])
    job = submit(jobs, req, metadata())
    assert job.stages == [] and job.reportId is None and jobs.is_runnable(job)
    result = worker.run_job(job.id)
    assert result.canonicalStatus == "succeeded"
    assert set(calls) == {"ball.detect","player.detect","pose.sequence"}
    assert result.stages == [] and result.reportId is None
    cached = submit(jobs, req.model_copy(update={"new_version": True}), metadata())
    calls.clear()
    worker.run_job(cached.id)
    assert calls == []
    manifest = inspect_run(jobs, cached.id)
    assert {r["status"] for r in manifest["nodes"]} == {"cached"}
    assert all(r["counters"]["capture_opens"] == 0 for r in manifest["nodes"])
    changed = submit(jobs, req.model_copy(update={"parameters":{"pose.sequence":{"confidence":0.5}}}), metadata())
    worker.run_job(changed.id)
    assert calls == ["pose.sequence"]
    trace = jobs.storage.resolve_run_trace_path(changed.id, None)
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert all(e["schema_version"] == "analysis-run-trace.v2" for e in events)
    assert any(e.get("outcome")=="cached" for e in events)
    assert [e["seq"] for e in events] == sorted({e["seq"] for e in events})


@pytest.mark.parametrize("policy,expected", [("all_targets","failed"),("best_effort","succeeded")])
def test_independent_failure_policy_preserves_outputs(runtime, isolated_settings, monkeypatch, policy, expected):
    from app.analysis_runtime.service import submit, inspect_run
    jobs = module_jobs(runtime, isolated_settings)
    calls = []
    worker = make_worker(jobs, monkeypatch, calls, fail=lambda node: node.capability_id=="ball.detect")
    job = submit(jobs, request(targets=["ball.detect","player.detect"], failure_policy=policy), metadata())
    result = worker.run_job(job.id)
    assert result.canonicalStatus == expected
    assert calls == ["ball.detect","player.detect"]
    value = inspect_run(jobs, job.id)
    assert value["completeness"] == "partial"
    assert len(value["artifacts"]) == 1
    assert result.failureEvidence is not None


def test_failure_blocks_required_pose_and_explicit_resume_reuses_frozen_plan(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime.service import submit, inspect_run, resume
    jobs = module_jobs(runtime, isolated_settings)
    calls, state = [], {"fail":True}
    worker = make_worker(jobs, monkeypatch, calls, fail=lambda node: state["fail"] and node.capability_id=="player.detect")
    job = submit(jobs, request(targets=["pose.sequence","ball.detect"]), metadata())
    failed = worker.run_job(job.id)
    assert failed.canonicalStatus=="failed" and "pose.sequence" not in calls
    assert any(r["status"]=="blocked" for r in inspect_run(jobs,job.id)["nodes"])
    state["fail"] = False
    resumed = resume(jobs, job.id)
    assert resumed.planHash==job.planHash and resumed.planId==job.planId
    calls.clear()
    completed = worker.run_job(job.id)
    assert completed.canonicalStatus=="succeeded" and completed.attempt==2
    assert calls==["player.detect","pose.sequence"]
    assert completed.failureEvidence==failed.failureEvidence


def test_module_cancel_keeps_published_branch(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime.service import submit, inspect_run
    jobs = module_jobs(runtime, isolated_settings)
    calls = []
    worker = make_worker(jobs, monkeypatch, calls, cancel=lambda node: node.capability_id=="player.detect")
    job = submit(jobs, request(targets=["ball.detect","player.detect"]), metadata())
    result = worker.run_job(job.id)
    assert result.canonicalStatus=="canceled"
    manifest = inspect_run(jobs,job.id)
    assert manifest["status"]=="canceled" and manifest["completeness"]=="partial"
    assert len(manifest["artifacts"])==1
    assert any(r["status"]=="canceled" for r in manifest["nodes"])


def test_disabled_submission_does_not_remove_reader(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime.service import submit, inspect_run
    jobs = module_jobs(runtime, isolated_settings)
    job = submit(jobs,request(),metadata())
    jobs.storage.settings.modular_analysis_enabled = False
    with pytest.raises(AnalysisRuntimeError) as error:
        submit(jobs, request(new_version=True), metadata())
    assert error.value.code=="modular_submission_disabled"
    assert inspect_run(jobs,job.id)["status"]=="queued"


def test_api_preview_and_module_submission_share_contract(runtime, isolated_settings, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import mock_analysis
    from app.api import routes_analysis_modules
    jobs = module_jobs(runtime, isolated_settings)
    monkeypatch.setattr(mock_analysis,"_JOB_STORE",jobs)
    monkeypatch.setattr(mock_analysis,"_STORAGE",jobs.storage)
    monkeypatch.setattr(mock_analysis,"_WORKER",None)
    monkeypatch.setattr(routes_analysis_modules,"jobs",lambda: jobs)
    client=TestClient(app)
    req=request()
    preview=client.post("/api/analysis/plans/preview",json=req.model_dump(mode="json"))
    assert preview.status_code==200,preview.text
    assert preview.json()["plan_hash"]==runtime[2].plan(req).plan_hash
    with jobs.control_plane._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM analysis_jobs").fetchone()[0]==0
    created=client.post("/api/analysis/jobs",json={"metadata":metadata().model_dump(),"analysisEngine":"modular_v1","modularRequest":req.model_dump(mode="json")})
    assert created.status_code==200,created.text
    job_id=created.json()["id"]
    manifest=client.get("/api/analysis/jobs/"+job_id+"/manifest")
    assert manifest.status_code==200 and manifest.json()["status"]=="queued"
    version=client.post("/api/analysis/jobs",json={"metadata":metadata().model_dump(),"analysisEngine":"modular_v1",
                        "modularRequest":req.model_dump(mode="json"),"requestNewVersion":True})
    assert version.status_code==200 and version.json()["id"]!=job_id
    assert version.json()["previousJobId"]==job_id and version.json()["analysisVersion"]==2
    unavailable=client.post("/api/analysis/jobs",json={"metadata":metadata().model_dump(),"analysisEngine":"modular_v1","modularRequest":request(targets=["racket.detect"]).model_dump(mode="json")})
    assert unavailable.status_code==400 and unavailable.json()["code"]=="capability_not_implemented"


def test_same_key_concurrent_publish_and_indirect_lineage(runtime):
    from concurrent.futures import ThreadPoolExecutor
    store,_registry,planner,_source=runtime
    plan=planner.plan(request())
    node=plan.nodes[0]
    jobs=[running_job(store,plan,"job-concurrent-"+str(i)) for i in range(2)]
    key=cache_key(plan,node,{})
    run=NodeRun(node_key=node.node_key,capability_id=node.capability_id,status="running",node_attempt=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda job:store.publish(job,plan,node,key,{"observations":[]},run),jobs))
    assert len({r.artifact.artifact_id for r in results})==2
    assert store.cached(key).ref in [r.artifact for r in results]
    upstream=store.manifest(results[0].artifact.artifact_id)
    # fixture 派生产物引用上游，存活 Job 只直接引用派生结果。
    derived=store.publish(jobs[1],plan,node,key+"derived",{"observations":[]},run.model_copy(update={"node_attempt":2}),
                          actual_inputs={"evidence":upstream})
    store.unlink_job(jobs[0].id)
    with store.transaction() as connection:
        connection.execute("DELETE FROM analysis_job_artifact_refs WHERE artifact_id=?", (upstream.ref.artifact_id,))
    assert upstream.ref.artifact_id in store.retention()["referenced"]
    assert store.source_pins(Path(runtime[3].media_path))


def fixture_implementation(registry, cap_id, impl_id, output, *, inputs=(), **kwargs):
    registry.capabilities.pop(cap_id, None)
    impl=ImplementationSpec(implementation_id=impl_id,capability_id=cap_id,output_type=output,
                            inputs=tuple(inputs),resources=(),**kwargs)
    registry.register(CapabilitySpec(capability_id=cap_id,status="implemented",implementations=(impl_id,)),(impl,))
    return impl


def test_alternative_classifiers_and_future_domain_contracts(runtime):
    store,registry,planner,source=runtime
    registry.capabilities.pop("stroke.classify")
    variants=(
        ImplementationSpec(implementation_id="fixture.stroke.rgb",capability_id="stroke.classify",
                           output_type="stroke.attributes",resources=("decode",),taxonomy_version="stroke.v1"),
        ImplementationSpec(implementation_id="fixture.stroke.pose",capability_id="stroke.classify",
                           output_type="stroke.attributes",resources=(),taxonomy_version="stroke.v1",
                           inputs=(InputSpec(name="pose",capability_id="pose.sequence",artifact_type="pose.observations"),)),
        ImplementationSpec(implementation_id="fixture.stroke.multi",capability_id="stroke.classify",
                           output_type="stroke.attributes",resources=(),taxonomy_version="stroke.v1",
                           inputs=(InputSpec(name="pose",capability_id="pose.sequence",artifact_type="pose.observations"),
                                   InputSpec(name="racket",capability_id="racket.detect",artifact_type="racket.observations"))),
    )
    registry.register(CapabilitySpec(capability_id="stroke.classify",status="implemented",
                                    implementations=tuple(i.implementation_id for i in variants)),variants)
    fixture_implementation(registry,"racket.detect","fixture.racket","racket.observations")
    fixture_implementation(registry,"racket.player_association","fixture.racket.person","racket.associations",
        inputs=[InputSpec(name="racket",capability_id="racket.detect",artifact_type="racket.observations"),
                InputSpec(name="players",capability_id="player.detect",artifact_type="player.observations")])
    fixture_implementation(registry,"motion.upper_limb","fixture.motion","motion.upper_limb_evidence",units="px/s",
        inputs=[InputSpec(name="pose",capability_id="pose.sequence",artifact_type="pose.observations")])
    fixture_implementation(registry,"context.rally","fixture.rally","rally.context",
                           consumed_context=("media","frame_time","rally"))
    for impl,expected in [
        ("fixture.stroke.rgb",{"stroke.classify"}),
        ("fixture.stroke.pose",{"stroke.classify","pose.sequence","player.detect"}),
        ("fixture.stroke.multi",{"stroke.classify","pose.sequence","player.detect","racket.detect"}),
    ]:
        plan=planner.plan(request(targets=["stroke.classify"],implementations={"stroke.classify":impl}))
        assert {n.capability_id for n in plan.nodes}==expected
    plan=planner.plan(request(targets=["racket.player_association","motion.upper_limb"]))
    assert {n.capability_id for n in plan.nodes}=={"racket.detect","player.detect","racket.player_association","pose.sequence","motion.upper_limb"}
    assert next(n for n in plan.nodes if n.capability_id=="motion.upper_limb").implementation.units=="px/s"
    a=planner.plan(request(targets=["context.rally"],context={"values":{"rally":{"stage":"third"},"score":1}}))
    b=planner.plan(request(targets=["context.rally"],context={"values":{"rally":{"stage":"return"},"score":1}}))
    assert a.plan_hash!=b.plan_hash
    assert builtin_registry().capabilities["stroke.classify"].status=="planned"


def test_event_constrained_reconstruction_dag_and_semantic_versions(runtime):
    store,registry,planner,_source=runtime
    fixture_implementation(registry,"ball.clean_2d","fixture.clean","ball.cleaned_2d",
        inputs=[InputSpec(name="raw",capability_id="ball.detect",artifact_type="ball.observations_2d")])
    fixture_implementation(registry,"contact.detect","fixture.contact","contact.candidates",
        inputs=[InputSpec(name="clean",capability_id="ball.clean_2d",artifact_type="ball.cleaned_2d")])
    fixture_implementation(registry,"ball.events","fixture.events","ball.events",
        inputs=[InputSpec(name="contact",capability_id="contact.detect",artifact_type="contact.candidates")])
    fixture_implementation(registry,"ball.reconstruct_3d","fixture.reconstruction","ball.reconstructed_3d",
        inputs=[InputSpec(name="clean",capability_id="ball.clean_2d",artifact_type="ball.cleaned_2d"),
                InputSpec(name="events",capability_id="ball.events",artifact_type="ball.events")])
    fixture_implementation(registry,"shot.assemble","fixture.shot","shot.events",
        inputs=[InputSpec(name="contact",capability_id="contact.detect",artifact_type="contact.candidates")])
    fixture_implementation(registry,"shot.landing","fixture.landing","shot.landings",
        inputs=[InputSpec(name="shot",capability_id="shot.assemble",artifact_type="shot.events")])
    fixture_implementation(registry,"shot.semantic","fixture.semantic","shot.semantic",
        inputs=[InputSpec(name="landing",capability_id="shot.landing",artifact_type="shot.landings")],
        taxonomy_version="semantic.v1",consumed_context=("media","frame_time","rally","calibration"))
    fixture_implementation(registry,"tactics.analyze","fixture.tactics","tactics",
        inputs=[InputSpec(name="semantic",capability_id="shot.semantic",artifact_type="shot.semantic")])
    context={"values":{"rally":{"stage":"third"},"calibration":{"revision":1}}}
    a=planner.plan(request(targets=["ball.reconstruct_3d","tactics.analyze"],context=context))
    order=[n.node_key for n in a.nodes]
    assert order.index("ball.events")<order.index("ball.reconstruct_3d")
    registry.implementations["fixture.semantic"]=registry.implementations["fixture.semantic"].model_copy(update={"version":"2"})
    b=planner.plan(request(targets=["ball.reconstruct_3d","tactics.analyze"],context=context))
    assert a.plan_hash!=b.plan_hash
    na,nb={n.node_key:n for n in a.nodes},{n.node_key:n for n in b.nodes}
    assert cache_key(a,na["ball.clean_2d"],{})==cache_key(b,nb["ball.clean_2d"],{})
    registry.implementations["fixture.events"]=registry.implementations["fixture.events"].model_copy(update={
        "inputs":(InputSpec(name="wrong_cycle",capability_id="ball.reconstruct_3d",artifact_type="ball.reconstructed_3d"),)})
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(targets=["ball.reconstruct_3d"]))
    assert error.value.code=="dependency_cycle"


def test_fixed_inputs_and_strict_association_scope(runtime):
    from app.analysis_runtime.association import resolve_object,validate_association
    from app.analysis_runtime.contracts import Association,AssociationCandidate,ObjectRef,StrokeAttributes
    store,registry,planner,source=runtime
    plan=planner.plan(request(targets=["player.detect"]))
    job=running_job(store,plan)
    node=plan.nodes[0]
    run=NodeRun(node_key=node.node_key,capability_id=node.capability_id,status="running",node_attempt=1)
    payload={"observations":[{"view_id":"cam_1","source_frame_index":60,"canonical_time_ms":2000,
                              "subjects":[{"observation_id":"person-1","bbox":[1,2,3,4],"confidence":0.9}]}]}
    completed=store.publish(job,plan,node,cache_key(plan,node,{}),payload,run)
    downstream=planner.plan(request(targets=["pose.sequence"],fixed_inputs={"pose.sequence:players":completed.artifact.model_dump()}))
    assert [n.capability_id for n in downstream.nodes]==["pose.sequence"]
    ref=ObjectRef(artifact_id=completed.artifact.artifact_id,object_type="player.observation",local_id="person-1",
                  subject_scope="observation",view_id="cam_1",epoch=source.media_sha256)
    assert resolve_object(store,ref)["observation_id"]=="person-1"
    before=store.manifest(ref.artifact_id).content_sha256
    relation=Association(relation_type="fixture.swing.contact",implementation_id="fixture.relation",implementation_version="1",
                         status="ambiguous",candidates=(
                             AssociationCandidate(source=ref,target=ref,score=0.8,temporal_delta_ms=10,constraints={"max_delta_ms":20}),
                             AssociationCandidate(source=ref,target=ref,score=0.7,temporal_delta_ms=15,constraints={"max_delta_ms":20})))
    assert validate_association(store,relation).status=="ambiguous"
    with pytest.raises(AnalysisRuntimeError) as error:
        resolve_object(store,ref.model_copy(update={"local_id":"missing-contact"}))
    assert error.value.code=="association_object_unresolved"
    with pytest.raises(AnalysisRuntimeError) as error:
        resolve_object(store,ref.model_copy(update={"view_id":"cam_2"}))
    assert error.value.code=="association_scope_mismatch"
    attr=StrokeAttributes(taxonomy_version="fixture.v1",stage="third",stroke_form="backhand",semantic="dink",
                          is_volley=False,confidence=0.99,evidence_sufficiency="insufficient_evidence",evidence=(ref,))
    assert attr.stage!=attr.semantic and attr.evidence_sufficiency!="sufficient"
    assert store.manifest(ref.artifact_id).content_sha256==before


def test_optional_failure_node_retry_and_monotonic_progress(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime import service
    store,registry,planner,_source=runtime
    fixture_implementation(registry,"shot.semantic","fixture.optional","shot.semantic",
        inputs=[InputSpec(name="players",capability_id="player.detect",artifact_type="player.observations"),
                InputSpec(name="ball",capability_id="ball.detect",artifact_type="ball.observations_2d",required=False)])
    monkeypatch.setattr(service,"builtin_registry",lambda:registry)
    jobs=module_jobs(runtime,isolated_settings)
    calls=[]
    worker=make_worker(jobs,monkeypatch,calls,fail=lambda node:node.capability_id=="ball.detect")
    job=service.submit(jobs,request(targets=["shot.semantic"],optional_inputs=["shot.semantic:ball"]),metadata())
    result=worker.run_job(job.id)
    assert result.canonicalStatus=="succeeded" and calls[-1]=="shot.semantic" and set(calls)=={"ball.detect","player.detect","shot.semantic"}
    # pose 在节点内重试一次，不能重跑已发布人框/球，也不能提前显示 100%。
    registry.implementations["pose.rtmpose26.v1"]=registry.implementations["pose.rtmpose26.v1"].model_copy(update={"max_retries":1})
    attempts={"pose":0}
    def once(node):
        if node.capability_id!="pose.sequence":return False
        attempts["pose"]+=1
        return attempts["pose"]==1
    worker=make_worker(jobs,monkeypatch,calls,fail=once)
    job=service.submit(jobs,request(targets=["pose.sequence"]),metadata())
    updates=[]
    original=jobs.update
    def tracking(job_id,**kwargs):
        if "progress" in kwargs:updates.append(kwargs["progress"])
        return original(job_id,**kwargs)
    monkeypatch.setattr(jobs,"update",tracking)
    calls.clear()
    result=worker.run_job(job.id)
    assert calls==["pose.sequence","pose.sequence"]  # 人框来自上一个 Job 的兼容缓存。
    assert result.attempt==1 and len(result.retryHistory)==1
    assert next(r for r in result.nodeRuns if r.capability_id=="pose.sequence").node_attempt==2
    assert updates==sorted(updates) and all(p<100 for p in updates[:-1])


def test_offline_location_and_delete_keep_shared_evidence(runtime, isolated_settings, monkeypatch):
    from app.analysis_runtime.service import submit,inspect_run
    from app.analysis_runtime.retention import references
    from app.services import mock_analysis
    store,_registry,planner,source=runtime
    jobs=module_jobs(runtime,isolated_settings)
    calls=[]
    worker=make_worker(jobs,monkeypatch,calls)
    first=submit(jobs,request(),metadata());worker.run_job(first.id)
    second=submit(jobs,request(new_version=True),metadata());worker.run_job(second.id)
    artifact=store.manifest(inspect_run(jobs,second.id)["artifacts"][0]["artifact_id"])
    offline=store.root.with_name("offline")
    store.root.rename(offline)
    try:
        assert store.availability(artifact)=="location_unavailable"
        assert store.cached(artifact.cache_key) is None
        with pytest.raises(AnalysisRuntimeError) as error:store.prepare_publish_location()
        assert error.value.code=="location_unavailable"
        assert not store.root.exists()
    finally:offline.rename(store.root)
    monkeypatch.setattr(mock_analysis,"_JOB_STORE",jobs)
    monkeypatch.setattr(mock_analysis,"_STORAGE",jobs.storage)
    monkeypatch.setattr(mock_analysis,"_WORKER",None)
    result=mock_analysis.delete_analysis_job(first.id)
    assert result.status=="deleted"
    assert store.payload(artifact.ref)=={"observations":[]}
    assert references(jobs.storage.settings,path=Path(source.media_path))
    # 无 video_id 的 CLI 来源仍应通过实际路径保留，不能绕过引用保护。
    jobs.storage.write_json_atomic(jobs.storage.video_metadata_path("fixture-video"),{"path":source.media_path})
    mock_analysis._cleanup_shared_video_artifacts("fixture-video")
    assert Path(source.media_path).is_file()


def test_cli_preview_is_readonly_and_matches_api_contract(runtime, isolated_settings, monkeypatch, tmp_path, capsys):
    import importlib.util
    from app.analysis_runtime import artifact_store as store_module
    jobs=module_jobs(runtime,isolated_settings)
    script=Path(__file__).parents[1]/"scripts"/"analysis_dev.py"
    spec=importlib.util.spec_from_file_location("fixture_analysis_cli",script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,"get_settings",lambda:jobs.storage.settings)
    path=tmp_path/"request.json";req=request()
    path.write_text(req.model_dump_json())
    def forbidden(*a,**kw):raise AssertionError("CLI preview wrote state")
    monkeypatch.setattr(store_module.ArtifactStore,"transaction",forbidden)
    assert module.main(["plan","--request",str(path)])==0
    output=json.loads(capsys.readouterr().out)
    assert output["plan_hash"]==runtime[2].plan(req).plan_hash


def dual_fixture(runtime):
    store,registry,planner,source=runtime
    ref_path=Path(source.timing_path)
    ref_path.write_text(json.dumps([{"frame_index":i,"pts_seconds":i/100,"dts_seconds":None,"keyframe":i==0}for i in range(4)]))
    ref=source.model_copy(update={"source_id":"source-ref","fps":100,"duration_ms":40,"frame_count":4,
                                 "timing_authority":"source_pts","timing_sha256":file_digest(ref_path)})
    sec_path=ref_path.with_name("secondary.json")
    sec_path.write_text(json.dumps([{"frame_index":i,"pts_seconds":i/20,"dts_seconds":None,"keyframe":i==0}for i in range(3)]))
    sec=source.model_copy(update={"source_id":"source-sec","view_id":"cam_2","camera_id":"camera-2",
                                 "fps":20,"duration_ms":150,"frame_count":3,"timing_path":str(sec_path),
                                 "timing_authority":"source_pts","timing_sha256":file_digest(sec_path)})
    store.register_source(ref);store.register_source(sec)
    sync={"schema_version":"dual_camera_sync_calibration.v1","reference_camera":"camera-1",
          "anchor_count":3,"source":"manual_anchors","anchor_validation":{"valid":True},
          "mappings":{"camera-2":{"reference_camera":"camera-1","camera_id":"camera-2","offset_ms":0,
                                  "rate":1,"residual_rms_ms":0,"quality":"good","anchor_count":3,
                                  "valid_start_seconds":0,"valid_end_seconds":1}}}
    return planner.plan(request(source_ids=[ref.source_id,sec.source_id],sync=sync,window={"start_ms":0,"end_ms":40}))


def test_dual_clock_no_duplicate_and_explicit_degradation(runtime,monkeypatch):
    from app.analysis_runtime import resources
    plan=dual_fixture(runtime)
    counts={"capture_opens":0,"decoded_frames":0}
    consumed,closed=[],[]
    class Capture:
        def __init__(self,source,counters,check):self.source=source
        def read(self,index):
            consumed.append((self.source.view_id,index))
            return object()
        def close(self):closed.append(self.source.view_id)
    monkeypatch.setattr(resources,"BoundedCapture",Capture)
    rows=list(resources.iter_frames(plan,plan.nodes[0],counts,lambda:None))
    secondary=[index for view,index in consumed if view=="cam_2"]
    assert secondary==sorted(set(secondary))
    assert any(row["mapping_status"]=="no_new_frame" for _source,row,_frame in rows)
    assert set(closed)=={"cam_1","cam_2"}
    class Degrade(Capture):
        def read(self,index):
            if self.source.view_id=="cam_2":raise AnalysisRuntimeError("source_decode_failed","fixture secondary")
            return super().read(index)
    monkeypatch.setattr(resources,"BoundedCapture",Degrade)
    counts={"capture_opens":0,"decoded_frames":0}
    rows=list(resources.iter_frames(plan,plan.nodes[0],counts,lambda:None))
    assert counts["secondary_degraded"] and any(r["mapping_status"]=="unavailable_decode"for _,r,_ in rows)


def test_seek_failure_releases_without_full_video_fallback(runtime,monkeypatch):
    import cv2
    from app.analysis_runtime.resources import BoundedCapture
    state={"reads":0,"released":False}
    class Capture:
        def isOpened(self):return True
        def set(self,*args):return False
        def read(self):state["reads"]+=1;return False,None
        def release(self):state["released"]=True
    monkeypatch.setattr(cv2,"VideoCapture",lambda *_:Capture())
    capture=BoundedCapture(runtime[3],{"capture_opens":0},lambda:None)
    try:
        with pytest.raises(AnalysisRuntimeError) as error:capture.read(60)
        assert error.value.code=="window_seek_failed"
        assert state["reads"]==0
    finally:capture.close()
    assert state["released"]


def test_legacy_executor_preserves_persisted_inference_toggles(runtime,isolated_settings):
    from app.schemas.analysis import AnalysisJobCreate
    from app.services.analysis_executor_dispatch import SingleViewAnalysisExecutor
    jobs=module_jobs(runtime,isolated_settings)
    job=jobs.create_job(AnalysisJobCreate(metadata=metadata(),videoId="fixture-video",
                                        enableModelInference=False,enablePoseInference=True,useRallyContext=False))
    captured={}
    class Pipeline:
        def run(self,**kwargs):
            return "fixture-result"
    def factory(**kwargs):
        captured.update(kwargs)
        return Pipeline()
    result=SingleViewAnalysisExecutor(jobs,factory).execute(job,object(),lambda value:None)
    assert result=="fixture-result"
    assert captured["analysis_options"]=={"enable_model_inference":False,"enable_pose_inference":True}


def test_pose_observation_scope_preserves_pixels_and_does_not_carry_visibility(runtime,monkeypatch):
    import numpy as np
    from app.analysis_capabilities.pose.adapter import PoseSequenceAdapter
    from app.analysis_runtime.contracts import ModelAsset
    from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter
    store,registry,planner,source=runtime
    plan=planner.plan(request(targets=["pose.sequence"]))
    node=next(n for n in plan.nodes if n.capability_id=="pose.sequence")
    asset=ModelAsset(path="fixture",sha256="fixture")
    node=node.model_copy(update={"model":ModelSnapshot(implementation_id="pose.rtmpose26.v1",assets={"weights":asset,"config":asset})})
    score={"value":0.31}
    sample=lambda:SimpleNamespace(pred_instances=SimpleNamespace(
        keypoints=np.array([[[100.0,200.0]]*26]),keypoint_scores=np.array([[score["value"]]*26])))
    monkeypatch.setattr(RTMPose26Adapter,"_load_model",lambda self:object())
    monkeypatch.setattr(RTMPose26Adapter,"_inference_topdown",lambda self:lambda *a,**kw:[sample()])
    inputs={"players":{"observations":[
        {"view_id":"cam_1","source_frame_index":60,"subjects":[{"observation_id":"frame-60-person","bbox":[0,0,200,300],"confidence":0.9}]},
        {"view_id":"cam_1","source_frame_index":61,"subjects":[{"observation_id":"frame-61-other","bbox":[0,0,200,300],"confidence":0.9}]},
    ]}}
    adapter=PoseSequenceAdapter(node,inputs,{"model_executions":0})
    first=adapter.infer(source,{"view_id":"cam_1","source_frame_index":60,"canonical_time_ms":2000},np.zeros((360,640,3)))
    assert first["subjects"][0]["keypoints"][0]["x"]==100
    assert first["subjects"][0]["keypoints"][0]["y"]==200
    assert first["subjects"][0]["keypoints"][0]["visible"]
    score["value"]=0.25
    second=adapter.infer(source,{"view_id":"cam_1","source_frame_index":61,"canonical_time_ms":2033},np.zeros((360,640,3)))
    assert not second["subjects"][0]["keypoints"][0]["visible"]
    assert second["subjects"][0]["observation_id"]=="frame-61-other"
    assert len(adapter.model._visible_states)==1
    adapter.close()


def test_calibration_scope_is_local_to_metric_consumer_and_parameters_are_typed(runtime):
    from app.analysis_runtime.parameters import parameters_for
    _store,registry,planner,_source=runtime
    fixture_implementation(registry,"metric.fixture","fixture.metric","fixture.court_positions",
        coordinate_system="court_m",units="m",consumed_context=("media","frame_time","calibration"))
    calibration={"calibration_id":"fixture-calibration","revision":"1","valid_window":{"start_ms":0,"end_ms":1000},
                 "view_ids":["cam_1"],"coordinate_system":"court_m","units":"m"}
    with pytest.raises(AnalysisRuntimeError) as error:
        planner.plan(request(targets=["metric.fixture"],context={"values":{"calibration":calibration}}))
    assert error.value.code=="calibration_out_of_range"
    assert planner.plan(request(targets=["ball.detect"])).nodes[0].consumed_context.get("calibration") is None
    impl=ImplementationSpec(implementation_id="fixture.parameters",capability_id="fixture.parameters",output_type="fixture",
        parameter_defaults={"enabled":False,"mode":"pose","threshold":0.5},
        parameter_schema={"enabled":{"type":"boolean"},"mode":{"type":"string","enum":["pose","rgb"]},
                          "threshold":{"type":"number","minimum":0,"maximum":1}})
    assert parameters_for(impl,{"enabled":True,"mode":"rgb"})["enabled"] is True
    for extra in [{"enabled":1},{"mode":"unknown"},{"threshold":float("nan")}]:
        with pytest.raises(AnalysisRuntimeError):parameters_for(impl,extra)


def test_planned_catalog_schema_paths_are_real_and_lightweight():
    from importlib import import_module
    for capability in builtin_registry().capabilities.values():
        if capability.status=="planned":
            assert capability.output_types
            module,name=capability.schema_path.split(":")
            assert getattr(import_module(module),name).model_json_schema()


def test_queued_module_cancel_does_not_build_legacy_stages(runtime,isolated_settings):
    from app.analysis_runtime.service import submit,inspect_run
    jobs=module_jobs(runtime,isolated_settings)
    job=submit(jobs,request(),metadata())
    canceled,reason=jobs.cancel(job.id)
    assert reason=="canceled" and canceled.stages==[]
    assert canceled.canonicalStatus=="canceled"
    assert inspect_run(jobs,job.id)["nodes"][0]["status"]=="canceled"
