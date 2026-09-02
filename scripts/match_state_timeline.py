"""比赛状态滑窗时序解码和回合级评估。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

STATE_CLASSES = ("rally_active", "non_play", "unknown")


def _segment_duration(segment: dict[str, Any]) -> float:
    return max(0.0, float(segment["end_ms"]) - float(segment["start_ms"]))


def _iou(first: dict[str, Any], second: dict[str, Any]) -> float:
    start = max(float(first["start_ms"]), float(second["start_ms"]))
    end = min(float(first["end_ms"]), float(second["end_ms"]))
    intersection = max(0.0, end - start)
    union = _segment_duration(first) + _segment_duration(second) - intersection
    return intersection / union if union > 0 else 0.0


def _center_label(timestamp_ms: float, ground_truth: list[dict[str, Any]]) -> str:
    return (
        "rally_active"
        if any(float(item["start_ms"]) <= timestamp_ms < float(item["end_ms"]) for item in ground_truth)
        else "non_play"
    )


def decode_state_timeline(
    windows: Iterable[dict[str, Any]],
    *,
    minimum_confidence: float = 0.65,
    minimum_coverage: float = 0.75,
    minimum_duration_ms: int = 500,
    hysteresis: float = 0.1,
    unknown_on_insufficient_evidence: bool = True,
) -> dict[str, Any]:
    """把窗口概率解码为连续状态和候选 rally 区间。

    窗口时间戳是窗口中心；候选边界使用相邻中心间隔的一半扩展，并在
    最短持续时间门禁后输出。迟滞只作用于 rally_active 的进入/退出。
    """

    ordered = sorted(
        (dict(item) for item in windows), key=lambda item: float(item.get("center_ms", item.get("timestamp_ms", 0)))
    )
    if not ordered:
        return {"windows": [], "segments": [], "unknown_rate": 0.0}
    centers = [float(item.get("center_ms", item.get("timestamp_ms", 0))) for item in ordered]
    deltas = [
        centers[index] - centers[index - 1] for index in range(1, len(centers)) if centers[index] > centers[index - 1]
    ]
    step_ms = min(deltas) if deltas else 500.0
    decoded: list[dict[str, Any]] = []
    active_latched = False
    for item, center_ms in zip(ordered, centers, strict=True):
        probabilities = item.get("state_probabilities", item.get("probabilities", {}))
        if isinstance(probabilities, list):
            probabilities = {
                STATE_CLASSES[index]: float(value) for index, value in enumerate(probabilities[: len(STATE_CLASSES)])
            }
        if not isinstance(probabilities, dict):
            probabilities = {}
        active_probability = float(probabilities.get("rally_active", 0.0))
        non_play_probability = float(probabilities.get("non_play", 0.0))
        confidence = max(active_probability, non_play_probability)
        coverage = float(item.get("coverage", item.get("input_coverage", 1.0)))
        coverage_ok = coverage >= minimum_coverage and not bool(item.get("insufficient_evidence", False))
        evidence_ok = coverage_ok and (confidence >= minimum_confidence or active_latched)
        if not coverage_ok or (not active_latched and confidence < minimum_confidence):
            state = "unknown" if unknown_on_insufficient_evidence else "non_play"
            active_latched = False
        elif active_latched:
            active_latched = active_probability >= max(0.0, minimum_confidence - hysteresis)
            state = "rally_active" if active_latched else "non_play"
        else:
            active_latched = active_probability >= min(1.0, minimum_confidence + hysteresis)
            state = "rally_active" if active_latched else "non_play"
        decoded.append(
            {
                **item,
                "center_ms": center_ms,
                "state": state,
                "confidence": round(confidence, 6),
                "coverage": round(coverage, 6),
                "evidence_ok": evidence_ok,
            }
        )

    # 删除低于最短持续时间的 active 碎片；对应窗口仍保留在窗口输出中。
    index = 0
    while index < len(decoded):
        if decoded[index]["state"] != "rally_active":
            index += 1
            continue
        end = index
        while end + 1 < len(decoded) and decoded[end + 1]["state"] == "rally_active":
            end += 1
        duration = decoded[end]["center_ms"] - decoded[index]["center_ms"] + step_ms
        if duration < minimum_duration_ms:
            for cursor in range(index, end + 1):
                decoded[cursor]["state"] = "non_play"
                decoded[cursor]["short_fragment_suppressed"] = True
        index = end + 1

    segments: list[dict[str, Any]] = []
    index = 0
    while index < len(decoded):
        if decoded[index]["state"] != "rally_active":
            index += 1
            continue
        end = index
        while end + 1 < len(decoded) and decoded[end + 1]["state"] == "rally_active":
            end += 1
        start_ms = max(0.0, decoded[index]["center_ms"] - step_ms * 0.5)
        end_ms = decoded[end]["center_ms"] + step_ms * 0.5
        probabilities = [
            float(decoded[cursor].get("state_probabilities", {}).get("rally_active", 0.0))
            for cursor in range(index, end + 1)
        ]
        segments.append(
            {
                "segment_index": len(segments) + 1,
                "start_ms": round(start_ms, 3),
                "end_ms": round(end_ms, 3),
                "duration_ms": round(end_ms - start_ms, 3),
                "confidence": round(sum(probabilities) / max(len(probabilities), 1), 6),
                "evidence_window_count": end - index + 1,
                "status": "unreviewed",
            }
        )
        index = end + 1
    unknown_rate = sum(item["state"] == "unknown" for item in decoded) / max(len(decoded), 1)
    return {"windows": decoded, "segments": segments, "unknown_rate": round(unknown_rate, 6), "step_ms": step_ms}


def _match_segments(
    predicted: list[dict[str, Any]], ground_truth: list[dict[str, Any]]
) -> list[tuple[int, int, float]]:
    candidates = [
        (iou, prediction_index, target_index)
        for prediction_index, prediction in enumerate(predicted)
        for target_index, target in enumerate(ground_truth)
        if (iou := _iou(prediction, target)) > 0.0
    ]
    matches: list[tuple[int, int, float]] = []
    used_predictions: set[int] = set()
    used_targets: set[int] = set()
    for iou, prediction_index, target_index in sorted(candidates, reverse=True):
        if prediction_index in used_predictions or target_index in used_targets:
            continue
        used_predictions.add(prediction_index)
        used_targets.add(target_index)
        matches.append((prediction_index, target_index, iou))
    return matches


def evaluate_rally_segments(
    predicted: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    *,
    boundary_tolerances_ms: tuple[int, ...] = (250, 500, 1000),
) -> dict[str, Any]:
    """计算回合 IoU、边界 MAE、漏检和误检。"""

    matches = _match_segments(predicted, ground_truth)
    matched_predictions = {item[0] for item in matches}
    matched_targets = {item[1] for item in matches}
    pairs = []
    for prediction_index, target_index, iou in matches:
        prediction = predicted[prediction_index]
        target = ground_truth[target_index]
        start_error = abs(float(prediction["start_ms"]) - float(target["start_ms"]))
        end_error = abs(float(prediction["end_ms"]) - float(target["end_ms"]))
        pairs.append(
            {
                "prediction_index": prediction_index,
                "target_index": target_index,
                "iou": round(iou, 6),
                "start_error_ms": round(start_error, 3),
                "end_error_ms": round(end_error, 3),
            }
        )
    start_errors = [item["start_error_ms"] for item in pairs]
    end_errors = [item["end_error_ms"] for item in pairs]
    tolerance_hits = {
        str(tolerance): sum(item["start_error_ms"] <= tolerance and item["end_error_ms"] <= tolerance for item in pairs)
        for tolerance in boundary_tolerances_ms
    }
    return {
        "ground_truth_count": len(ground_truth),
        "predicted_count": len(predicted),
        "matched_count": len(matches),
        "missed_count": len(ground_truth) - len(matched_targets),
        "false_positive_count": len(predicted) - len(matched_predictions),
        "precision": len(matches) / max(len(predicted), 1),
        "recall": len(matches) / max(len(ground_truth), 1),
        "mean_iou": sum(item["iou"] for item in pairs) / max(len(pairs), 1),
        "boundary_start_mae_ms": sum(start_errors) / max(len(start_errors), 1),
        "boundary_end_mae_ms": sum(end_errors) / max(len(end_errors), 1),
        "boundary_tolerance_hits": tolerance_hits,
        "matches": pairs,
    }


def evaluate_state_windows(windows: list[dict[str, Any]], ground_truth: list[dict[str, Any]]) -> dict[str, Any]:
    """按窗口中心计算 active/non-play/unknown 的分类指标。"""

    matrix = {actual: {predicted: 0 for predicted in STATE_CLASSES} for actual in STATE_CLASSES}
    for item in windows:
        actual = _center_label(float(item["center_ms"]), ground_truth)
        predicted = str(item.get("state", "unknown"))
        if predicted not in STATE_CLASSES:
            predicted = "unknown"
        matrix[actual][predicted] += 1
    per_class: dict[str, dict[str, float]] = {}
    for label in STATE_CLASSES:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in STATE_CLASSES) - tp
        fn = sum(matrix[label].values()) - tp
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(STATE_CLASSES)
    return {
        "sample_count": len(windows),
        "macro_f1": macro_f1,
        "unknown_rate": sum(item.get("state") == "unknown" for item in windows) / max(len(windows), 1),
        "per_class": per_class,
        "confusion_matrix": [[matrix[actual][predicted] for predicted in STATE_CLASSES] for actual in STATE_CLASSES],
    }


def evaluate_timeline(
    windows: list[dict[str, Any]],
    predicted_segments: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    *,
    boundary_tolerances_ms: tuple[int, ...] = (250, 500, 1000),
) -> dict[str, Any]:
    state = evaluate_state_windows(windows, ground_truth)
    rally = evaluate_rally_segments(predicted_segments, ground_truth, boundary_tolerances_ms=boundary_tolerances_ms)
    return {"state": state, "rally": rally}
