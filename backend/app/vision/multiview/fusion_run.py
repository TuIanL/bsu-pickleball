"""多视角融合运行实体（fusion_run）—— MultiViewFusionRun 的所有权与编排。

回答三个问题：
- **谁等待**：Run 的编排者等待两个 source AnalysisJob 完成；
- **谁执行**：Run 的执行管线（Canonical Timeline → predict → associate → quality →
  pair → conflict → fusion → update）；
- **产物归属**：fused artifact 挂 Run 的产物目录（不挂 cam_1/cam_2 Job，不挂 CaptureTake）。

job-level 与 sample-level fallback 在此分层：
- job-level：Run 无法合法启动（任一 view `court_orientation=None` 或 sync authority
  unavailable）→ 不生成 fused artifact，下游继续消费单摄 artifact；
- sample-level：Run 合法但某时刻某路 unavailable → 该 fused sample 降级，Run 继续。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition
from app.vision.multiview.sync import MultiViewSyncCalibration, SyncGateDecision, evaluate_sync_gate
from app.vision.multiview.view_input import MultiViewViewInput

RunStatus = Literal[
    "pending",
    "waiting_source_jobs",
    "ready",
    "job_level_fallback",
    "running",
    "completed",
    "failed",
]


@dataclass
class MultiViewFusionRun:
    """一次多视角分析的运行实体（持有输入、等待、执行、产物归属）。"""

    run_id: str
    capture_take_id: str
    source_analysis_job_ids: list[str] = field(default_factory=list)
    view_inputs: list[MultiViewViewInput] = field(default_factory=list)
    sync_calibration_ref: MultiViewSyncCalibration | None = None
    canonical_frame_ref: CanonicalCourtFrameDefinition | None = None
    pairing_plan_ref: dict[str, object] | None = None
    output_dir: Path | None = None
    status: RunStatus = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # ---- 构造 ---------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        capture_take_id: str,
        source_analysis_job_ids: list[str],
        view_inputs: list[MultiViewViewInput],
        sync_calibration_ref: MultiViewSyncCalibration | None = None,
        canonical_frame_ref: CanonicalCourtFrameDefinition | None = None,
        output_dir: Path | None = None,
    ) -> MultiViewFusionRun:
        return cls(
            run_id=f"mvf_{uuid4().hex[:12]}",
            capture_take_id=capture_take_id,
            source_analysis_job_ids=list(source_analysis_job_ids),
            view_inputs=list(view_inputs),
            sync_calibration_ref=sync_calibration_ref,
            canonical_frame_ref=canonical_frame_ref,
            output_dir=output_dir,
        )

    # ---- 输入查询 -----------------------------------------------------------

    def view_ids(self) -> list[str]:
        return [view.view_id for view in self.view_inputs]

    def view_input(self, view_id: str) -> MultiViewViewInput | None:
        for view in self.view_inputs:
            if view.view_id == view_id:
                return view
        return None

    # ---- 编排 ---------------------------------------------------------------

    def check_eligibility(self) -> RunEligibility:
        """校验 Run 能否合法启动（job-level gate）。

        不合法 → job_level_fallback，不生成 fused artifact。
        """
        missing = [
            view.view_id for view in self.view_inputs if view.court_orientation is None
        ]
        if missing:
            return RunEligibility(
                ready=False,
                reason=f"court_orientation not declared for view(s): {missing}",
                sync_gate="single_view",
                missing_orientations=missing,
            )
        sync_gate, reason = evaluate_sync_gate(self.sync_calibration_ref)
        if sync_gate == "single_view":
            return RunEligibility(
                ready=False,
                reason=reason,
                sync_gate=sync_gate,
                missing_orientations=[],
            )
        return RunEligibility(ready=True, reason=reason, sync_gate=sync_gate, missing_orientations=[])

    def wait_for_source_jobs(
        self,
        job_status: Callable[[str], str],
        *,
        required: Literal["completed"] = "completed",
    ) -> bool:
        """等待全部 source AnalysisJob 完成；任一未完成/失败返回 False。"""
        return all(job_status(job_id) == required for job_id in self.source_analysis_job_ids)


@dataclass(frozen=True)
class RunEligibility:
    """Run 能否合法启动的判定结果（job-level fallback gate）。"""

    ready: bool
    reason: str
    sync_gate: SyncGateDecision
    missing_orientations: list[str]


def default_run_output_dir(analysis_dir: str | os.PathLike[str], run_id: str) -> Path:
    """默认 Run 产物目录：`analysis_dir/multiview/<run_id>`。"""
    return Path(analysis_dir) / "multiview" / run_id
