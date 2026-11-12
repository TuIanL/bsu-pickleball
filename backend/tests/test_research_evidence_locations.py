"""Content identity and local location mapping for research evidence.

Covers the 1.2 requirements: identical content must keep one identity across
platform paths, distinct content must stay distinct even at equivalent paths,
and a shareable manifest must never carry an absolute machine path.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.research_evidence import (
    IdentityCollisionError,
    InvalidDigestError,
    LocationError,
    assert_no_local_paths,
    assign_content_ids,
    build_locator,
    find_local_paths,
    group_by_content,
    is_absolute_path,
    normalize_sha256,
    parse_locator,
    resolve_locator,
)
from app.research_evidence.locations import (
    AssetLocation,
    LocalLocationFile,
    SourceRoot,
)

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "research_evidence"
    / "v1"
    / "fixtures"
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_COLLIDING_PREFIX = "a" * 12 + "f" * 52
PACKAGE_ID = "pkg_0123456789ab"


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-locations-") as tmp:
        yield Path(tmp)


# --- content identity -------------------------------------------------------


def test_same_content_across_platform_paths_shares_one_identity():
    mac_locator = build_locator("root_captures", "2026-07-20/take/174_merged.mp4")
    windows_locator = build_locator("root_windows", r"2026-07-20\take\174_merged.mp4")

    groups = group_by_content({mac_locator: DIGEST_A, windows_locator: DIGEST_A})

    assert len(groups) == 1
    (asset_id, locators), = groups.items()
    assert locators == sorted([mac_locator, windows_locator])
    assert asset_id.startswith("a_")


def test_duplicate_copies_collapse_without_comparing_paths():
    """Two identical yolov8n.pt copies must map to a single asset id."""
    root_copy = build_locator("root_models", "yolov8n.pt")
    backend_copy = build_locator("root_models", "backend/yolov8n.pt")

    groups = group_by_content({root_copy: DIGEST_A, backend_copy: DIGEST_A})

    assert len(groups) == 1
    assert list(groups.values())[0] == sorted([root_copy, backend_copy])


def test_different_content_at_equivalent_paths_stays_distinct():
    mac_locator = build_locator("root_captures", "take/174.mp4")
    windows_locator = build_locator("root_windows", "take/174.mp4")

    ids = assign_content_ids({mac_locator: DIGEST_A, windows_locator: DIGEST_B})

    assert ids[mac_locator] != ids[windows_locator]


def test_short_id_prefix_collision_is_rejected():
    with pytest.raises(IdentityCollisionError):
        assign_content_ids(
            {
                "asset://root_x/one.mp4": DIGEST_A,
                "asset://root_x/two.mp4": DIGEST_COLLIDING_PREFIX,
            }
        )


def test_identity_is_stable_across_repeated_assignment():
    mapping = {
        build_locator("root_captures", "a/1.mp4"): DIGEST_A,
        build_locator("root_captures", "b/2.mp4"): DIGEST_B,
    }

    assert assign_content_ids(mapping) == assign_content_ids(dict(reversed(list(mapping.items()))))


@pytest.mark.parametrize(
    "bad_digest",
    ["", "a" * 63, "a" * 65, "g" * 64, "x" * 64, 123, None],
)
def test_invalid_digests_are_rejected(bad_digest):
    with pytest.raises(InvalidDigestError):
        normalize_sha256(bad_digest)


def test_uppercase_digest_is_normalised_rather_than_rejected():
    assert normalize_sha256(DIGEST_A.upper()) == DIGEST_A


# --- locators ---------------------------------------------------------------


def test_locator_round_trip():
    locator = build_locator("root_captures", "2026-07-20/take_x/174_merged.mp4")

    assert locator == "asset://root_captures/2026-07-20/take_x/174_merged.mp4"
    assert parse_locator(locator) == (
        "root_captures",
        "2026-07-20/take_x/174_merged.mp4",
    )


def test_windows_separators_are_normalised():
    assert (
        build_locator("root_windows", r"take\174_merged.mp4")
        == "asset://root_windows/take/174_merged.mp4"
    )


def test_dot_segments_are_collapsed():
    assert build_locator("root_x", "a/./b//c.mp4") == "asset://root_x/a/b/c.mp4"


@pytest.mark.parametrize(
    "bad_relative",
    ["/Volumes/Elements/a.mp4", "D:\\项目\\a.mp4", "\\\\server\\share\\a.mp4"],
)
def test_absolute_relative_paths_are_rejected(bad_relative):
    with pytest.raises(LocationError):
        build_locator("root_x", bad_relative)


@pytest.mark.parametrize("bad_relative", ["../secret.mp4", "a/../../b.mp4", "a/.."])
def test_upward_traversal_is_rejected(bad_relative):
    with pytest.raises(LocationError):
        build_locator("root_x", bad_relative)


@pytest.mark.parametrize("bad_root", ["Captures", "root-1", "root 1", "", "../root"])
def test_invalid_root_ids_are_rejected(bad_root):
    with pytest.raises(LocationError):
        build_locator(bad_root, "a.mp4")


def test_locator_without_scheme_is_rejected():
    with pytest.raises(LocationError):
        parse_locator("/Volumes/Elements/a.mp4")


# --- resolution -------------------------------------------------------------


def test_resolve_locator_joins_a_declared_root(tmp_path):
    root = tmp_path / "captures"
    target = root / "take" / "174_merged.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"placeholder")

    resolved = resolve_locator(
        build_locator("root_captures", "take/174_merged.mp4"),
        {"root_captures": str(root)},
    )

    assert resolved == target.resolve()


def test_resolve_locator_rejects_unauthorised_root(tmp_path):
    with pytest.raises(LocationError):
        resolve_locator(
            build_locator("root_other", "take/174.mp4"),
            {"root_captures": str(tmp_path)},
        )


@pytest.mark.parametrize(
    "value",
    ["/Volumes/Elements/a.mp4", "C:\\项目\\a.mp4", "D:/项目/a.mp4", "\\\\server\\share\\a.mp4"],
)
def test_absolute_path_detection_accepts_all_platform_forms(value):
    assert is_absolute_path(value)


@pytest.mark.parametrize("value", ["a/b.mp4", "asset://root_x/a.mp4", "", "take\\a.mp4"])
def test_absolute_path_detection_rejects_relative_forms(value):
    assert not is_absolute_path(value)


# --- shareable manifest must not leak local paths ---------------------------


@pytest.mark.parametrize(
    "fixture_name",
    [
        "manifest.complete.example.json",
        "manifest.partial-windows-missing.example.json",
        "manifest.historical-gap.example.json",
        "manifest.fixture-present.example.json",
    ],
)
def test_shareable_manifests_contain_no_local_paths(fixture_name: str):
    payload = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    assert find_local_paths(payload) == []


def test_local_path_lookup_finds_both_platform_forms():
    payload = {
        "note": "copied from /Volumes/Elements/项目/匹克球",
        "nested": [{"origin": "D:\\项目\\匹克球\\视频"}],
    }

    offenders = find_local_paths(payload)

    assert len(offenders) == 2
    assert any("/Volumes/Elements" in item for item in offenders)
    assert any("D:\\" in item for item in offenders)


def test_assert_no_local_paths_blocks_a_leak():
    with pytest.raises(LocationError):
        assert_no_local_paths({"assets": [{"locator": "/Volumes/Elements/a.mp4"}]})


# --- locations.local.json model --------------------------------------------


def _root(root_id: str = "root_captures") -> SourceRoot:
    return SourceRoot(
        root_id=root_id, path="/Volumes/Elements/captures", source_kind="external_disk"
    )


def test_local_location_file_accepts_a_consistent_mapping():
    model = LocalLocationFile(
        package_id=PACKAGE_ID,
        source_roots={"root_captures": _root()},
        assets={
            "a_aaaaaaaaaaaa": AssetLocation(
                locator="asset://root_captures/take/174.mp4",
                relative_path="take/174.mp4",
                source_root_id="root_captures",
            )
        },
    )

    assert model.schema_version == "pb.research-evidence-locations.v1.0"
    assert model.assets["a_aaaaaaaaaaaa"].relative_path == "take/174.mp4"


def test_local_location_file_requires_declared_roots():
    with pytest.raises(ValidationError):
        LocalLocationFile(
            package_id=PACKAGE_ID,
            source_roots={"root_captures": _root()},
            assets={
                "a_bbbbbbbbbbbb": AssetLocation(
                    locator="asset://root_models/best.pt",
                    relative_path="best.pt",
                    source_root_id="root_models",
                )
            },
        )


def test_source_root_key_must_equal_root_id():
    with pytest.raises(ValidationError):
        LocalLocationFile(
            package_id=PACKAGE_ID,
            source_roots={"root_other": _root()},
            assets={},
        )


def test_source_root_must_be_absolute():
    with pytest.raises(ValidationError):
        SourceRoot(root_id="root_x", path="relative/dir", source_kind="repository")


def test_asset_location_rejects_locator_and_root_mismatch():
    with pytest.raises(ValidationError):
        AssetLocation(
            locator="asset://root_captures/take/174.mp4",
            relative_path="take/174.mp4",
            source_root_id="root_models",
        )
