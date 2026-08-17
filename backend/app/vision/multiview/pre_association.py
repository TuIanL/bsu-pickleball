"""pre_association.py —— same-tick usable-candidate recovery 的候选归属先验层。

`strengthen-multiview-cooperative-player-perception`：

- `PreAssociationCandidate`：某 view 当前 tick 的 raw/ROI-filtered evidence 的
  canonical candidate + 轻量归属判定结果；
- `pre_associate()`：只读 `GlobalState(t-1)` 预测，对 ROI-filtered base + 成功
  pre-tick guided evidence 做一对一 min-cost 匹配 + gate + ambiguity rejection。

关键语义：
- **只读**：MUST NOT 修改任何 global state / mapping / tracker；不产生 AssociationUpdate；
- **只消费 ROI-filtered evidence**（球场外人员不得成为强 candidate）；raw detections 仅诊断；
- **投影与正式 `PlayerProjector` 共用** `classify_projection_status`（防前后不一致）；
- 一对一匹配：`residual ≤ pre_association_gate_ft` 且 second-best margin > `ambiguity_margin`
  → strong candidate；否则 `ambiguous`（双打 NVZ 密集时防 P1/P2 互换）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical
from app.vision.player_tracking_engine.player_projector import classify_projection_status


@dataclass
class PreAssociationCandidate:
    """某 view 当前 tick 的 canonical candidate + 归属判定结果。"""

    view_id: str
    source_frame_index: int
    origin: str  # base | guided_roi
    image_footpoint: tuple[float, float]
    court_position_ft: tuple[float, float] | None  # 投影失败则 None
    canonical_position_ft: tuple[float, float] | None
    projection_status: str  # inside_court | outside_court_visible | outside_tracking_area | projection_failed
    intrinsic_quality: float = 0.0
    # ---- 归属判定（一对一匹配 + gate + ambiguity rejection）----
    matched_global_id: str | None = None
    residual_ft: float | None = None
    ambiguity_margin: float | None = None
    match_status: str = "not_assessed"  # strong | ambiguous | unmatched | not_assessed

    @property
    def is_usable(self) -> bool:
        """可 canonical 化且归属为 strong 的 candidate 才可作为 same-tick donor。"""
        return (
            self.canonical_position_ft is not None
            and self.match_status == "strong"
        )


@dataclass
class PreAssociationResult:
    """一次 pre-association 的输出（按 view 分组）。"""

    candidates: list[PreAssociationCandidate] = field(default_factory=list)

    def strong_for_view(self, view_id: str) -> list[PreAssociationCandidate]:
        return [c for c in self.candidates if c.view_id == view_id and c.match_status == "strong"]


def _footpoint_of(det: Any) -> tuple[float, float] | None:
    """从 detection 提取图像脚点（支持 bbox / footpoint / image_footpoint）。"""
    fp = getattr(det, "image_footpoint", None) or getattr(det, "footpoint", None)
    if fp is not None and len(fp) >= 2:
        return float(fp[0]), float(fp[1])
    bbox = getattr(det, "bbox", None)
    if bbox is not None and len(bbox) >= 4:
        return (float(bbox[0]) + float(bbox[2])) / 2.0, float(bbox[3])
    return None


def _quality_of(det: Any) -> float:
    return float(getattr(det, "confidence", 0.0) or getattr(det, "score", 0.0) or 0.0)


def build_candidate(
    *,
    view_id: str,
    source_frame_index: int,
    det: Any,
    origin: str,
    homography: Any,
    orientation: CourtOrientation | None,
) -> PreAssociationCandidate:
    """从单个 evidence 构建 canonical candidate（复用共享投影分类）。

    - footpoint → `image_to_court` → court position；
    - `classify_projection_status` 与正式 PlayerProjector 一致；
    - court → canonical（local_to_canonical）；投影失败则 canonical=None。
    """
    from app.vision.courtvision_calibration_engine.homography import image_to_court

    fp = _footpoint_of(det)
    if fp is None:
        return PreAssociationCandidate(
            view_id=view_id, source_frame_index=source_frame_index, origin=origin,
            image_footpoint=(0.0, 0.0), court_position_ft=None, canonical_position_ft=None,
            projection_status="projection_failed", intrinsic_quality=_quality_of(det),
        )
    try:
        court_x, court_y = image_to_court(fp, homography)
    except Exception:  # noqa: BLE001 投影失败保留 candidate（投影修复问题）
        return PreAssociationCandidate(
            view_id=view_id, source_frame_index=source_frame_index, origin=origin,
            image_footpoint=fp, court_position_ft=None, canonical_position_ft=None,
            projection_status="projection_failed", intrinsic_quality=_quality_of(det),
        )
    court_position = (float(court_x), float(court_y))
    status = classify_projection_status([court_x, court_y])
    canonical = None
    if orientation is not None:
        try:
            canonical = local_to_canonical(court_x, court_y, orientation)
        except Exception:  # noqa: BLE001
            canonical = None
    return PreAssociationCandidate(
        view_id=view_id,
        source_frame_index=source_frame_index,
        origin=origin,
        image_footpoint=fp,
        court_position_ft=court_position,
        canonical_position_ft=canonical,
        projection_status=status,
        intrinsic_quality=_quality_of(det),
    )


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def pre_associate(
    *,
    view_evidence: dict[str, list[tuple[Any, str]]],  # view_id -> [(det, origin)]
    homography_by_view: dict[str, Any],
    orientation_by_view: dict[str, CourtOrientation | None],
    source_frame_index_by_view: dict[str, int],
    global_predictions: dict[str, tuple[float, float, float]],  # GlobalState(t-1).predict_all
    pre_association_gate_ft: float = 3.0,
    ambiguity_margin: float = 0.15,
) -> PreAssociationResult:
    """对两路 ROI-filtered evidence 做 pre-association（只读，一对一匹配 + gate + ambiguity）。

    输入 `view_evidence`：`view_id -> [(det, origin)]`，其中 det 来自
    `PreparedViewFrame.roi_filtered_base` 与成功的 `pre_tick_guided`（保留 origin）。
    raw detections 不参与（球场外人员不得成为强 candidate）。
    """
    result = PreAssociationResult()
    # 1) 每 view 构建 canonical candidate
    candidates_by_view: dict[str, list[PreAssociationCandidate]] = {}
    for view_id, evidence in view_evidence.items():
        homography = homography_by_view.get(view_id)
        orientation = orientation_by_view.get(view_id)
        frame_index = source_frame_index_by_view.get(view_id, 0)
        cands: list[PreAssociationCandidate] = []
        for det, origin in evidence:
            if homography is None:
                continue
            cand = build_candidate(
                view_id=view_id, source_frame_index=frame_index, det=det, origin=origin,
                homography=homography, orientation=orientation,
            )
            if cand.court_position_ft is not None:
                cands.append(cand)
        candidates_by_view[view_id] = cands
        result.candidates.extend(cands)

    if not global_predictions:
        # 无预测：全部 unmatched（不制造归属）
        for cand in result.candidates:
            cand.match_status = "unmatched"
        return result

    # 2) 每 view 一对一匹配（min-cost）+ gate + ambiguity rejection
    for view_id, cands in candidates_by_view.items():
        if not cands or not global_predictions:
            for cand in cands:
                cand.match_status = "unmatched"
            continue
        # 每 view 内：candidate × global prediction 的 cost 矩阵（residual 距离）
        pred_ids = list(global_predictions)
        cand_keys = [str(id(c)) for c in cands if c.canonical_position_ft is not None]
        ranking: dict[str, dict[str, float]] = {}
        feasibility: dict[str, dict[str, float]] = {}
        # 双向填充（min_cost_matching 在 secondary 多于 reference 时会翻转 key 顺序访问）
        for cand in cands:
            if cand.canonical_position_ft is None:
                cand.match_status = "projection_failed"
                continue
            key = str(id(cand))
            ranking[key] = {}
            feasibility[key] = {}
            for gid in pred_ids:
                px, py, _unc = global_predictions[gid]
                cost = _dist(cand.canonical_position_ft, (px, py))
                ranking[key][gid] = cost
                feasibility[key][gid] = cost
        for gid in pred_ids:
            ranking.setdefault(gid, {})
            feasibility.setdefault(gid, {})
            for cand in cands:
                if cand.canonical_position_ft is None:
                    continue
                key = str(id(cand))
                cost = ranking[key].get(gid, float("inf"))
                ranking[gid][key] = cost
                feasibility[gid][key] = cost
        # 一对一匹配：复用 max-cardinality min-cost primitive
        from app.vision.multiview.association import min_cost_matching

        pairs = min_cost_matching(
            cand_keys,
            pred_ids,
            ranking,
            feasibility_cost=feasibility,
            max_feasibility_cost=pre_association_gate_ft,
        )
        matched_cands = {int(key): gid for key, gid in pairs}
        # ambiguity rejection：second-best margin
        for cand in cands:
            cand_key = str(id(cand))
            if cand_key not in ranking:
                continue
            matched = matched_cands.get(id(cand))
            if matched is None:
                cand.match_status = "unmatched"
                continue
            cand.matched_global_id = matched
            cand.residual_ft = ranking[cand_key][matched]
            # second-best 计算 margin
            sorted_costs = sorted(ranking[cand_key].values())
            if len(sorted_costs) >= 2:
                cand.ambiguity_margin = sorted_costs[1] - sorted_costs[0]
            else:
                cand.ambiguity_margin = float("inf")
            if cand.ambiguity_margin is not None and cand.ambiguity_margin >= ambiguity_margin:
                cand.match_status = "strong"
            else:
                cand.match_status = "ambiguous"
    return result
