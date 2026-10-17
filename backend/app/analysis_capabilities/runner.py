"""静态适配器工厂，窗口/资源运行共用，算法留在独立能力目录。"""
from __future__ import annotations

from contextlib import closing
from importlib import import_module

from app.analysis_runtime.hashing import AnalysisRuntimeError
from app.analysis_runtime.resources import iter_frames
from app.analysis_runtime.sources import verify_model

# 内置静态映射；无扫描、插件发现或第三方注册。
ADAPTERS = {
    "player.yolo.v1": ("app.analysis_capabilities.players.adapter","PlayerDetectionAdapter"),
    "ball.yolo.v1": ("app.analysis_capabilities.ball.adapter","BallDetectionAdapter"),
    "pose.rtmpose26.v1": ("app.analysis_capabilities.pose.adapter","PoseSequenceAdapter"),
}


def run_capability(plan, node, inputs, counters, check):
    from app.analysis_runtime.registry import builtin_registry
    _cap, installed = builtin_registry().resolve(node.capability_id, node.implementation.implementation_id)
    if installed.version != node.implementation.version or installed.output_schema != node.implementation.output_schema:
        raise AnalysisRuntimeError("implementation_revision_mismatch", "冻结实现版本不在当前运行时中")
    verify_model(node.model)
    if "weights" not in node.model.assets:
        raise AnalysisRuntimeError("model_environment","模型权重未准备")
    entry = ADAPTERS.get(node.implementation.implementation_id)
    if entry is None:
        raise AnalysisRuntimeError("capability_not_implemented",node.capability_id)
    adapter = getattr(import_module(entry[0]),entry[1])(node,inputs,counters)
    counters["model_constructors"] += 1
    rows = []
    try:
        with closing(iter_frames(plan,node,counters,check)) as frames:
            for source,row,frame in frames:
                check()
                if frame is None:
                    data = {"candidates":[]} if node.capability_id=="ball.detect" else {"subjects":[]}
                else:
                    counters["sampled_frames"] += 1
                    data = adapter.infer(source,row,frame)
                check()
                if node.output_window.start_ms <= row["canonical_time_ms"] < node.output_window.end_ms:
                    rows.append({**row,**data})
        return {"schema_version":node.implementation.output_type+".v"+node.implementation.output_schema,
                "coordinates":"image_px","units":"px","subject_scope":"observation",
                "temporal_association":"absent","observations":rows}
    finally:
        adapter.close()
