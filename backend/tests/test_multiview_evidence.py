from app.vision.multiview.artifact import evidence_summary_from_artifact


def _sample(status: str, views: list[str]) -> dict[str, object]:
    return {
        "fusion_status": status,
        "contributing_views": views,
        "view_observations": {view: {} for view in views},
    }


def test_evidence_mode_zero_dual_samples_is_single_view_fallback():
    result = evidence_summary_from_artifact(
        {"samples": [_sample("single_view_fallback", ["reference"]), _sample("predicted", [])]}
    )
    assert result["dual_evidence_samples"] == 0
    assert result["single_view_fallback_samples"] == 1
    assert result["predicted_samples"] == 1
    assert result["effective_mode"] == "single_view_fallback"


def test_evidence_mode_low_coverage_is_degraded():
    samples = [_sample("dual_observed", ["reference", "secondary"])]
    samples.extend(_sample("single_view_fallback", ["reference"]) for _ in range(3))
    result = evidence_summary_from_artifact({"samples": samples})
    assert result["secondary_available_samples"] == 1
    assert result["effective_multiview_ratio"] == 0.25
    assert result["effective_mode"] == "multiview_degraded"


def test_evidence_mode_normal_coverage_is_fused():
    samples = [_sample("dual_observed", ["reference", "secondary"]) for _ in range(3)]
    samples.append(_sample("single_view_fallback", ["reference"]))
    result = evidence_summary_from_artifact({"samples": samples})
    assert result["dual_evidence_samples"] == 3
    assert result["effective_multiview_ratio"] == 0.75
    assert result["effective_mode"] == "multiview_fused"
