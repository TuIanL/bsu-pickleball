"""Read-only importers for historical job artifacts.

Historical artifacts predate the research evidence contract. They carry no code
revision, no sync digest and sometimes no config signature. The importer records
those gaps as ``missing_fields`` and never fills them from the current HEAD: an
unknown version must stay unknown, otherwise a later audit would attribute old
results to new code.

Import is strictly read-only and tolerates exFAT metadata sidecars such as
``._name.json`` that macOS leaves next to real files.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

QUALITY_SCHEMA_VERSION = "four-player-identification-quality.v1"

# Fields that the v1 quality report has never recorded. They are always reported
# as missing so no caller can mistake "not present in the file" for "verified as
# equal to current HEAD".
NEVER_RECORDED_FIELDS: tuple[str, ...] = ("code_revision", "sync_digest")

_METADATA_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


class ArtifactImportError(ValueError):
    """Raised when a historical artifact cannot be imported faithfully."""


class UnsupportedSchemaVersion(ArtifactImportError):
    """Raised when a payload declares a schema this importer does not know."""


@dataclass(frozen=True)
class QualityRecord:
    """Normalised view of a four-player quality report."""

    job_id: str
    schema_version: str
    verdict: Literal["pass", "fail", "unknown"]
    verdict_source: Literal["quality_report", "none"]
    duration_seconds: float | None
    attempted_ticks: int | None
    confirmed_roster_count: int | None
    algorithm_version: str | None
    config_signature: str | None
    baseline_job_id: str | None
    failure_reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]


def is_metadata_sidecar(path: Path) -> bool:
    """True for exFAT/AppleDouble sidecars that must never be treated as data."""
    name = Path(path).name
    return name.startswith("._") or name in _METADATA_NAMES


def iter_quality_reports(job_dir: Path) -> Iterator[Path]:
    """Yield real quality reports in a job directory, skipping sidecars."""
    pattern = "*four_player_identification_quality.json"
    for candidate in sorted(Path(job_dir).glob(pattern)):
        if is_metadata_sidecar(candidate):
            continue
        if candidate.is_file():
            yield candidate


def load_json_read_only(path: Path) -> Any:
    """Read a JSON artifact without touching its mtime or content."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError as error:
        raise ArtifactImportError(f"产物不存在: {path}") from error
    except OSError as error:
        raise ArtifactImportError(f"产物不可读: {path}") from error
    except json.JSONDecodeError as error:
        raise ArtifactImportError(f"产物不是合法 JSON: {path}") from error


def _optional_str(payload: Mapping[str, Any], key: str, missing: list[str]) -> str | None:
    value = payload.get(key)
    if value is None or value == "":
        missing.append(key)
        return None
    return str(value)


def _optional_number(
    payload: Mapping[str, Any], key: str, missing: list[str]
) -> float | None:
    value = payload.get(key)
    if value is None:
        missing.append(key)
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ArtifactImportError(f"字段 {key} 不是数值: {value!r}") from error


def _optional_int(payload: Mapping[str, Any], key: str, missing: list[str]) -> int | None:
    value = payload.get(key)
    if value is None:
        missing.append(key)
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ArtifactImportError(f"字段 {key} 不是整数: {value!r}") from error


def import_four_player_quality(payload: Any) -> QualityRecord:
    """Normalise a v1 quality report, recording every absent field as missing."""
    if not isinstance(payload, Mapping):
        raise ArtifactImportError(
            f"质量报告应为对象，实际为 {type(payload).__name__}"
        )

    version = payload.get("schema_version")
    if version != QUALITY_SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"不支持的质量报告版本: {version!r}，期望 {QUALITY_SCHEMA_VERSION}"
        )

    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ArtifactImportError("质量报告缺少 job_id")

    missing: list[str] = list(NEVER_RECORDED_FIELDS)

    raw_verdict = payload.get("verdict")
    if raw_verdict in ("pass", "fail"):
        verdict: Literal["pass", "fail", "unknown"] = raw_verdict
        verdict_source: Literal["quality_report", "none"] = "quality_report"
    else:
        # 缺失或未知的判定不得当作 pass，也不得推测。
        verdict = "unknown"
        verdict_source = "none"
        missing.append("verdict")

    reasons_raw = payload.get("failure_reasons") or []
    if not isinstance(reasons_raw, list):
        raise ArtifactImportError("failure_reasons 应为数组")
    reasons = tuple(str(reason) for reason in reasons_raw)

    return QualityRecord(
        job_id=job_id,
        schema_version=str(version),
        verdict=verdict,
        verdict_source=verdict_source,
        duration_seconds=_optional_number(payload, "duration_seconds", missing),
        attempted_ticks=_optional_int(payload, "attempted_ticks", missing),
        confirmed_roster_count=_optional_int(payload, "confirmed_roster_count", missing),
        algorithm_version=_optional_str(payload, "algorithm_version", missing),
        config_signature=_optional_str(payload, "config_signature", missing),
        baseline_job_id=_optional_str(payload, "baseline_job_id", missing),
        failure_reasons=reasons,
        missing_fields=tuple(missing),
    )


