"""Controlled build/verify CLI.

Covers the 3.1 requirements: explicit source roots and a new output root, refusal
to overwrite inputs or existing packages, and a guarantee that building never
initialises the database, the model runtime or the app lifespan.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.builder import (
    BuildError,
    assert_output_is_safe,
    load_build_config,
    verify_package,
)
from app.research_evidence.cli import EXIT_ERROR, EXIT_OK, EXIT_VERIFY_FAILED, main

BACKEND = Path(__file__).resolve().parents[1]
MP4_HEADER = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"

VALID_BASELINE = {
    "selected_revision": {
        "label": "selected_baseline",
        "status": "known",
        "commit": "bd136d661bf391104b9193752f7c868878e63a48",
        "worktree_clean": True,
        "dirty_patch": {
            "status": "known",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        "note": None,
    },
    "reference_revisions": [],
}


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-cli-") as tmp:
        yield Path(tmp)


def _source_root(tmp_path: Path, name: str = "source") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "clip.mp4").write_bytes(MP4_HEADER + b"\x00" * 256)
    return root


def _write_config(
    tmp_path: Path,
    root: Path,
    *,
    assets: list[dict] | None = None,
    baseline: dict | None = None,
    package_id: str = "pkg_0123456789ab",
) -> Path:
    config = {
        "package_id": package_id,
        "source_roots": [
            {
                "root_id": "root_captures",
                "path": str(root),
                "source_kind": "external_disk",
            }
        ],
        "assets": assets
        if assets is not None
        else [
            {
                "root_id": "root_captures",
                "relative_path": "clip.mp4",
                "kind": "source_video",
                "usage_kind": "real",
                "requirement": "required",
            }
        ],
        "baseline": baseline if baseline is not None else VALID_BASELINE,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


# --- build ------------------------------------------------------------------


def test_build_creates_the_package(tmp_path, capsys):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"

    code = main(["build", "--config", str(config), "--output", str(output)])

    assert code == EXIT_OK
    assert (output / "manifest.json").is_file()
    assert (output / "checks.json").is_file()
    assert (output / "locations.local.json").is_file()
    printed = capsys.readouterr().out
    assert "completeness: complete" in printed


def test_built_manifest_passes_verify(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    report = verify_package(output)
    assert report.ok, [check for check in report.failures]


def test_manifest_never_leaks_absolute_paths(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"
    main(["build", "--config", str(config), "--output", str(output)])

    raw = (output / "manifest.json").read_text(encoding="utf-8")
    assert str(root) not in raw
    assert "asset://root_captures/clip.mp4" in raw


def test_locations_file_holds_the_local_path(tmp_path):
    """The absolute path belongs to locations.local.json, not the manifest."""
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"
    main(["build", "--config", str(config), "--output", str(output)])

    locations = json.loads((output / "locations.local.json").read_text(encoding="utf-8"))

    assert locations["source_roots"]["root_captures"]["path"] == str(root)
    asset_id = next(iter(locations["assets"]))
    assert locations["assets"][asset_id]["source_root_id"] == "root_captures"
    assert locations["assets"][asset_id]["relative_path"] == "clip.mp4"


# --- refusals ---------------------------------------------------------------


def test_output_inside_a_source_root_is_refused(tmp_path):
    root = _source_root(tmp_path)

    with pytest.raises(BuildError, match="授权来源根"):
        assert_output_is_safe(root / "out", {"root_captures": str(root)})


def test_output_containing_a_source_root_is_refused(tmp_path):
    root = _source_root(tmp_path)

    with pytest.raises(BuildError, match="包含授权来源根"):
        assert_output_is_safe(tmp_path, {"root_captures": str(root)})


def test_non_empty_output_directory_is_refused(tmp_path):
    root = _source_root(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / "leftover.txt").write_text("x", encoding="utf-8")

    with pytest.raises(BuildError, match="非空"):
        assert_output_is_safe(output, {"root_captures": str(root)})


def test_existing_manifest_is_not_overwritten(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK
    # 第二次构建指向同一目录：必须失败，且不覆盖已有产物。
    code = main(["build", "--config", str(config), "--output", str(output)])

    assert code == EXIT_ERROR


def test_config_without_baseline_is_rejected(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root, baseline={})

    with pytest.raises(BuildError, match="baseline"):
        load_build_config(config)


def test_unreadable_asset_requires_an_explicit_asset_id(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    config = _write_config(
        tmp_path,
        root,
        assets=[
            {
                "root_id": "root_captures",
                "relative_path": "absent.mp4",
                "kind": "job_artifact",
                "usage_kind": "unknown",
                "requirement": "optional",
            }
        ],
    )
    output = tmp_path / "out"

    code = main(["build", "--config", str(config), "--output", str(output)])

    assert code == EXIT_ERROR


def test_unreadable_asset_with_explicit_id_is_recorded_as_missing(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    config = _write_config(
        tmp_path,
        root,
        assets=[
            {
                "root_id": "root_captures",
                "relative_path": "windows-job",
                "kind": "job_artifact",
                "usage_kind": "unknown",
                "requirement": "required",
                "asset_id": "a_windows_job",
            }
        ],
    )
    output = tmp_path / "out"

    assert main(["build", "--config", str(config), "--output", str(output)]) == EXIT_OK

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"][0]["availability"] == "missing"
    assert manifest["assets"][0]["digest"]["status"] == "unknown"
    assert manifest["completeness"] == "partial"


# --- verify -----------------------------------------------------------------


def test_verify_fails_when_locations_are_missing(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"
    main(["build", "--config", str(config), "--output", str(output)])
    (output / "locations.local.json").unlink()

    report = verify_package(output)

    assert report.ok is False
    assert any(check.name == "locations_present" for check in report.failures)


def test_verify_cli_exit_codes(tmp_path):
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"
    main(["build", "--config", str(config), "--output", str(output)])

    assert main(["verify", "--package", str(output)]) == EXIT_OK

    (output / "locations.local.json").unlink()
    assert main(["verify", "--package", str(output)]) == EXIT_VERIFY_FAILED
    assert main(["verify", "--package", str(tmp_path / "nope")]) == EXIT_ERROR


# --- isolation from the application runtime ---------------------------------


def test_build_does_not_import_database_models_or_lifespan(tmp_path):
    """The CLI must stay usable without FastAPI, SQLAlchemy or torch loaded."""
    root = _source_root(tmp_path)
    config = _write_config(tmp_path, root)
    output = tmp_path / "out"

    script = (
        "import json, sys\n"
        "from app.research_evidence.cli import main\n"
        f"code = main(['build', '--config', {str(config)!r}, '--output', {str(output)!r}])\n"
        "watched = ('app.main', 'app.database', 'app.api', 'app.vision',\n"
        "           'sqlalchemy', 'fastapi', 'uvicorn', 'torch', 'cv2')\n"
        "print('RC', code)\n"
        "print('HEAVY', json.dumps([m for m in watched if m in sys.modules]))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "RC 0" in completed.stdout, completed.stdout + completed.stderr
    assert 'HEAVY []' in completed.stdout, completed.stdout
