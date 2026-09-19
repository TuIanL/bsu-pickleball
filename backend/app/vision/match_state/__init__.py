"""Production match-state segmentation primitives.

This package deliberately has no dependency on ``scripts/`` or dataset/cache
artifacts.  Training and QA commands may import the pure decoder helpers, but
the formal analysis path imports only this package.
"""

from .artifact import AnalysisWindowPlan, SegmentationArtifact, build_segmentation_artifact
from .decoder import DecodedRally, decode_state_timeline, decode_state_timeline_result
from .package import ModelPackageCache, ModelPackageError, ProductionModelPackage, load_production_package
from .runtime import MatchStateSegmentationRuntime, SegmentationInput, SegmentationResult
from .sampler import MatchStateSynchronizedSampler, SynchronizedSample

__all__ = [
    "AnalysisWindowPlan",
    "DecodedRally",
    "MatchStateSegmentationRuntime",
    "ModelPackageCache",
    "ModelPackageError",
    "ProductionModelPackage",
    "SegmentationArtifact",
    "SegmentationInput",
    "SegmentationResult",
    "MatchStateSynchronizedSampler",
    "SynchronizedSample",
    "build_segmentation_artifact",
    "decode_state_timeline",
    "decode_state_timeline_result",
    "load_production_package",
]
