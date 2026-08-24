"""球端点相对标准场地和比赛环境的证据分类。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import hypot

from app.vision.pickleball_game_analysis.schemas import Point2D


class BallEnvironmentOutcome(StrEnum):
    IN_COURT = "in_court"
    LEGAL_OUT_CANDIDATE = "legal_out_candidate"
    CALIBRATION_UNCERTAIN = "calibration_uncertain"
    ENVIRONMENT_OUTLIER = "environment_outlier"


@dataclass(frozen=True)
class CourtBounds:
    min_x_ft: float = 0.0
    max_x_ft: float = 20.0
    min_y_ft: float = 0.0
    max_y_ft: float = 44.0

    def contains(self, point: Point2D) -> bool:
        return self.min_x_ft <= point[0] <= self.max_x_ft and self.min_y_ft <= point[1] <= self.max_y_ft

    def outside_distance(self, point: Point2D) -> float:
        dx = max(self.min_x_ft - point[0], 0.0, point[0] - self.max_x_ft)
        dy = max(self.min_y_ft - point[1], 0.0, point[1] - self.max_y_ft)
        return hypot(dx, dy)


@dataclass(frozen=True)
class PlayEnvironmentBounds(CourtBounds):
    """包含底线后准备区和边线外救球区的可配置环境边界。"""

    min_x_ft: float = -8.0
    max_x_ft: float = 28.0
    min_y_ft: float = -12.0
    max_y_ft: float = 56.0


@dataclass(frozen=True)
class EndpointEvidence:
    continuity_score: float = 0.0
    endpoint_time_consistent: bool = False
    static_pattern: bool = False
    jump_detected: bool = False
    reprojection_error_px: float | None = None
    cross_view_supported: bool = False
    calibration_uncertainty_ft: float = 1.0


@dataclass(frozen=True)
class EndpointClassification:
    court_location: str
    outcome_classification: str
    accepted_for_formal_trajectory: bool
    automatic_adjudication: bool
    calibration_uncertainty_ft: float
    reasons: tuple[str, ...]

    @property
    def non_adjudication_notice(self) -> str:
        return "可能界外落点，非自动判罚" if self.outcome_classification == "legal_out_candidate" else "非自动判罚"


class BallEnvironmentClassifier:
    """越过标准边线只产生事实；只有多项环境离群证据才正式拒绝。"""

    def __init__(
        self,
        court_bounds: CourtBounds | None = None,
        environment_bounds: PlayEnvironmentBounds | None = None,
        *,
        max_reprojection_error_px: float = 45.0,
        min_continuity_score: float = 0.55,
    ) -> None:
        self.court_bounds = court_bounds or CourtBounds()
        self.environment_bounds = environment_bounds or PlayEnvironmentBounds()
        self.max_reprojection_error_px = max_reprojection_error_px
        self.min_continuity_score = min_continuity_score

    def classify(self, point: Point2D, evidence: EndpointEvidence) -> EndpointClassification:
        if self.court_bounds.contains(point):
            return self._result("inside_line", BallEnvironmentOutcome.IN_COURT, evidence, ("inside_standard_court",))

        outside_line_reason = "outside_standard_court_line"
        if self.environment_bounds.contains(point):
            if evidence.continuity_score >= self.min_continuity_score and evidence.endpoint_time_consistent:
                return self._result(
                    "outside_line",
                    BallEnvironmentOutcome.LEGAL_OUT_CANDIDATE,
                    evidence,
                    (outside_line_reason, "continuous_flight", "endpoint_time_consistent"),
                )
            return self._result(
                "outside_line",
                BallEnvironmentOutcome.CALIBRATION_UNCERTAIN,
                evidence,
                (outside_line_reason, "insufficient_endpoint_support"),
            )

        environment_distance = self.environment_bounds.outside_distance(point)
        if environment_distance <= max(0.0, evidence.calibration_uncertainty_ft):
            return self._result(
                "outside_environment",
                BallEnvironmentOutcome.CALIBRATION_UNCERTAIN,
                evidence,
                ("outside_environment_within_calibration_uncertainty",),
            )

        inconsistency_reasons: list[str] = []
        if evidence.static_pattern:
            inconsistency_reasons.append("static_pattern")
        if evidence.jump_detected:
            inconsistency_reasons.append("trajectory_jump")
        if (
            evidence.reprojection_error_px is not None
            and evidence.reprojection_error_px > self.max_reprojection_error_px
        ):
            inconsistency_reasons.append("high_reprojection_error")
        if not evidence.cross_view_supported:
            inconsistency_reasons.append("no_cross_view_support")
        if evidence.continuity_score < self.min_continuity_score:
            inconsistency_reasons.append("low_continuity")

        if len(inconsistency_reasons) >= 2:
            return self._result(
                "outside_environment",
                BallEnvironmentOutcome.ENVIRONMENT_OUTLIER,
                evidence,
                tuple(["far_outside_play_environment", *inconsistency_reasons]),
            )
        return self._result(
            "outside_environment",
            BallEnvironmentOutcome.CALIBRATION_UNCERTAIN,
            evidence,
            ("outside_environment_but_not_enough_outlier_evidence", *inconsistency_reasons),
        )

    @staticmethod
    def _result(
        court_location: str,
        outcome: BallEnvironmentOutcome,
        evidence: EndpointEvidence,
        reasons: tuple[str, ...],
    ) -> EndpointClassification:
        return EndpointClassification(
            court_location=court_location,
            outcome_classification=outcome.value,
            accepted_for_formal_trajectory=outcome != BallEnvironmentOutcome.ENVIRONMENT_OUTLIER,
            automatic_adjudication=False,
            calibration_uncertainty_ft=max(0.0, evidence.calibration_uncertainty_ft),
            reasons=reasons,
        )
