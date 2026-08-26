"""球 3D 核心算法包（court-constrained approximate stereo）。

包含：虚拟相机分解（virtual_camera）、逐 tick 立体证据（stereo_measurement）、
跨视角关联（association）、段级 3D 曲线优化（segment_reconstruction）、
落点权威（landing_authority）、衍生指标（metrics）、产物序列化（artifact_builders）。
"""

from app.vision.multiview.ball_stereo.association import associate_views  # noqa: F401
from app.vision.multiview.ball_stereo.artifact_builders import (  # noqa: F401
    build_stereo_evidence_v1,
    build_v3_trajectory,
)
from app.vision.multiview.ball_stereo.bundle_refine import (  # noqa: F401
    BAPlaneAnchor,
    CameraInit,
    BundleResult,
    bundle_refine,
)
from app.vision.multiview.ball_stereo.landing_authority import resolve_landing  # noqa: F401
from app.vision.multiview.ball_stereo.metrics import BallMetrics, compute_metrics  # noqa: F401
from app.vision.multiview.ball_stereo.net_assisted_camera import (  # noqa: F401
    NetCameraQuality,
    evaluate_net_camera_quality,
    refine_virtual_camera_with_net,
)
from app.vision.multiview.ball_stereo.segment_reconstruction import (  # noqa: F401
    Observation,
    Reconstructed3DSegment,
    reconstruct_segment,
)
from app.vision.multiview.ball_stereo.stereo_measurement import BallStereoMeasurement, measure_stereo  # noqa: F401
from app.vision.multiview.ball_stereo.virtual_camera import (  # noqa: F401
    VirtualCameraResult,
    decompose_virtual_camera,
)
