"""Pure temporal decoder shared by formal inference and offline QA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

STATE_CLASSES = ("rally_active", "non_play", "unknown")


@dataclass(frozen=True)
class DecodedRally:
    start_ms: int
    end_ms: int
    confidence: float
    evidence_count: int


def decode_state_timeline_result(
    samples: Iterable[dict[str, Any]],
    *,
    minimum_confidence: float = 0.65,
    minimum_coverage: float = 0.75,
    minimum_duration_ms: int = 500,
    hysteresis: float = 0.1,
    unknown_on_insufficient_evidence: bool = True,
) -> dict[str, Any]:
    """Decode state probabilities using the validated candidate semantics.

    Window timestamps are centres. Rally boundaries expand by half the
    smallest positive centre delta, and short active fragments are suppressed
    while their decoded windows remain available for diagnostics.
    """
    ordered = sorted(
        (_normalize(item) for item in samples if isinstance(item, dict)),
        key=lambda item: float(item.get("center_ms", item.get("timestamp_ms", 0))),
    )
    if not ordered:
        return {"windows": [], "segments": [], "unknown_rate": 0.0, "step_ms": 0.0}
    centers = [float(item.get("center_ms", item.get("timestamp_ms", 0))) for item in ordered]
    deltas = [
        centers[index] - centers[index - 1]
        for index in range(1, len(centers))
        if centers[index] > centers[index - 1]
    ]
    step_ms = min(deltas) if deltas else 500.0
    decoded: list[dict[str, Any]] = []
    active_latched = False
    for item, center_ms in zip(ordered, centers, strict=True):
        probabilities = item.get("state_probabilities", item.get("probabilities", {}))
        if not isinstance(probabilities, dict):
            probabilities = {}
        active_probability = float(item.get("active_probability", probabilities.get("rally_active", 0.0)))
        non_play_probability = float(item.get("non_play_probability", probabilities.get("non_play", 0.0)))
        unknown_probability = float(item.get("unknown_probability", probabilities.get("unknown", 0.0)))
        probabilities = {
            **probabilities,
            "rally_active": active_probability,
            "non_play": non_play_probability,
            "unknown": unknown_probability,
        }
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
                "state_probabilities": probabilities,
                "state": state,
                "confidence": round(confidence, 6),
                "coverage": round(coverage, 6),
                "evidence_ok": evidence_ok,
            }
        )

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
            float(decoded[cursor]["state_probabilities"].get("rally_active", 0.0))
            for cursor in range(index, end + 1)
        ]
        segment_index = len(segments) + 1
        segments.append(
            {
                "candidate_id": f"candidate_{segment_index:04d}",
                "segment_index": segment_index,
                "start_ms": round(start_ms, 3),
                "end_ms": round(end_ms, 3),
                "duration_ms": round(end_ms - start_ms, 3),
                "confidence": round(sum(probabilities) / max(len(probabilities), 1), 6),
                "evidence_window_count": end - index + 1,
                "boundary_evidence": {
                    "window_index_start": index,
                    "window_index_end": end,
                    "first_active_center_ms": decoded[index]["center_ms"],
                    "last_active_center_ms": decoded[end]["center_ms"],
                    "first_active_probability": round(probabilities[0], 6),
                    "last_active_probability": round(probabilities[-1], 6),
                    "first_coverage": decoded[index]["coverage"],
                    "last_coverage": decoded[end]["coverage"],
                },
                "status": "unreviewed",
            }
        )
        index = end + 1
    unknown_rate = sum(item["state"] == "unknown" for item in decoded) / max(len(decoded), 1)
    return {"windows": decoded, "segments": segments, "unknown_rate": round(unknown_rate, 6), "step_ms": step_ms}


def decode_state_timeline(samples: Iterable[dict[str, Any]], **kwargs: Any) -> list[DecodedRally]:
    """Return typed rally ranges for the formal runtime."""
    result = decode_state_timeline_result(samples, **kwargs)
    return [
        DecodedRally(
            start_ms=int(round(float(item["start_ms"]))),
            end_ms=int(round(float(item["end_ms"]))),
            confidence=float(item.get("confidence", 0.0)),
            evidence_count=int(item.get("evidence_window_count", 0)),
        )
        for item in result["segments"]
    ]


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    probabilities = item.get("state_probabilities", item.get("probabilities", {}))
    if isinstance(probabilities, list):
        probabilities = {
            STATE_CLASSES[index]: float(value)
            for index, value in enumerate(probabilities[: len(STATE_CLASSES)])
        }
    if not isinstance(probabilities, dict):
        probabilities = {}
    timestamp = float(item.get("center_ms", item.get("timestamp_ms", 0)))
    return {
        **item,
        "center_ms": timestamp,
        "state_probabilities": probabilities,
        "active_probability": float(item.get("active_probability", probabilities.get("rally_active", 0.0))),
        "non_play_probability": float(item.get("non_play_probability", probabilities.get("non_play", 0.0))),
        "unknown_probability": float(item.get("unknown_probability", probabilities.get("unknown", 0.0))),
        "coverage": float(item.get("coverage", item.get("input_coverage", 1.0))),
    }
