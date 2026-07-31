from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
from typing import Any

from .contracts import validate_contract


class ProviderPreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightReport:
    platform_commit: str
    worktree_clean: bool
    configuration_sha256: str
    model_sha256: dict[str, str]
    model_paths: dict[str, Path]
    runtime_versions: dict[str, str]
    video_path: Path
    output_path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_preflight(
    request: dict[str, Any],
    *,
    request_dir: Path,
    output_path: Path,
    platform_root: Path | None = None,
) -> PreflightReport:
    validate_contract("provider_request", request)
    platform_root = platform_root or Path(__file__).resolve().parents[4]
    commit = _git(platform_root, "rev-parse", "HEAD")
    clean = not bool(_git(platform_root, "status", "--porcelain"))
    if request["run_mode"] in {"pilot", "formal"} and not clean:
        raise ProviderPreflightError(f"platform worktree is dirty at {platform_root}")

    video_path = _resolve_path(request["video"]["path"], request_dir)
    _require_file(video_path, "video")
    actual_video_sha = sha256_file(video_path)
    if actual_video_sha != request["video"]["sha256"]:
        raise ProviderPreflightError(
            f"video SHA-256 mismatch: expected {request['video']['sha256']}, got {actual_video_sha}"
        )

    configuration = request["configuration"]
    model_paths = {"person_detector": _resolve_path(configuration["detector_model_path"], request_dir)}
    if configuration.get("pose_scoring_enabled"):
        pose_config = configuration.get("pose_config_path")
        pose_checkpoint = configuration.get("pose_checkpoint_path")
        if not pose_config or not pose_checkpoint:
            raise ProviderPreflightError("pose scoring requires pose_config_path and pose_checkpoint_path")
        model_paths["pose_config"] = _resolve_path(pose_config, request_dir)
        model_paths["pose_checkpoint"] = _resolve_path(pose_checkpoint, request_dir)
    model_hashes: dict[str, str] = {}
    for name, path in sorted(model_paths.items()):
        _require_file(path, name)
        model_hashes[name] = sha256_file(path)

    if output_path.exists():
        raise ProviderPreflightError(f"output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return PreflightReport(
        platform_commit=commit,
        worktree_clean=clean,
        configuration_sha256=canonical_sha256(_portable_configuration(configuration)),
        model_sha256=model_hashes,
        model_paths=model_paths,
        runtime_versions=_runtime_versions(),
        video_path=video_path,
        output_path=output_path,
    )


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ProviderPreflightError(f"{label} file not found: {path}")


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise ProviderPreflightError(completed.stderr.strip() or "Git preflight failed")
    return completed.stdout.strip()


def _runtime_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package, key in (("opencv-python", "opencv"), ("ultralytics", "ultralytics")):
        try:
            versions[key] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[key] = "not-installed"
    return versions


def _portable_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    portable = dict(configuration)
    portable["detector_model_path"] = "external://person_detector"
    if portable.get("pose_config_path") is not None:
        portable["pose_config_path"] = "external://pose_config"
    if portable.get("pose_checkpoint_path") is not None:
        portable["pose_checkpoint_path"] = "external://pose_checkpoint"
    return portable
