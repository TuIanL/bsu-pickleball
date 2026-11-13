"""Usage classification and formal-input admission for research evidence.

Covers the 1.3 requirements: synthetic AVI, text pretending to be a video, and
files of unknown provenance must all be refused as formal research input.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.classification import (
    AdmissionError,
    UnreadableMediaError,
    assert_formal_input_eligible,
    classify_path_for_admission,
    classify_usage_kind,
    extension_matches_container,
    probe_container,
)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-classification-") as tmp:
        yield Path(tmp)

MP4_HEADER = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"
AVI_HEADER = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 64
MKV_HEADER = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
TS_HEADER = b"\x47" + b"\x00" * 187 + b"\x47" + b"\x00" * 100


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    target = tmp_path / name
    target.write_bytes(payload)
    return target


# --- container probing ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [
        ("clip.mp4", MP4_HEADER, "mp4"),
        ("clip.avi", AVI_HEADER, "avi"),
        ("clip.mkv", MKV_HEADER, "matroska"),
        ("clip.ts", TS_HEADER, "mpegts"),
    ],
)
def test_container_is_probed_from_header(tmp_path, name, payload, expected):
    assert probe_container(_write(tmp_path, name, payload)) == expected


def test_text_file_renamed_to_mp4_is_not_a_container(tmp_path):
    fake = _write(tmp_path, "fake.mp4", b"this is plainly a text file, not video")

    assert probe_container(fake) == "unknown"


def test_empty_and_truncated_files_are_unknown(tmp_path):
    assert probe_container(_write(tmp_path, "empty.mp4", b"")) == "unknown"
    assert probe_container(_write(tmp_path, "short.mp4", b"\x00\x00\x00\x18ftyp")) == "unknown"


def test_missing_file_raises_typed_error(tmp_path):
    with pytest.raises(UnreadableMediaError):
        probe_container(tmp_path / "does-not-exist.mp4")


# --- extension consistency --------------------------------------------------


@pytest.mark.parametrize(
    ("suffix", "container", "expected"),
    [
        (".mp4", "mp4", True),
        (".MP4", "mp4", True),
        (".mov", "mp4", True),
        (".avi", "avi", True),
        (".mkv", "matroska", True),
        (".ts", "mpegts", True),
        (".mp4", "avi", False),
        (".avi", "mp4", False),
        (".txt", "mp4", False),
        (".mp4", "unknown", False),
    ],
)
def test_extension_container_consistency(suffix, container, expected):
    assert extension_matches_container(suffix, container) is expected


# --- classification ---------------------------------------------------------


def test_operator_declaration_wins_over_root_policy():
    evidence = classify_usage_kind(
        declared="real", root_policy="fixture", container="mp4"
    )

    assert evidence.usage_kind == "real"
    assert evidence.basis == "operator_declared"


def test_root_policy_applies_when_nothing_is_declared():
    evidence = classify_usage_kind(declared=None, root_policy="fixture", container="avi")

    assert evidence.usage_kind == "fixture"
    assert evidence.basis == "root_policy"


def test_recognisable_container_without_evidence_stays_unknown():
    """A decodable-looking file is not evidence of research provenance."""
    evidence = classify_usage_kind(declared=None, root_policy=None, container="mp4")

    assert evidence.usage_kind == "unknown"
    assert evidence.basis == "no_evidence"


def test_unverified_container_reports_its_own_basis():
    evidence = classify_usage_kind(declared=None, root_policy=None, container="unknown")

    assert evidence.usage_kind == "unknown"
    assert evidence.basis == "container_unverified"


def test_evidence_serialises_into_manifest_field():
    evidence = classify_usage_kind(declared="real", root_policy=None, container="mp4")

    assert evidence.to_manifest_field() == {
        "basis": "operator_declared",
        "reason": "操作者显式声明 usage_kind=real",
    }


# --- formal-input admission -------------------------------------------------


def test_fixture_is_refused_as_formal_input():
    with pytest.raises(AdmissionError, match="夹具"):
        assert_formal_input_eligible(
            usage_kind="fixture", container="avi", suffix=".avi", digest_status="known"
        )


def test_unknown_provenance_is_refused():
    with pytest.raises(AdmissionError, match="未知"):
        assert_formal_input_eligible(
            usage_kind="unknown", container="mp4", suffix=".mp4", digest_status="known"
        )


def test_fake_video_is_refused_even_when_declared_real():
    with pytest.raises(AdmissionError, match="伪视频|容器"):
        assert_formal_input_eligible(
            usage_kind="real", container="unknown", suffix=".mp4", digest_status="known"
        )


def test_renamed_container_is_refused():
    with pytest.raises(AdmissionError, match="不一致"):
        assert_formal_input_eligible(
            usage_kind="real", container="avi", suffix=".mp4", digest_status="known"
        )


def test_unknown_digest_is_refused_for_formal_input():
    with pytest.raises(AdmissionError, match="摘要"):
        assert_formal_input_eligible(
            usage_kind="real", container="mp4", suffix=".mp4", digest_status="unknown"
        )


def test_genuine_real_media_is_admitted():
    assert_formal_input_eligible(
        usage_kind="real", container="mp4", suffix=".mp4", digest_status="known"
    )


# --- end to end -------------------------------------------------------------


def test_synthetic_avi_under_test_root_is_refused(tmp_path):
    """A structurally valid AVI is still a fixture when its root says so."""
    synthetic = _write(tmp_path, "synthetic_two_player.avi", AVI_HEADER)

    with pytest.raises(AdmissionError):
        classify_path_for_admission(
            synthetic, root_policy="fixture", digest_status="known"
        )


def test_text_pretending_to_be_video_is_refused(tmp_path):
    fake = _write(tmp_path, "fake.mp4", b"not video at all")

    with pytest.raises(AdmissionError):
        classify_path_for_admission(fake, declared="real", digest_status="known")


def test_real_declared_media_under_reference_root_is_admitted(tmp_path):
    real = _write(tmp_path, "174_merged.mp4", MP4_HEADER)

    evidence = classify_path_for_admission(
        real, declared="real", digest_status="known"
    )

    assert evidence.usage_kind == "real"
    assert evidence.basis == "operator_declared"


def test_probe_does_not_depend_on_file_size(tmp_path):
    """Only the header is read, so a huge file costs the same as a small one."""
    huge = tmp_path / "huge.mp4"
    with huge.open("wb") as handle:
        handle.write(MP4_HEADER)
        handle.write(b"\x00" * (2 * 1024 * 1024))

    assert probe_container(huge, max_bytes=512) == "mp4"
