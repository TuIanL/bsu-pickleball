"""静态声明注册；模型工厂仅在 executor cache miss 后加载。"""
from __future__ import annotations

from app.analysis_runtime.contracts import CapabilitySpec, ImplementationSpec, InputSpec
from app.analysis_runtime.hashing import AnalysisRuntimeError


class Registry:
    def __init__(self):
        self.capabilities: dict[str, CapabilitySpec] = {}
        self.implementations: dict[str, ImplementationSpec] = {}

    def register(self, capability: CapabilitySpec, implementations=()):
        if capability.status == "implemented" and not capability.implementations:
            raise ValueError("implemented capability requires an implementation")
        if capability.capability_id in self.capabilities:
            raise ValueError("duplicate capability: " + capability.capability_id)
        for implementation in implementations:
            if implementation.capability_id != capability.capability_id:
                raise ValueError("implementation capability mismatch")
            if implementation.implementation_id in self.implementations:
                raise ValueError("duplicate implementation")
            self.implementations[implementation.implementation_id] = implementation
        if set(capability.implementations) != {i.implementation_id for i in implementations}:
            raise ValueError("implementation declaration mismatch")
        self.capabilities[capability.capability_id] = capability

    def resolve(self, capability_id: str, implementation_id: str | None = None):
        cap = self.capabilities.get(capability_id)
        if cap is None:
            raise AnalysisRuntimeError("unknown_capability", capability_id)
        if cap.status != "implemented":
            raise AnalysisRuntimeError("capability_not_implemented", capability_id)
        selected = implementation_id or cap.implementations[0]
        if selected not in cap.implementations:
            raise AnalysisRuntimeError("implementation_not_compatible", selected)
        return cap, self.implementations[selected]

    def catalog(self):
        return [c.model_dump(mode="json") for c in self.capabilities.values()]


def builtin_registry() -> Registry:
    registry = Registry()
    for cap_id, impl_id, output, inputs, defaults in [
        ("player.detect", "player.yolo.v1", "player.observations", (), {"confidence": 0.15}),
        ("ball.detect", "ball.yolo.v1", "ball.observations_2d", (), {"confidence": 0.18}),
        ("pose.sequence", "pose.rtmpose26.v1", "pose.observations",
         (InputSpec(name="players", capability_id="player.detect", artifact_type="player.observations"),),
         {"confidence": 0.3, "exit_confidence": 0.2}),
    ]:
        impl = ImplementationSpec(
            implementation_id=impl_id, capability_id=cap_id, output_type=output,
            inputs=inputs, parameter_defaults=defaults, resources=("decode", "model"),
            parameter_schema={key: {"type": "number", "minimum": 0, "maximum": 1} for key in defaults},
            secondary_failure_policy="degrade" if cap_id == "ball.detect" else "fail",
        )
        registry.register(CapabilitySpec(capability_id=cap_id, status="implemented", implementations=(impl_id,), output_types=(output,)), (impl,))
    for cap_id in (
        "player.track", "player.identity", "ball.track_2d", "ball.clean_2d", "ball.events",
        "ball.reconstruct_3d", "racket.detect", "racket.track", "racket.player_association",
        "pose.associate", "motion.upper_limb", "swing.segment", "contact.detect",
        "stroke.classify", "shot.assemble", "shot.landing", "context.rally",
        "shot.semantic", "tactics.analyze", "evaluation.quality", "metrics.compute",
    ):
        domain_schema = {
            "racket": "RacketObservation", "motion": "MotionEvidence", "swing": "SwingSequence",
            "contact": "ContactCandidate", "stroke": "ShotSemantics", "ball": "BallTrackEvidence",
            "shot": "LandingEvidence" if cap_id == "shot.landing" else "ShotSemantics" if cap_id == "shot.semantic" else "ShotEvidence",
            "context": "RallyContext", "tactics": "TacticalInterpretation", "evaluation": "EvaluationEvidence",
            "metrics": "EvaluationEvidence",
        }.get(cap_id.split(".")[0])
        schema_path = "app.analysis_capabilities.catalog.contracts:" + domain_schema if domain_schema else "app.analysis_runtime.contracts:ObjectRef"
        if cap_id == "stroke.classify":
            schema_path = "app.analysis_runtime.contracts:StrokeAttributes"
        if cap_id in {"player.track", "racket.track"}:
            schema_path = "app.analysis_capabilities.catalog.contracts:SubjectTrack"
        if cap_id == "ball.events":
            schema_path = "app.analysis_capabilities.catalog.contracts:BallEventCandidate"
        if cap_id in {"racket.player_association", "pose.associate", "player.identity"}:
            schema_path = "app.analysis_runtime.contracts:Association"
        output = {
            "player.track": "player.local_tracks", "player.identity": "player.identity_associations",
            "ball.track_2d": "ball.observed_tracks_2d", "ball.clean_2d": "ball.cleaned_tracks_2d",
            "ball.events": "ball.events", "ball.reconstruct_3d": "ball.reconstructed_tracks_3d",
            "racket.detect": "racket.observations", "racket.track": "racket.local_tracks",
            "racket.player_association": "racket.player_associations", "pose.associate": "pose.associations",
            "motion.upper_limb": "motion.upper_limb_evidence", "swing.segment": "swing.sequences",
            "contact.detect": "contact.candidates", "stroke.classify": "stroke.attributes",
            "shot.assemble": "shot.events", "shot.landing": "shot.landings", "context.rally": "rally.context",
            "shot.semantic": "shot.semantics", "tactics.analyze": "tactical.interpretations",
            "evaluation.quality": "evaluation.evidence", "metrics.compute": "metric.snapshot",
        }[cap_id]
        registry.register(CapabilitySpec(capability_id=cap_id, output_types=(output,), schema_path=schema_path))
    return registry
