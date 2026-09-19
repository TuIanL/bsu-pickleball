"""Validated, cacheable production model package loader."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable


class ModelPackageError(RuntimeError):
    """A stable error that can be surfaced as ``model_unavailable``."""

    def __init__(self, message: str, *, code: str = "model_unavailable") -> None:
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_package_file(package_dir: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ModelPackageError(f"artifacts.{field} 缺少有效文件名")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ModelPackageError(f"artifacts.{field} 不能引用模型包目录外的文件")
    path = package_dir / candidate
    if not path.is_file():
        raise ModelPackageError(f"模型包文件不存在: {candidate}")
    return path


@dataclass(frozen=True)
class ProductionModelPackage:
    directory: Path
    manifest: dict[str, Any]
    package_sha256: str
    weights_sha256: str
    decoder_sha256: str

    @property
    def package_id(self) -> str:
        return str(self.manifest["package_id"])

    @property
    def version(self) -> str:
        return str(self.manifest["model_version"])

    @property
    def thresholds(self) -> dict[str, Any]:
        value = self.manifest.get("thresholds")
        return dict(value) if isinstance(value, dict) else {}

    @property
    def input_contract(self) -> dict[str, Any]:
        value = self.manifest.get("input_contract")
        return dict(value) if isinstance(value, dict) else {}

    @property
    def runtime_spec(self) -> dict[str, Any]:
        value = self.manifest.get("runtime")
        return dict(value) if isinstance(value, dict) else {}


def load_production_package(package_dir: str | Path, *, required_profile: str = "match_default") -> ProductionModelPackage:
    """Load and verify a package without importing training/QA code."""
    root = Path(package_dir).expanduser().resolve()
    manifest_path = root / "model_package.json"
    if not manifest_path.is_file():
        raise ModelPackageError(f"缺少正式模型包: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ModelPackageError(f"正式模型包清单不可读: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "match_state_model_package.v1":
        raise ModelPackageError("正式模型包 schema_version 不受支持")
    required = {"package_id", "model_name", "model_version", "task", "classes", "input_contract", "thresholds", "artifacts"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ModelPackageError(f"正式模型包缺少字段: {missing}")
    if manifest.get("task") != "match_state_temporal_segmentation":
        raise ModelPackageError("正式模型包 task 不匹配")
    profiles = manifest.get("profiles")
    if profiles is not None and required_profile not in profiles:
        raise ModelPackageError(f"正式模型包不支持 profile={required_profile}")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict):
        raise ModelPackageError("正式模型包 artifacts 必须是对象")
    weights_path = _safe_package_file(root, artifacts.get("weights"), "weights")
    # A decoder hash is a first-class provenance field.  Older validated model
    # packages may omit decoder.json; hash the declared decoder config when it
    # exists, otherwise the immutable threshold payload.
    decoder_value = artifacts.get("decoder")
    if decoder_value is not None:
        decoder_path = _safe_package_file(root, decoder_value, "decoder")
        decoder_sha256 = sha256_file(decoder_path)
    else:
        decoder_sha256 = hashlib.sha256(
            json.dumps(manifest["thresholds"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    weights_sha256 = sha256_file(weights_path)
    package_sha256 = sha256_file(manifest_path)
    checksums = artifacts.get("checksums") or {}
    if isinstance(checksums, dict):
        for filename, checksum in checksums.items():
            if not isinstance(checksum, dict) or not checksum.get("sha256"):
                continue
            path = _safe_package_file(root, filename, f"checksums[{filename}]")
            actual = sha256_file(path)
            if actual != checksum["sha256"]:
                raise ModelPackageError(f"模型包文件 SHA-256 校验失败: {filename}")
    expected = None
    if isinstance(checksums, dict):
        relative_weights = weights_path.relative_to(root).as_posix()
        expected = checksums.get(relative_weights) or checksums.get(weights_path.name)
    if isinstance(expected, dict) and expected.get("sha256") and expected["sha256"] != weights_sha256:
        raise ModelPackageError("模型权重 SHA-256 校验失败")
    return ProductionModelPackage(root, manifest, package_sha256, weights_sha256, decoder_sha256)


class ModelPackageCache:
    """Process-local cache keyed by immutable package hash and device."""

    def __init__(self, loader: Callable[[ProductionModelPackage, str], object] | None = None) -> None:
        self._loader = loader or _load_runtime_adapter
        self._cache: dict[tuple[str, str], object] = {}
        self._lock = RLock()

    def get(self, package: ProductionModelPackage, device: str) -> object:
        key = (package.package_sha256, str(device))
        with self._lock:
            if key not in self._cache:
                self._cache[key] = self._loader(package, str(device))
            return self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


def _load_runtime_adapter(package: ProductionModelPackage, device: str) -> object:
    """Load an explicitly declared inference adapter without training imports.

    A package may declare ``runtime.entrypoint`` as ``module:function``. The
    factory receives ``(package, device)`` and may return a model object. A
    TorchScript package is supported directly as a dependency-lazy fallback.
    Packages without a runtime declaration remain usable for canonical
    probability sidecars, but raw frame samples are rejected by the runtime.
    """
    spec = package.runtime_spec
    entrypoint = spec.get("entrypoint")
    if isinstance(entrypoint, str) and ":" in entrypoint:
        module_name, function_name = entrypoint.split(":", 1)
        try:
            factory = getattr(importlib.import_module(module_name), function_name)
            return factory(package, device)
        except ModelPackageError:
            raise
        except Exception as exc:  # pragma: no cover - exercised on deployed worker
            raise ModelPackageError(f"模型运行时适配器加载失败: {exc}", code="model_unavailable") from exc
    if spec.get("kind") == "torchscript":
        try:
            import torch

            model = torch.jit.load(str(package.directory / str(package.manifest["artifacts"]["weights"])), map_location=device)
            return model.eval()
        except Exception as exc:  # pragma: no cover - depends on optional torch runtime
            raise ModelPackageError(f"TorchScript 模型加载失败: {exc}", code="model_unavailable") from exc
    return package
