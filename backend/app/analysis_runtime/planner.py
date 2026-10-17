"""同一规划器供 CLI/API 使用；只读准备索引，不打开媒体或模型。"""
from __future__ import annotations

import json
from typing import Callable

from app.analysis_runtime.contracts import (
    AnalysisPlan, AnalysisRequest, ArtifactManifest, ArtifactRef, CalibrationContext, ModelSnapshot,
    PlanNode, SourceSnapshot, Window,
)
from app.analysis_runtime.hashing import AnalysisRuntimeError, canonical_json, digest
from app.analysis_runtime.registry import Registry
from app.analysis_runtime.parameters import parameters_for
from app.analysis_runtime.windows import clamp_window


def source_identity(source: SourceSnapshot) -> dict:
    return source.model_dump(exclude={"source_id", "video_id", "media_path", "sidecar_path", "timing_path"})


def model_identity(model: ModelSnapshot) -> dict:
    return {
        "implementation_id": model.implementation_id,
        "assets": {key: asset.sha256 for key, asset in sorted(model.assets.items())},
        "configuration": model.configuration,
    }


def node_contract(node: PlanNode) -> dict:
    value = node.model_dump(mode="json", exclude={"inputs", "window_reasons"})
    value["model"] = model_identity(node.model)
    return value


def semantic_contract(plan: AnalysisPlan) -> dict:
    value = plan.model_dump(mode="json", exclude={"plan_id", "created_at", "plan_hash", "cache_hints", "sources", "nodes"})
    value["sources"] = [source_identity(s) for s in plan.sources]
    value["nodes"] = [
        {**node_contract(node), "inputs": {
            key: value.model_dump(mode="json") if isinstance(value, ArtifactRef) else value
            for key, value in sorted(node.inputs.items())
        }} for node in plan.nodes
    ]
    return value


def verify_plan(plan: AnalysisPlan) -> None:
    if digest(semantic_contract(plan)) != plan.plan_hash:
        raise AnalysisRuntimeError("plan_integrity_error", "冻结计划身份不符")


def cache_key(plan: AnalysisPlan, node: PlanNode, actual_inputs: dict[str, ArtifactManifest]) -> str:
    return digest({
        "node": node_contract(node),
        "sources": [source_identity(s) for s in plan.sources],
        "sampling": plan.sampling.model_dump(),
        "sync": plan.sync,
        "reference_view_id": plan.reference_view_id,
        "inputs": {
            key: {"content": manifest.content_sha256, "type": manifest.ref.artifact_type,
                  "schema": manifest.ref.schema_version,
                  "fixed_id": manifest.ref.artifact_id if isinstance(node.inputs.get(key), ArtifactRef) else None}
            for key, manifest in sorted(actual_inputs.items())
        },
        "missing_optional": sorted(set(node.missing_optional) | (set(node.inputs) - set(actual_inputs))),
    })


