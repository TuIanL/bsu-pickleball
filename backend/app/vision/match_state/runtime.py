"""Dependency-light formal segmentation runtime orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .artifact import SegmentationArtifact, build_segmentation_artifact
from .decoder import decode_state_timeline_result
from .package import ModelPackageCache, ModelPackageError, ProductionModelPackage, load_production_package


_DEFAULT_PACKAGE_CACHE = ModelPackageCache()


@dataclass(frozen=True)
class SegmentationInput:
    capture_take_id: str
    planning_job_id: str
    samples: tuple[dict[str, Any], ...]
    input_fingerprint: str
    sync_calibration_revision: int | None
    timing_authority: str
    coverage: float = 1.0
    view_mask: tuple[str, ...] = ("cam_1", "cam_2")
    # Long CaptureTake jobs provide a one-shot stream so RGB tensors are
    # inferred in bounded batches rather than retained for the full video.
    sample_factory: Callable[[], Iterable[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class SegmentationResult:
    status: str
    artifact: SegmentationArtifact | None
    error_code: str | None = None
    detail: str | None = None


class MatchStateSegmentationRuntime:
    def __init__(self, *, package_loader=load_production_package, package_cache: ModelPackageCache | None = None) -> None:
        self.package_loader = package_loader
        # Keep the cache process-local so repeated CaptureTake runs do not
        # reload the same verified weights.  Tests/deployments may inject an
        # isolated cache explicitly.
        self.package_cache = package_cache or _DEFAULT_PACKAGE_CACHE

    def run(
        self,
        source: SegmentationInput,
        *,
        package_dir: str,
        device: str = "cpu",
        required_profile: str = "match_default",
        predictor: Callable[[ProductionModelPackage, tuple[dict[str, Any], ...], object], Iterable[dict[str, Any]]] | None = None,
    ) -> SegmentationResult:
        samples = tuple(source.samples) if source.sample_factory is None else None
        if samples is not None and any(bool(item.get("input_unavailable")) for item in samples):
            return SegmentationResult("input_unavailable", None, "input_unavailable", "双摄 CaptureTrack 媒体不可用")
        if samples is not None and any(bool(item.get("sync_unavailable")) for item in samples):
            return SegmentationResult("sync_unavailable", None, "sync_unavailable", "双摄同步标定或时间 authority 不可用")
        if samples is not None and any(bool(item.get("model_unavailable")) for item in samples):
            detail = next((str(item.get("detail")) for item in samples if item.get("detail")), "正式模型包不可用")
            return SegmentationResult("model_unavailable", None, "model_unavailable", detail)
        if samples is not None and (not samples or source.coverage <= 0):
            return SegmentationResult("input_unavailable", None, "input_unavailable", "双摄输入没有可用采样")
        if len(source.view_mask) < 2 or source.sync_calibration_revision is None:
            return SegmentationResult("sync_unavailable", None, "sync_unavailable", "双摄同步标定不可用")
        try:
            package = self.package_loader(package_dir, required_profile=required_profile)
        except ModelPackageError as exc:
            status = "input_unavailable" if exc.code == "input_unavailable" else "model_unavailable"
            return SegmentationResult(status, None, exc.code, str(exc))
        minimum_coverage = float(package.thresholds.get("minimum_coverage", 0.75))
        observed_coverage = float(source.coverage)
        try:
            model = self.package_cache.get(package, device)
            rows = source.sample_factory() if source.sample_factory is not None else iter(samples or ())
            predicted_rows: list[dict[str, Any]] = []
            chunk: list[dict[str, Any]] = []
            saw_row = False
            total_rows = 0
            usable_rows = 0

            def flush_chunk(items: list[dict[str, Any]]) -> None:
                nonlocal observed_coverage, saw_row, total_rows, usable_rows
                if not items:
                    return
                saw_row = True
                if any(bool(item.get("input_unavailable")) for item in items):
                    raise ModelPackageError("双摄 CaptureTrack 媒体不可用", code="input_unavailable")
                if any(bool(item.get("sync_unavailable")) for item in items):
                    raise ModelPackageError("双摄同步标定或时间 authority 不可用", code="sync_unavailable")
                if any(bool(item.get("model_unavailable")) for item in items):
                    detail = next((str(item.get("detail")) for item in items if item.get("detail")), "正式模型包不可用")
                    raise ModelPackageError(detail, code="model_unavailable")
                total_rows += len(items)
                usable: list[dict[str, Any]] = []
                usable_positions: list[int] = []
                missing: list[dict[str, Any]] = []
                for position, item in enumerate(items):
                    if (
                        item.get("model_input") is not None
                        or item.get("tensor") is not None
                        or _has_prediction_fields((item,))
                    ):
                        usable.append(item)
                        usable_positions.append(position)
                    else:
                        missing.append(item)
                usable_rows += len(usable)
                if _has_prediction_fields(usable):
                    outputs = usable
                elif predictor is not None:
                    outputs = tuple(predictor(package, tuple(usable), model))
                elif hasattr(model, "predict_samples"):
                    outputs = tuple(model.predict_samples(tuple(usable)))
                else:
                    raise ModelPackageError("正式模型包没有可用的推理适配器", code="model_unavailable")
                output_by_position: dict[int, dict[str, Any]] = {}
                # Discard the large RGB tensor immediately after inference;
                # only timing/probability fields are needed by the decoder.
                for position, output in zip(usable_positions, outputs, strict=True):
                    value = dict(output)
                    value.pop("model_input", None)
                    value.pop("tensor", None)
                    output_by_position[position] = value
                # Preserve chronological spacing for an occasional missing
                # media window without asking the RGB adapter to tensorize a
                # row it cannot observe.  The decoder treats this as unknown
                # evidence; the aggregate coverage gate below decides whether
                # the run remains publishable.
                missing_positions = set(range(len(items))) - set(usable_positions)
                for position, item in enumerate(items):
                    if position in missing_positions:
                        output_by_position[position] = {
                            **item,
                            "state_probabilities": {"rally_active": 0.0, "non_play": 0.0, "unknown": 1.0},
                            "coverage": 0.0,
                            "insufficient_evidence": True,
                        }
                predicted_rows.extend(output_by_position[position] for position in range(len(items)))

            for row in rows:
                chunk.append(row)
                if len(chunk) >= 8:
                    flush_chunk(chunk)
                    chunk = []
            flush_chunk(chunk)
            if total_rows > 0:
                observed_coverage = min(observed_coverage, usable_rows / total_rows)
            if not saw_row or observed_coverage <= 0:
                raise ModelPackageError("双摄输入没有可用采样", code="input_unavailable")
            if observed_coverage < minimum_coverage:
                return SegmentationResult(
                    "low_evidence", None, "low_evidence",
                    f"双摄有效证据覆盖率 {observed_coverage:.3f} 低于门槛 {minimum_coverage:.3f}",
                )
            predicted = tuple(predicted_rows)
            decoded_result = decode_state_timeline_result(predicted, **_decoder_kwargs(package.thresholds))
            segments_result = decoded_result["segments"]
        except ModelPackageError as exc:
            status = "input_unavailable" if exc.code == "input_unavailable" else "model_unavailable"
            return SegmentationResult(status, None, exc.code, str(exc))
        except Exception as exc:  # runtime boundary: never leak implementation details as status
            return SegmentationResult("inference_failed", None, "inference_failed", str(exc))
        segments = tuple(
            {
                "segment_id": f"{source.planning_job_id}:rally:{index + 1}",
                "ordinal": index + 1,
                "start_ms": int(round(float(item["start_ms"]))),
                "end_ms": int(round(float(item["end_ms"]))),
                "confidence": float(item.get("confidence", 0.0)),
                "evidence_count": int(item.get("evidence_window_count", 0)),
                "boundary_evidence": item.get("boundary_evidence", {}),
            }
            for index, item in enumerate(segments_result)
        )
        status = "succeeded" if segments else "valid_no_rallies"
        artifact = build_segmentation_artifact(
            planning_job_id=source.planning_job_id, capture_take_id=source.capture_take_id,
            run_id=f"seg_{hashlib.sha256((source.planning_job_id + source.input_fingerprint).encode()).hexdigest()[:16]}",
            status=status,
            model={"package_id": package.package_id, "model_version": package.version, "profile": required_profile, "device": device, "package_sha256": package.package_sha256, "weights_sha256": package.weights_sha256, "decoder_sha256": package.decoder_sha256},
            input_provenance={"input_fingerprint": source.input_fingerprint, "sync_calibration_revision": source.sync_calibration_revision, "timing_authority": source.timing_authority, "coverage": observed_coverage, "view_mask": list(source.view_mask)},
            decoder=package.thresholds,
            state_summary={
                "sample_count": len(predicted),
                "unknown_rate": float(decoded_result.get("unknown_rate", _unknown_rate(predicted))),
                "step_ms": decoded_result.get("step_ms"),
            },
            segments=segments,
            state_timeline=decoded_result["windows"],
        )
        return SegmentationResult(status, artifact)


def _decoder_kwargs(thresholds: dict[str, Any]) -> dict[str, Any]:
    return {
        "minimum_confidence": float(thresholds.get("minimum_confidence", 0.65)),
        "minimum_coverage": float(thresholds.get("minimum_coverage", 0.75)),
        "minimum_duration_ms": int(thresholds.get("minimum_duration_ms", 500)),
        "hysteresis": float(thresholds.get("hysteresis", 0.1)),
    }


def _unknown_rate(samples: Iterable[dict[str, Any]]) -> float:
    values = list(samples)
    if not values:
        return 1.0
    return round(sum(float(item.get("unknown_probability", 0.0)) for item in values) / len(values), 6)


def _has_prediction_fields(samples: Iterable[dict[str, Any]]) -> bool:
    values = list(samples)
    return bool(values) and all(
        isinstance(item, dict)
        and (
            "active_probability" in item
            or isinstance(item.get("state_probabilities"), (dict, list))
            or isinstance(item.get("probabilities"), (dict, list))
        )
        for item in values
    )
