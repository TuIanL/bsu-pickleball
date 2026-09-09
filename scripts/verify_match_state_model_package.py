#!/usr/bin/env python3
"""验证比赛状态模型包的契约、权重和配套 artifact 哈希。

该脚本不执行推理，也不要求 CUDA。它适合在模型下载完成后、本地归档或
远程部署前运行；模型包中的 checksums 对象是可选的，缺少时仍会报告文件
存在性，但在 strict 模式下会拒绝发布。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA = "match_state_model_package.v1"
REQUIRED_ARTIFACT_FIELDS = {
    "weights": "model.pt",
    "training_config": "training_profile.json",
    "evaluation_report": "evaluation_report.json",
}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "package_id",
    "model_name",
    "model_version",
    "task",
    "classes",
    "input_contract",
    "thresholds",
    "provenance",
    "artifacts",
    "runtime",
    "source_dataset_manifest_id",
    "source_rgb_manifest_id",
    "structured_feature_profile_schema",
}
REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "package_id",
    "model_name",
    "model_version",
    "task",
    "classes",
    "input_contract",
    "thresholds",
    "provenance",
    "artifacts",
    "runtime",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def _safe_relative_artifact(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"artifacts.{field} 必须是非空文件名")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise ValueError(f"artifacts.{field} 只能引用模型包目录下的文件: {value!r}")
    return value


def validate_package(package_dir: Path, schema_path: Path | None = None, strict: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    package_path = package_dir / "model_package.json"
    if not package_path.is_file():
        return {"status": "failed", "errors": [f"缺少 {package_path}"], "warnings": []}
    try:
        package = load_object(package_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "failed", "errors": [str(exc)], "warnings": []}

    if schema_path is not None and not schema_path.is_file():
        errors.append(f"Schema 不存在: {schema_path}")
    unknown_fields = sorted(set(package) - TOP_LEVEL_FIELDS)
    if unknown_fields:
        errors.append(f"模型包含未知顶层字段: {unknown_fields}")
    missing_fields = sorted(REQUIRED_TOP_LEVEL_FIELDS - set(package))
    if missing_fields:
        errors.append(f"模型缺少必需顶层字段: {missing_fields}")
    if package.get("schema_version") != PACKAGE_SCHEMA:
        errors.append(f"schema_version={package.get('schema_version')!r}，需要 {PACKAGE_SCHEMA!r}")
    if package.get("task") != "match_state_temporal_segmentation":
        errors.append("task 不是 match_state_temporal_segmentation")
    if package.get("classes") != ["rally_active", "non_play", "unknown"]:
        errors.append("classes 必须按顺序包含 rally_active、non_play、unknown")
    input_contract = package.get("input_contract")
    if (
        not isinstance(input_contract, dict)
        or not input_contract.get("modalities")
        or not input_contract.get("feature_schema")
    ):
        errors.append("input_contract 缺少 modalities 或 feature_schema")
    thresholds = package.get("thresholds")
    if not isinstance(thresholds, dict):
        errors.append("thresholds 必须是对象")
    else:
        for key in ("minimum_confidence", "minimum_coverage", "minimum_duration_ms", "hysteresis"):
            if key not in thresholds:
                errors.append(f"thresholds 缺少 {key}")

    artifacts = package.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts 必须是对象")
        artifacts = {}
    paths: dict[str, Path] = {}
    for field, expected_name in REQUIRED_ARTIFACT_FIELDS.items():
        try:
            actual_name = _safe_relative_artifact(artifacts.get(field), field)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if actual_name != expected_name:
            errors.append(f"artifacts.{field}={actual_name!r}，需要 {expected_name!r}")
        path = package_dir / actual_name
        paths[field] = path
        if not path.is_file():
            errors.append(f"缺少模型包文件: {path}")

    checksums = artifacts.get("checksums")
    if checksums is None:
        message = "artifacts.checksums 缺失，无法证明包内文件未被替换"
        (errors if strict else warnings).append(message)
        checksums = {}
    elif not isinstance(checksums, dict):
        errors.append("artifacts.checksums 必须是对象")
        checksums = {}

    artifact_report: dict[str, Any] = {}
    for _field, path in paths.items():
        if not path.is_file():
            continue
        digest = sha256_file(path)
        size = path.stat().st_size
        expected = checksums.get(path.name)
        item: dict[str, Any] = {"path": str(path), "size_bytes": size, "sha256": digest}
        if expected is None:
            (errors if strict else warnings).append(f"未记录 {path.name} 的 checksum")
        elif not isinstance(expected, dict):
            errors.append(f"checksums.{path.name} 必须是对象")
        else:
            item["expected_sha256"] = expected.get("sha256")
            item["expected_size_bytes"] = expected.get("size_bytes")
            if expected.get("sha256") != digest:
                errors.append(f"{path.name} SHA-256 不匹配: expected={expected.get('sha256')} actual={digest}")
            if expected.get("size_bytes") != size:
                errors.append(f"{path.name} 大小不匹配: expected={expected.get('size_bytes')} actual={size}")
        artifact_report[path.name] = item

    provenance = package.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance 必须是对象")
    else:
        for key in (
            "dataset_manifest_sha256",
            "rgb_clip_manifest_sha256",
            "group_split_sha256",
            "structured_feature_profile_sha256",
            "config_sha256",
        ):
            value = provenance.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                errors.append(f"provenance.{key} 不是合法 SHA-256")
        for key in (
            "structured_sequence_manifest_sha256",
            "structured_tensor_manifest_sha256",
            "rgb_checkpoint_sha256",
            "structured_checkpoint_sha256",
        ):
            value = provenance.get(key)
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                errors.append(f"provenance.{key} 不是合法 SHA-256")

    report = {
        "schema_version": "match_state_model_package_integrity.v1",
        "status": "passed" if not errors else "failed",
        "package_id": package.get("package_id"),
        "package_path": str(package_path),
        "package_file": {
            "size_bytes": package_path.stat().st_size,
            "sha256": sha256_file(package_path),
        },
        "model_version": package.get("model_version"),
        "strict": strict,
        "schema_path": str(schema_path) if schema_path else None,
        "artifacts": artifact_report,
        "errors": errors,
        "warnings": warnings,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="验证比赛状态模型包的文件、契约和 SHA-256")
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--strict", action="store_true", help="缺少 artifact checksum 时也失败")
    parser.add_argument("--report", type=Path, help="可选：写入 JSON 校验报告")
    args = parser.parse_args()
    try:
        report = validate_package(args.package_dir, args.schema, args.strict)
    except (OSError, ValueError) as exc:
        report = {"schema_version": "match_state_model_package_integrity.v1", "status": "failed", "errors": [str(exc)]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