class Planner:
    def __init__(
        self, registry: Registry,
        source_reader: Callable[[str], SourceSnapshot | None],
        model_reader: Callable[[str], ModelSnapshot | None],
        artifact_reader: Callable[[str], ArtifactManifest | None],
        cache_reader: Callable[[str], object] | None = None,
    ):
        self.registry = registry
        self.source_reader = source_reader
        self.model_reader = model_reader
        self.artifact_reader = artifact_reader
        self.cache_reader = cache_reader

    def plan(self, request: AnalysisRequest) -> AnalysisPlan:
        # 深拷贝调用方可变字典；队列中另以 hash 核验冻结合同。
        request = AnalysisRequest.model_validate_json(request.model_dump_json())
        resolved, visiting, order = {}, set(), []
        fixed = request.fixed_inputs

        def visit(capability_id: str):
            if capability_id in visiting:
                raise AnalysisRuntimeError("dependency_cycle", capability_id)
            if capability_id in resolved:
                return
            cap, impl = self.registry.resolve(capability_id, request.implementations.get(capability_id))
            visiting.add(capability_id)
            inputs, required, missing = {}, [], []
            for inp in impl.inputs:
                binding_key = capability_id + ":" + inp.name
                ref = fixed.get(binding_key)
                if not inp.required and binding_key not in request.optional_inputs and ref is None:
                    missing.append(inp.name)
                    continue
                if ref is not None:
                    manifest = self.artifact_reader(ref.artifact_id)
                    if manifest is None or manifest.ref != ref:
                        raise AnalysisRuntimeError("fixed_input_missing", binding_key)
                    if ref.artifact_type != inp.artifact_type or ref.schema_version != inp.schema_version:
                        raise AnalysisRuntimeError("input_schema_mismatch", binding_key)
                    inputs[inp.name] = ref
                else:
                    visit(inp.capability_id)
                    producer = resolved[inp.capability_id][1]
                    if producer.output_type != inp.artifact_type or producer.output_schema != inp.schema_version:
                        raise AnalysisRuntimeError("input_schema_mismatch", binding_key)
                    inputs[inp.name] = inp.capability_id
                if inp.required:
                    required.append(inp.name)
            resolved[capability_id] = (cap, impl, inputs, tuple(required), tuple(missing))
            visiting.remove(capability_id)
            order.append(capability_id)

        # 未实现目标先校验，避免创建 Job 或执行来源准备。
        for target in sorted(request.targets):
            visit(target)
        sources = []
        for source_id in request.source_ids:
            source = self.source_reader(source_id)
            if source is None:
                raise AnalysisRuntimeError("preparation_required", "来源尚未准备", details={"source_id": source_id})
            sources.append(source)
        if len({s.view_id for s in sources}) != len(sources):
            raise AnalysisRuntimeError("duplicate_view", "机位标识必须互异")
        reference = request.reference_view_id or sources[0].view_id
        if reference not in {s.view_id for s in sources}:
            raise AnalysisRuntimeError("unknown_reference_view", reference)
        ref_source = next(s for s in sources if s.view_id == reference)
        if len(sources) == 2:
            if request.sync is None or any(s.timing_authority != "source_pts" for s in sources):
                raise AnalysisRuntimeError("authoritative_sync_required", "双摄需要已准备 PTS 与同步快照")
            # 验证同步结构与 camera 映射，禁止 runtime 静默换用 FPS。
            from app.analysis_runtime.sources import parse_sync, sync_contract
            sync = parse_sync(request.sync)
            if sync.reference_camera != ref_source.camera_id:
                raise AnalysisRuntimeError("sync_reference_mismatch", "同步参考机位与计划不符")
            for source in sources:
                if source.view_id != reference and sync.mapping_for(source.camera_id) is None:
                    raise AnalysisRuntimeError("sync_mapping_missing", source.view_id)
            from app.vision.multiview.sync import validate_sync_authority
            secondary = next(s for s in sources if s.view_id != reference)
            authority = validate_sync_authority(sync, reference_camera_id=ref_source.camera_id,
                                                secondary_camera_id=secondary.camera_id,
                                                require_authoritative_calibration=True)
            if not authority.valid:
                raise AnalysisRuntimeError("sync_snapshot_invalid", "同步权威校验失败", details=[issue.code for issue in authority.issues])
            request = request.model_copy(update={"sync": sync_contract(request.sync)})

        needs = {target: request.window for target in request.targets}
        reasons = {key: [] for key in resolved}
        for key in reversed(order):
            if key not in needs:
                continue
            _cap, impl, inputs, _required, _missing = resolved[key]
            output = needs[key]
            required_window = Window(start_ms=output.start_ms - impl.pre_roll_ms, end_ms=output.end_ms + impl.post_roll_ms)
            if (required_window.start_ms < request.window.start_ms - request.context_budget.before_ms
                or required_window.end_ms > request.window.end_ms + request.context_budget.after_ms):
                raise AnalysisRuntimeError("window_budget_exceeded", key, details=required_window.model_dump())
            reasons[key].append(f"{key}: pre={impl.pre_roll_ms}, post={impl.post_roll_ms}")
            for name, producer in inputs.items():
                if isinstance(producer, ArtifactRef):
                    manifest = self.artifact_reader(producer.artifact_id)
                    coverage = manifest.provenance.get("output_window", {}) if manifest else {}
                    if coverage.get("start_ms", float("inf")) > max(0, required_window.start_ms) or coverage.get("end_ms", -1) < min(ref_source.duration_ms, required_window.end_ms):
                        raise AnalysisRuntimeError("fixed_input_window_mismatch", name)
                    if manifest.provenance.get("sources") != [source_identity(s) for s in sorted(sources, key=lambda s: s.view_id)]:
                        raise AnalysisRuntimeError("fixed_input_source_mismatch", name)
                    if manifest.provenance.get("sampling") != request.sampling.model_dump():
                        raise AnalysisRuntimeError("fixed_input_sampling_mismatch", name)
                else:
                    old = needs.get(producer)
                    needs[producer] = required_window if old is None else Window(
                        start_ms=min(old.start_ms, required_window.start_ms), end_ms=max(old.end_ms, required_window.end_ms))
                    reasons[producer].append("consumer:" + key)
        nodes = []
        context_base = dict(request.context.values)
        context_base.update(media=[source_identity(s) for s in sorted(sources, key=lambda s: s.view_id)],
                            frame_time={"sync": request.sync, "reference_view_id": reference})
        for key in order:
            cap, impl, inputs, required, missing = resolved[key]
            extra = request.parameters.get(key, {})
            params = parameters_for(impl, extra)
            model = self.model_reader(impl.implementation_id)
            if model is None and "model" in impl.resources:
                raise AnalysisRuntimeError("preparation_required", "模型身份尚未准备", details={"implementation_id": impl.implementation_id})
            model = model or ModelSnapshot(implementation_id=impl.implementation_id)
            missing_context = set(impl.consumed_context) - set(context_base)
            if missing_context:
                raise AnalysisRuntimeError("context_missing", key, details=sorted(missing_context))
            output = needs[key]
            compute = Window(start_ms=output.start_ms - impl.pre_roll_ms, end_ms=output.end_ms + impl.post_roll_ms)
            effective = clamp_window(compute, ref_source.duration_ms)
            if impl.coordinate_system in {"court_m", "world_3d"}:
                if "calibration" not in impl.consumed_context:
                    raise AnalysisRuntimeError("calibration_context_required", "空间换算必须声明所消费标定")
                try:
                    calibration = CalibrationContext.model_validate(context_base["calibration"])
                except ValueError as exc:
                    raise AnalysisRuntimeError("calibration_context_invalid", "标定快照结构无效") from exc
                if (calibration.valid_window.start_ms > effective.start_ms or calibration.valid_window.end_ms < effective.end_ms
                    or not {s.view_id for s in sources}.issubset(calibration.view_ids)
                    or calibration.coordinate_system != impl.coordinate_system):
                    raise AnalysisRuntimeError("calibration_out_of_range", "标定不覆盖目标时间/机位/坐标系")
            nodes.append(PlanNode(
                node_key=key, capability_id=key, capability_version=cap.contract_version,
                implementation=impl, parameters=params, model=model, inputs=inputs, required_inputs=required,
                missing_optional=missing, compute_window=compute, effective_window=effective,
                output_window=clamp_window(output, ref_source.duration_ms), output_selector=impl.selector,
                consumed_context={f: context_base[f] for f in sorted(impl.consumed_context)},
                window_reasons=tuple(reasons[key]), truncated=compute != effective,
            ))
        plan = AnalysisPlan(
            plan_hash="", sources=tuple(sorted(sources, key=lambda s: s.view_id)),
            requested_window=request.window, sampling=request.sampling, context_budget=request.context_budget,
            failure_policy=request.failure_policy, targets=tuple(sorted(request.targets)), nodes=tuple(nodes),
            sync=request.sync, reference_view_id=reference,
        )
        hints = {}
        for node in plan.nodes:
            if any(isinstance(v, str) for v in node.inputs.values()):
                hints[node.node_key] = {"decision": "pending_binding"}
            else:
                actual = {key: self.artifact_reader(ref.artifact_id) for key, ref in node.inputs.items()}
                result = self.cache_reader(cache_key(plan, node, actual)) if self.cache_reader else None
                hints[node.node_key] = {"decision": "hit" if result else "miss"}
        plan = plan.model_copy(update={"plan_hash": digest(semantic_contract(plan)), "cache_hints": hints})
        # 去掉调用方字典别名，并拒绝非 JSON 数值。
        canonical_json(semantic_contract(plan))
        return AnalysisPlan.model_validate_json(plan.model_dump_json())