def import_quality_report_file(path: Path) -> QualityRecord:
    """Import a quality report from disk, read-only."""
    return import_four_player_quality(load_json_read_only(path))


@dataclass(frozen=True)
class RunRange:
    """The span a run actually covered.

    ``derivation`` matters: ``result.json`` has never declared a start/end, so
    the span is reconstructed from observed track timestamps. That is evidence of
    coverage, not a declared analysis window, and must not be presented as one.
    """

    start_seconds: float
    end_seconds: float
    derivation: Literal["observed_tracks_span", "declared"]
    sample_count: int

    def contains(self, other: "RunRange") -> bool:
        return (
            self.start_seconds <= other.start_seconds
            and self.end_seconds >= other.end_seconds
        )

    def overlaps(self, other: "RunRange") -> bool:
        return not (
            self.end_seconds < other.start_seconds
            or other.end_seconds < self.start_seconds
        )

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class RunContext:
    """Declared analysis context of a run, when the artifact recorded one."""

    schema_version: str | None
    match_format: str | None
    expected_player_count: int | None
    players_per_side: int | None


@dataclass(frozen=True)
class RunRecord:
    """One historical run: what it covered, under which context, and its verdict."""

    job_id: str
    status: str
    generated_at: str | None
    video_id: str | None
    calibration_id: str | None
    observed_player_count: int | None
    range: RunRange | None
    context: RunContext
    missing_fields: tuple[str, ...]


def _import_run_context(raw: Any, missing: list[str]) -> RunContext:
    if not isinstance(raw, Mapping):
        missing.append("match_context")
        return RunContext(None, None, None, None)
    return RunContext(
        schema_version=_optional_str(raw, "schema_version", missing),
        match_format=_optional_str(raw, "match_format", missing),
        expected_player_count=_optional_int(raw, "expected_player_count", missing),
        players_per_side=_optional_int(raw, "players_per_side", missing),
    )


def _observed_track_span(raw_tracks: Any) -> RunRange | None:
    if not isinstance(raw_tracks, list):
        return None
    timestamps = [
        float(track["timestamp_seconds"])
        for track in raw_tracks
        if isinstance(track, Mapping)
        and isinstance(track.get("timestamp_seconds"), (int, float))
    ]
    if not timestamps:
        return None
    return RunRange(
        start_seconds=min(timestamps),
        end_seconds=max(timestamps),
        derivation="observed_tracks_span",
        sample_count=len(timestamps),
    )


def import_job_result(payload: Any) -> RunRecord:
    """Normalise a ``result.json`` into a run record.

    The range is reconstructed from track timestamps because the artifact has no
    window field. ``code_revision`` and ``sync_digest`` are reported missing for
    the same reason as in the quality importer: v1 results never carried them.
    """
    if not isinstance(payload, Mapping):
        raise ArtifactImportError(f"运行结果应为对象，实际为 {type(payload).__name__}")

    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ArtifactImportError("运行结果缺少 job_id")

    missing: list[str] = list(NEVER_RECORDED_FIELDS)

    range_ = _observed_track_span(payload.get("tracks"))
    if range_ is None:
        missing.append("range")

    return RunRecord(
        job_id=job_id,
        status=str(payload.get("status") or "unknown"),
        generated_at=_optional_str(payload, "generated_at", missing),
        video_id=_optional_str(payload, "video_id", missing),
        calibration_id=_optional_str(payload, "calibration_id", missing),
        observed_player_count=_optional_int(payload, "observed_player_count", missing),
        range=range_,
        context=_import_run_context(payload.get("match_context"), missing),
        missing_fields=tuple(missing),
    )


def import_job_result_file(path: Path) -> RunRecord:
    """Import a ``result.json`` from disk, read-only."""
    return import_job_result(load_json_read_only(path))


@dataclass(frozen=True)
class RunWithQuality:
    """A run paired with the quality verdict recorded for it, if any."""

    run: RunRecord
    quality: QualityRecord | None

    @property
    def verdict(self) -> str:
        return self.quality.verdict if self.quality else "unknown"

    @property
    def covers_whole_take(self) -> bool:
        """A run can only speak for its own span; it never certifies the take."""
        return False


def pair_runs_with_quality(
    runs: list[RunRecord], qualities: list[QualityRecord]
) -> tuple[RunWithQuality, ...]:
    """Pair runs to verdicts by job id, preserving each run as its own scope.

    Deliberately performs no merging, no best-of selection and no promotion: a
    passing 6-second run and a failing 200-second run coexist as two facts. Any
    aggregate that reports "the take passed" would be an over-claim, which is why
    this function returns a flat tuple rather than a summary verdict.
    """
    by_job = {quality.job_id: quality for quality in qualities}
    return tuple(
        RunWithQuality(run=run, quality=by_job.get(run.job_id)) for run in runs
    )
