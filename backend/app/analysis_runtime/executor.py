"""冻结 DAG 的节点执行、缓存复用、有限重试与清单发布。"""
from __future__ import annotations

import time

from app.analysis_runtime.contracts import ArtifactRef, ModularRunManifest, NodeRun
from app.analysis_runtime.hashing import AnalysisRuntimeError, digest
from app.analysis_runtime.planner import cache_key, model_identity
from app.analysis_runtime.sources import verify_sources


class ModularAnalysisExecutor:
    def __init__(self, store, *, runner=None, sink=None, guard=None):
        self.jobs = store
        from app.analysis_runtime.service import artifact_store
        self.artifacts = artifact_store(store)
        self.runner = runner
        self.sink = sink
        self.guard = guard

    def execute(self, job, token, progress_callback):
        from app.services.job_orchestration import JobCanceledError, StageTimeoutError, WorkerLeaseLostError
        from app.services.analysis_failure_taxonomy import classify_failure
        from app.services.analysis_run_trace import describe_exception
        plan = self.artifacts.plan(job.planId)
        if plan is None or plan.plan_hash != job.planHash:
            raise AnalysisRuntimeError("plan_unavailable", "冻结计划不存在或身份不符")
        runs = {n.node_key: NodeRun(node_key=n.node_key, capability_id=n.capability_id,
                                  implementation_id=n.implementation.implementation_id, implementation_version=n.implementation.version,
                                  configuration_digest=digest({"parameters": n.parameters, "model": model_identity(n.model)})) for n in plan.nodes}

        def trace(event, node=None, **fields):
            if self.sink:
                self.sink.record(event, node.node_key if node else "modular",
                                 node_id=node.node_key if node else None,
                                 capability_id=node.capability_id if node else None,
                                 implementation_id=node.implementation.implementation_id if node else None, **fields)

        def check():
            token.raise_if_cancelled()
            if self.guard:
                self.guard()

        def manifest(status=None):
            completed = [key for key in plan.targets if runs[key].status in {"completed", "cached"}]
            completeness = "complete" if len(completed) == len(plan.targets) else "partial" if completed else "none"
            if status is None:
                status = "succeeded" if completeness == "complete" or (completed and plan.failure_policy == "best_effort") else "failed"
            return ModularRunManifest(job_id=job.id, plan_id=plan.plan_id, plan_hash=plan.plan_hash,
                                      status=status, completeness=completeness, targets=plan.targets,
                                      nodes=tuple(runs.values()), artifacts=tuple(r.artifact for r in runs.values() if r.artifact))

        try:
            check()
            verify_sources(plan.sources)
            for node in plan.nodes:
                check()
                actual, unavailable = {}, {}
                for name, binding in node.inputs.items():
                    upstream = self.artifacts.manifest(binding.artifact_id) if isinstance(binding, ArtifactRef) else (
                        self.artifacts.manifest(runs[binding].artifact.artifact_id) if runs[binding].artifact else None)
                    if upstream and self.artifacts.availability(upstream) == "available":
                        actual[name] = upstream
                    else:
                        unavailable[name] = "input_unavailable"
                if set(node.required_inputs) & set(unavailable):
                    run = runs[node.node_key].model_copy(update={"status": "blocked", "error_code": "required_input_unavailable",
                                                                 "message": "必需上游不可用"})
                    runs[node.node_key] = run
                    self.artifacts.record_node(job, run)
                    trace("end", node, node_attempt=0, outcome="blocked", upstream_failure=unavailable)
                    progress_callback(run)
                    continue
                key = cache_key(plan, node, actual)
                cached = self.artifacts.cached(key)
                if cached and cached.ref.artifact_type == node.implementation.output_type and cached.ref.schema_version == node.implementation.output_schema:
                    run = runs[node.node_key].model_copy(update={"status": "cached", "artifact": cached.ref,
                                                                 "counters": {"capture_opens": 0, "model_constructors": 0, "model_executions": 0}})
                    self.artifacts.bind_cached(job, run)
                    runs[node.node_key] = run
                    trace("start", node, node_attempt=0, cache_decision="hit")
                    trace("end", node, node_attempt=0, outcome="cached", artifact=cached.ref.model_dump(), counters=run.counters)
                    progress_callback(run)
                    continue
                for attempt in range(1, node.implementation.max_retries + 2):
                    counters = {"capture_opens": 0, "decoded_frames": 0, "sampled_frames": 0, "model_constructors": 0, "model_executions": 0}
                    started = time.monotonic()
                    run = runs[node.node_key].model_copy(update={"status": "running", "node_attempt": attempt, "counters": counters,
                                                                "error_code": None, "message": None, "internal_message": None, "diagnostics": {}})
                    runs[node.node_key] = run
                    self.artifacts.record_node(job, run)
                    progress_callback(run)
                    trace("start", node, node_attempt=attempt, cache_decision="miss",
                          actual_inputs={k: m.ref.model_dump() for k, m in actual.items()}, missing_optional=unavailable)
                    try:
                        self.artifacts.prepare_publish_location()
                        if "model" in node.implementation.resources:
                            from app.analysis_runtime.resources import configure_model_cache
                            configure_model_cache(self.jobs.storage.tmp_dir)
                        # 每次尝试重新核验输入，不能沿用损坏数据或有状态实例。
                        inputs = {name: self.artifacts.payload(m.ref) for name, m in actual.items()}
                        def node_check():
                            check()
                            timeout = self.jobs.storage.settings.job_stage_timeout_seconds
                            if timeout > 0 and time.monotonic()-started > timeout:
                                raise StageTimeoutError("模块节点超时: " + node.node_key)
                        runner = self.runner
                        if runner is None:
                            from app.analysis_capabilities.runner import run_capability
                            runner = run_capability
                        payload = runner(plan, node, inputs, counters, node_check)
                        node_check()
                        counters["duration_ms"] = round((time.monotonic()-started)*1000)
                        run = run.model_copy(update={"counters": counters})
                        run = self.artifacts.publish(job, plan, node, key, payload, run, actual_inputs=actual)
                        runs[node.node_key] = run
                        trace("end", node, node_attempt=attempt, outcome="completed", artifact=run.artifact.model_dump(), counters=counters)
                        progress_callback(run)
                        break
                    except (JobCanceledError, StageTimeoutError, WorkerLeaseLostError):
                        raise
                    except Exception as exc:
                        described = describe_exception(exc)
                        code = exc.code if isinstance(exc, AnalysisRuntimeError) else "node_execution_failed"
                        failure_class = ("model_environment" if code in {"model_environment", "model_revision_mismatch"} or isinstance(exc, ImportError)
                                         else classify_failure(exception_type=type(exc).__name__, message=str(exc)))
                        retry = attempt <= node.implementation.max_retries
                        trace("retry" if retry else "fail", node, node_attempt=attempt, outcome="failed", error_code=code,
                              failure_class=failure_class, retry_index=attempt, retry_limit=node.implementation.max_retries,
                              will_retry=retry, progress_before=0, progress_after=0, **described)
                        run = run.model_copy(update={"status": "failed", "error_code": code, "failure_class": failure_class,
                                                     "message": "节点执行失败，请检查输入和模型环境", "internal_message": str(exc), "counters": counters,
                                                     "diagnostics": described})
                        runs[node.node_key] = run
                        self.artifacts.record_node(job, run)
                        progress_callback(run)
                        if retry:
                            continue
                        break
            result = manifest()
            self.artifacts.save_result(job, result)
            return result
        except (JobCanceledError, StageTimeoutError, WorkerLeaseLostError) as exc:
            status = "canceled" if isinstance(exc, JobCanceledError) else "interrupted" if isinstance(exc, WorkerLeaseLostError) else "failed"
            runs = {key: run.model_copy(update={"status": "canceled" if status == "canceled" else "blocked"})
                    if run.status in {"pending", "running"} else run for key, run in runs.items()}
            # 旧租约/取消不能发布，Worker 会从已提交节点重建部分清单。
            raise
