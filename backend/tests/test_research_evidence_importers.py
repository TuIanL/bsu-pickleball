"""Read-only import of historical four-player quality reports.

The sample payload below is trimmed from a real artifact
(``job-43e7475fd8/four_player_identification_quality.json``); only bulky nested
sections are omitted. The point of these tests is that absent information stays
absent.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.hashing import snapshot_file
from app.research_evidence.importers import (
    NEVER_RECORDED_FIELDS,
    ArtifactImportError,
    UnsupportedSchemaVersion,
    import_four_player_quality,
    import_quality_report_file,
    is_metadata_sidecar,
    iter_quality_reports,
    load_json_read_only,
)

REAL_QUALITY_PAYLOAD = {
    "schema_version": "four-player-identification-quality.v1",
    "job_id": "job-43e7475fd8",
    "baseline_job_id": None,
    "status": "available",
    "detail": "",
    "algorithm_version": "motion-aware-v1+clothing-hsv-lab.v1",
    "config_signature": None,
    "attempted_ticks": 6266,
    "duration_seconds": 208.83333399999998,
    "confirmed_roster_count": 4,
    "verdict": "fail",
    "failure_reasons": [
        "Player_1.longest_gap",
        "Player_2.longest_gap",
        "Player_3.longest_gap",
    ],
}


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-importers-") as tmp:
        yield Path(tmp)


def test_real_report_keeps_its_failure_verdict():
    record = import_four_player_quality(REAL_QUALITY_PAYLOAD)

    assert record.verdict == "fail"
    assert record.verdict_source == "quality_report"
    assert record.job_id == "job-43e7475fd8"
    assert record.failure_reasons == (
        "Player_1.longest_gap",
        "Player_2.longest_gap",
        "Player_3.longest_gap",
    )


def test_ranges_and_counts_are_preserved():
    record = import_four_player_quality(REAL_QUALITY_PAYLOAD)

    assert record.duration_seconds == pytest.approx(208.83333399999998)
    assert record.attempted_ticks == 6266
    assert record.confirmed_roster_count == 4
    assert record.algorithm_version == "motion-aware-v1+clothing-hsv-lab.v1"


def test_never_recorded_fields_are_always_flagged_missing():
    """A v1 report has no code revision and no sync digest; both stay missing."""
    record = import_four_player_quality(REAL_QUALITY_PAYLOAD)

    for field in NEVER_RECORDED_FIELDS:
        assert field in record.missing_fields


def test_null_config_signature_is_recorded_instead_of_invented():
    record = import_four_player_quality(REAL_QUALITY_PAYLOAD)

    assert record.config_signature is None
    assert "config_signature" in record.missing_fields
    assert record.baseline_job_id is None
    assert "baseline_job_id" in record.missing_fields


def test_missing_verdict_becomes_unknown_not_pass():
    payload = {k: v for k, v in REAL_QUALITY_PAYLOAD.items() if k != "verdict"}

    record = import_four_player_quality(payload)

    assert record.verdict == "unknown"
    assert record.verdict_source == "none"
    assert "verdict" in record.missing_fields


def test_unrecognised_verdict_value_is_not_trusted():
    payload = dict(REAL_QUALITY_PAYLOAD, verdict="probably-fine")

    record = import_four_player_quality(payload)

    assert record.verdict == "unknown"
    assert record.verdict_source == "none"


def test_unknown_schema_version_is_rejected():
    payload = dict(REAL_QUALITY_PAYLOAD, schema_version="four-player-identification-quality.v2")

    with pytest.raises(UnsupportedSchemaVersion):
        import_four_player_quality(payload)


def test_non_mapping_payload_is_rejected():
    with pytest.raises(ArtifactImportError):
        import_four_player_quality(["not", "a", "report"])


def test_missing_job_id_is_rejected():
    payload = {k: v for k, v in REAL_QUALITY_PAYLOAD.items() if k != "job_id"}

    with pytest.raises(ArtifactImportError):
        import_four_player_quality(payload)


def test_non_numeric_duration_is_rejected_rather_than_coerced():
    payload = dict(REAL_QUALITY_PAYLOAD, duration_seconds="about 3 minutes")

    with pytest.raises(ArtifactImportError):
        import_four_player_quality(payload)


# --- filesystem side --------------------------------------------------------


def test_appledouble_sidecars_are_skipped(tmp_path):
    real = tmp_path / "four_player_identification_quality.json"
    real.write_text(json.dumps(REAL_QUALITY_PAYLOAD), encoding="utf-8")
    sidecar = tmp_path / "._four_player_identification_quality.json"
    sidecar.write_bytes(b"\x00\x05\x16\x07binary resource fork")
    (tmp_path / ".DS_Store").write_bytes(b"junk")

    found = list(iter_quality_reports(tmp_path))

    assert found == [real]
    assert is_metadata_sidecar(sidecar) is True
    assert is_metadata_sidecar(real) is False


def test_import_from_file_does_not_modify_it(tmp_path):
    target = tmp_path / "four_player_identification_quality.json"
    target.write_text(json.dumps(REAL_QUALITY_PAYLOAD), encoding="utf-8")
    before = snapshot_file(target)
    payload_before = target.read_bytes()

    record = import_quality_report_file(target)

    after = snapshot_file(target)
    assert record.verdict == "fail"
    assert before.matches(after)
    assert target.read_bytes() == payload_before


def test_missing_file_raises_import_error(tmp_path):
    with pytest.raises(ArtifactImportError):
        import_quality_report_file(tmp_path / "absent.json")


def test_malformed_json_raises_import_error(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(ArtifactImportError):
        load_json_read_only(broken)
