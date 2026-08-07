"""击球球员归属（ball_hit_player_attributor）。

对通过事件粗门（prefilter）的击球候选，综合球员时空证据评分归属：

  - wrist_proximity：球—任一手腕图像距离（按人体框对角线归一化）；
  - bbox_proximity：球—球员检测框中心距离（归一化）；
  - arm_motion_peak：接触时间窗内上肢运动峰值（共享上肢证据索引）；
  - court_side：球员半场与球球场位置半场的一致性；
  - temporal_freshness：球员证据帧的时间接近度。

判定（设计 D5）：
  confirmed  = 最佳分数达标 且 与次佳候选差距（margin）达标；
  ambiguous  = 分数达标但 margin 不足；
  unassigned = 球员证据不足。

证据缺失时对剩余权重重新归一化；无姿态数据不使归属失效（bbox 降级）。
归属结果只使用 canonical `Player_N`（不变量 I4 / I9）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from app.vision.pickleball_game_analysis.ball_event_resolver import PrefilteredHitCandidate
from app.vision.pickleball_game_analysis.player_attribution_context import PlayerAttributionContext
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    OwnershipStatus,
    PlayerAttribution,
    PlayerCandidateScore,
)


@dataclass(frozen=True)
class HitPlayerAttributionConfig:
    """击球归属超参数（时间语义，兼容不同帧率与 frame_stride）。"""

    contact_window_before_sec: float = 0.15
    contact_window_after_sec: float = 0.08
    maximum_pose_sample_gap_sec: float = 0.10
    maximum_tracking_sample_gap_sec: float = 0.12
    minimum_scale_px: float = 60.0
    attribution_min_score: float = 0.60
    attribution_min_margin: float = 0.20
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "wrist_proximity": 0.35,
            "bbox_proximity": 0.25,
            "arm_motion_peak": 0.20,
            "court_side": 0.15,
            "temporal_freshness": 0.05,
        }
    )

    @property
    def weight_names(self) -> list[str]:
        return list(self.weights.keys())


class BallHitPlayerAttributor:
    """为击球候选计算球员归属。"""

    def __init__(self, config: HitPlayerAttributionConfig | None = None) -> None:
        self.config = config or HitPlayerAttributionConfig()

    def attribute(
        self,
        candidates: list[PrefilteredHitCandidate],
        context: PlayerAttributionContext,
    ) -> dict[str, PlayerAttribution]:
        """返回 candidate_id -> PlayerAttribution（含 confirmed/ambiguous/unassigned）。"""
        result: dict[str, PlayerAttribution] = {}
        for candidate in candidates:
            if candidate.prefilter_status != "survived":
                continue
            scores = self._score_players(candidate, context)
            result[candidate.candidate_id] = self._decide(candidate, scores, context)
        return result

    # ------------------------------------------------------------------
    # 评分
    # ------------------------------------------------------------------

    def _score_players(
        self,
        candidate: PrefilteredHitCandidate,
        context: PlayerAttributionContext,
    ) -> dict[str, tuple[dict[str, float], int | None]]:
        """每个球员的逐证据评分（缺失证据不在 dict 中，判定时归一化）。"""
        scores: dict[str, tuple[dict[str, float], int | None]] = {}
        for player_id in context.player_ids:
            scores[player_id] = self._score_player(candidate, player_id, context)
        return scores

    def _score_player(
        self,
        candidate: PrefilteredHitCandidate,
        player_id: str,
        context: PlayerAttributionContext,
    ) -> tuple[dict[str, float], int | None]:
        start_sec = candidate.timestamp_sec - self.config.contact_window_before_sec
        end_sec = candidate.timestamp_sec + self.config.contact_window_after_sec
        evidence: dict[str, float] = {}
        wrist_frame: int | None = None

        wrist_score, wrist_frame, scale = self._wrist_proximity(candidate, player_id, context, start_sec, end_sec)
        if wrist_score is not None:
            evidence["wrist_proximity"] = wrist_score

        bbox_score = self._bbox_proximity(candidate, player_id, context, start_sec, end_sec, scale)
        if bbox_score is not None:
            evidence["bbox_proximity"] = bbox_score

        motion_score = self._arm_motion_peak(player_id, context, start_sec, end_sec)
        if motion_score is not None:
            evidence["arm_motion_peak"] = motion_score

        side_score = self._court_side(candidate, player_id, context)
        if side_score is not None:
            evidence["court_side"] = side_score

        freshness = self._temporal_freshness(player_id, context, candidate.timestamp_sec)
        if freshness is not None:
            evidence["temporal_freshness"] = freshness

        return evidence, wrist_frame

    def _wrist_proximity(
        self,
        candidate: PrefilteredHitCandidate,
        player_id: str,
        context: PlayerAttributionContext,
        start_sec: float,
        end_sec: float,
    ) -> tuple[float | None, int | None, float | None]:
        """球—任一手腕归一化距离；返回 (score, 最近帧, 尺度基准)。

        尺度 = 球员检测框对角线（接触窗内采样），缺失时用配置下限。
        归一化：pixel_dist / max(bbox_diagonal, minimum_scale_px)。
        """
        if context.upper_limb_index is None or candidate.image_xy is None:
            return None, None, None
        ball_x, ball_y = candidate.image_xy
        scale = self._player_scale(player_id, context, start_sec, end_sec)
        best_px: float | None = None
        best_frame: int | None = None
        for track_id in context.tracks_for_player(player_id):
            for evidence in context.upper_limb_index.evidence_in_window(track_id, start_sec, end_sec):
                wrists = [
                    evidence.left_wrist_xy,
                    evidence.right_wrist_xy,
                ]
                for wrist in wrists:
                    if wrist is None:
                        continue
                    px = hypot(ball_x - wrist[0], ball_y - wrist[1])
                    if best_px is None or px < best_px:
                        best_px = px
                        best_frame = evidence.frame_index
        if best_px is None:
            return None, None, scale
        denom = max(scale if scale and scale > 0 else self.config.minimum_scale_px, 1e-6)
        normalized = best_px / denom
        return self._clamp01(1.0 - normalized), best_frame, scale

    def _bbox_proximity(
        self,
        candidate: PrefilteredHitCandidate,
        player_id: str,
        context: PlayerAttributionContext,
        start_sec: float,
        end_sec: float,
        scale: float | None,
    ) -> float | None:
        """球—球员检测框中心距离（归一化）；tracking 采样缺失时返回 None。"""
        if candidate.image_xy is None:
            return None
        ball_x, ball_y = candidate.image_xy
        best_px: float | None = None
        for sample in context.samples_in_window(player_id, start_sec, end_sec):
            if sample.bbox is None:
                continue
            x1, y1, x2, y2 = sample.bbox
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            px = hypot(ball_x - center[0], ball_y - center[1])
            if best_px is None or px < best_px:
                best_px = px
        if best_px is None:
            return None
        denom = max(
            scale if scale and scale > 0 else self.config.minimum_scale_px,
            self.config.minimum_scale_px,
        )
        return self._clamp01(1.0 - best_px / denom)

    def _arm_motion_peak(
        self,
        player_id: str,
        context: PlayerAttributionContext,
        start_sec: float,
        end_sec: float,
    ) -> float | None:
        """接触时间窗内上肢运动峰值（取该球员全部 track 的最大值）。"""
        if context.upper_limb_index is None:
            return None
        peak = 0.0
        found = False
        for track_id in context.tracks_for_player(player_id):
            for evidence in context.upper_limb_index.evidence_in_window(track_id, start_sec, end_sec):
                if evidence.arm_motion_px_per_second > 0:
                    found = True
                peak = max(peak, evidence.arm_motion_px_per_second)
        if not found:
            return None
        # 以 1500 px/s 为满分参考（30fps 下相邻帧 50px 的挥拍）
        return self._clamp01(peak / 1500.0)

    def _court_side(
        self,
        candidate: PrefilteredHitCandidate,
        player_id: str,
        context: PlayerAttributionContext,
    ) -> float | None:
        """球员半场与球球场位置半场的一致性（无球球场坐标时中性 0.5）。"""
        if candidate.image_xy is None:
            return None
        ball_court = getattr(candidate, "court_xy", None)
        if ball_court is None:
            return 0.5
        length = 44.0
        ball_side = "near" if ball_court[1] < length / 2 else "far"
        player_side = context.side_at(player_id, candidate.timestamp_sec)
        if player_side is None:
            return 0.5
        return 1.0 if player_side == ball_side else 0.0

    def _temporal_freshness(
        self,
        player_id: str,
        context: PlayerAttributionContext,
        timestamp_sec: float,
    ) -> float | None:
        """球员最近采样与接触时刻的时间接近度（0~1）。"""
        samples = context.player_samples.get(player_id)
        if not samples:
            return None
        gap = min(abs(s.timestamp_seconds - timestamp_sec) for s in samples)
        return self._clamp01(1.0 - gap / max(self.config.maximum_tracking_sample_gap_sec, 1e-6))

    def _player_scale(
        self,
        player_id: str,
        context: PlayerAttributionContext,
        start_sec: float,
        end_sec: float,
    ) -> float | None:
        """球员检测框对角线（接触窗内最大者，作为尺度基准）。"""
        diagonal: float | None = None
        for sample in context.samples_in_window(player_id, start_sec, end_sec):
            if sample.bbox is None:
                continue
            x1, y1, x2, y2 = sample.bbox
            d = hypot(x2 - x1, y2 - y1)
            if diagonal is None or d > diagonal:
                diagonal = d
        return diagonal

    # ------------------------------------------------------------------
    # 判定
    # ------------------------------------------------------------------

    def _decide(
        self,
        candidate: PrefilteredHitCandidate,
        scores: dict[str, tuple[dict[str, float], int | None]],
        context: PlayerAttributionContext,
    ) -> PlayerAttribution:
        """按归一化总分与 margin 判定 confirmed / ambiguous / unassigned。"""
        totals: list[tuple[float, str, int | None]] = []
        for player_id, (evidence, wrist_frame) in scores.items():
            if not evidence:
                continue
            available_weight = sum(self.config.weights[name] for name in evidence)
            if available_weight <= 0:
                continue
            total = sum(self.config.weights[name] * score for name, score in evidence.items()) / available_weight
            totals.append((total, player_id, wrist_frame))

        if not totals:
            return PlayerAttribution(
                candidate_id=candidate.candidate_id,
                status=OwnershipStatus.UNASSIGNED.value,
                method="none",
            )

        totals.sort(key=lambda item: item[0], reverse=True)
        best_score, best_player, best_wrist_frame = totals[0]
        second_score = totals[1][0] if len(totals) > 1 else 0.0
        margin = best_score - second_score

        render_slot = context.render_slot_for(best_player)
        candidate_scores = [
            PlayerCandidateScore(player_id=player_id, score=round(score, 3)) for score, player_id, _frame in totals
        ]

        method = "pose_bbox_fused" if context.upper_limb_index is not None else "bbox_fused"
        if best_score >= self.config.attribution_min_score:
            if margin >= self.config.attribution_min_margin:
                return PlayerAttribution(
                    candidate_id=candidate.candidate_id,
                    status=OwnershipStatus.CONFIRMED.value,
                    player_id=best_player,
                    render_slot=render_slot,
                    confidence=round(best_score, 3),
                    score_margin=round(margin, 3),
                    attributed_frame_index=best_wrist_frame,
                    method=method,
                    candidate_scores=candidate_scores,
                )
            return PlayerAttribution(
                candidate_id=candidate.candidate_id,
                status=OwnershipStatus.AMBIGUOUS.value,
                confidence=round(best_score, 3),
                score_margin=round(margin, 3),
                method=method,
                candidate_scores=candidate_scores,
            )
        return PlayerAttribution(
            candidate_id=candidate.candidate_id,
            status=OwnershipStatus.UNASSIGNED.value,
            confidence=round(best_score, 3),
            score_margin=round(margin, 3),
            method=method,
            candidate_scores=candidate_scores,
        )

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))


def serve_seeded_attribution(
    candidate: PrefilteredHitCandidate,
    player_id: str,
    context: PlayerAttributionContext,
    *,
    method: str = "serve_seeded",
) -> PlayerAttribution:
    """发球直接播种归属（不执行普通推断）。"""
    return PlayerAttribution(
        candidate_id=candidate.candidate_id,
        status=OwnershipStatus.CONFIRMED.value,
        player_id=player_id,
        render_slot=context.render_slot_for(player_id),
        confidence=1.0,
        score_margin=1.0,
        attributed_frame_index=candidate.frame_index,
        method=method,
        candidate_scores=[PlayerCandidateScore(player_id=player_id, score=1.0)],
    )
