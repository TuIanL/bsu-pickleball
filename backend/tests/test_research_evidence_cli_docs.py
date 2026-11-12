"""The CLI guide is executable: its commands parse and its flow actually runs.

Covers 3.3: run the documented flow in a temporary fixture directory, confirm a
cancelled build leaves sources untouched, and confirm a failed build leaves no
half-written package.
"""

from __future__ import annotations

import json
import shlex
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.cli import EXIT_ERROR, EXIT_INTERRUPTED, EXIT_OK, build_parser, main
from app.research_evidence.hashing import snapshot_file

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "research-evidence-cli.md"
MP4_HEADER = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"

BASELINE = {
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
    with tempfile.TemporaryDirectory(prefix="pe-clidocs-") as tmp:
        yield Path(tmp)


def _config(tmp_path: Path, root: Path, *, baseline: dict | None = BASELINE) -> Path:
    config = {
        "package_id": "pkg_0123456789ab",
        "source_roots": [
            {"root_id": "root_captures", "path": str(root), "source_kind": "external_disk"}
        ],
        "assets": [
            {
                "root_id": "root_captures",
                "relative_path": "clip.mp4",
                "kind": "source_video",
                "usage_kind": "real",
                "requirement": "required",
            }
        ],
        "baseline": baseline,
    }
    path = tmp_path / "roots.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "clip.mp4").write_bytes(MP4_HEADER + b"\x00" * 256)
    return root


# --- documentation ----------------------------------------------------------


def test_guide_exists_and_covers_the_commands():
    assert DOC.is_file(), "缺少 CLI 使用文档"
    text = DOC.read_text(encoding="utf-8")
    for command in ("build --config", "verify --package", "publish --package"):
        assert command in text, f"文档未覆盖命令: {command}"
    assert "撤回" in text, "文档必须说明撤回流程"


def test_every_documented_command_parses():
    text = DOC.read_text(encoding="utf-8")
    prefix = "python scripts/research_evidence.py "
    commands = [
        line.strip()[len(prefix) :]
        for line in text.splitlines()
        if line.strip().startswith(prefix)
    ]

    assert len(commands) >= 4, f"文档命令过少: {commands}"
    for raw in commands:
        # argparse 遇到未知参数会 SystemExit(2)，这里只要不抛就算合法。
        build_parser().parse_args(shlex.split(raw))


# --- the documented flow runs ----------------------------------------------


def test_documented_flow_runs_end_to_end(tmp_path):
    root = _source(tmp_path)
    config = _config(tmp_path, root)
    package = tmp_path / "out" / "pkg_0123456789ab"
    share = tmp_path / "share" / "pkg_0123456789ab"

    assert main(["build", "--config", str(config), "--output", str(package)]) == EXIT_OK
    assert main(["verify", "--package", str(package)]) == EXIT_OK
    assert main(["verify", "--package", str(package), "--deep"]) == EXIT_OK
    assert main(["publish", "--package", str(package), "--output", str(share)]) == EXIT_OK
    assert (
        main(["verify", "--package", str(share), "--shareable"]) == EXIT_OK
    )

    assert not (share / "locations.local.json").exists()
    assert (package / "locations.local.json").is_file()


def test_retry_into_a_new_directory_succeeds(tmp_path):
    """撤回后换新目录重建：旧目录不复用，源文件不受影响。"""
    root = _source(tmp_path)
    config = _config(tmp_path, root)
    first = tmp_path / "out" / "pkg_a"
    second = tmp_path / "out" / "pkg_b"

    assert main(["build", "--config", str(config), "--output", str(first)]) == EXIT_OK
    assert main(["build", "--config", str(config), "--output", str(second)]) == EXIT_OK

    assert (first / "manifest.json").is_file()
    assert (second / "manifest.json").is_file()


# --- interruption and failure ----------------------------------------------


def test_cancelled_build_leaves_sources_untouched(tmp_path, monkeypatch, capsys):
    root = _source(tmp_path)
    config = _config(tmp_path, root)
    package = tmp_path / "out"
    before = snapshot_file(root / "clip.mp4")

    def _interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("app.research_evidence.cli.build_manifest", _interrupt)
    code = main(["build", "--config", str(config), "--output", str(package)])

    assert code == EXIT_INTERRUPTED
    assert before.matches(snapshot_file(root / "clip.mp4"))
    assert "已中断" in capsys.readouterr().err
    assert not package.exists() or not any(package.iterdir())


def test_interrupted_manifest_build_returns_no_partial_package(tmp_path):
    """摘要被取消时构建整体失败，输出目录不会产生半成品。"""
    root = _source(tmp_path)
    config = _config(tmp_path, root)
    package = tmp_path / "out"

    from app.research_evidence.builder import BuildError, build_manifest, write_package
    from app.research_evidence.builder import load_build_config

    parsed = load_build_config(config)
    with pytest.raises(BuildError):
        manifest, locations, _checks = build_manifest(parsed, cancel=lambda: True)
        write_package(package, manifest, locations)

    assert not package.exists() or not any(package.iterdir())


def test_failed_build_reports_a_readable_reason(tmp_path, capsys):
    root = _source(tmp_path)
    config = _config(tmp_path, root, baseline={})
    package = tmp_path / "out"

    code = main(["build", "--config", str(config), "--output", str(package)])

    assert code == EXIT_ERROR
    assert "baseline" in capsys.readouterr().err
    assert not package.exists()
