#!/usr/bin/env python3
"""比赛状态实验的本地校验与远程任务打包 CLI。

本 CLI 只处理 metadata 和配置，不读取视频、不解码视频，也不在本地启动训练。
真正的 RGB/结构化特征读取、训练、评估和批量推理必须在远程计算节点执行。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TRAINING_SCHEMA_VERSION = "match_state_training_profile.v1"
JOB_SCHEMA_VERSION = "match_state_training_job.v1"
DATASET_SCHEMA_VERSION = "match_state_dataset_manifest.v1"
RGB_MANIFEST_SCHEMA_VERSION = "match_state_rgb_clip_manifest.v1"
SPLIT_SCHEMA_VERSION = "match_state_group_split.v1"
SYNC_SCHEMA_VERSION = "match_state_dual_sync_report.v1"
LABEL_SCHEMA_VERSION = "match_state_label_profile.v1"
REMOTE_SCHEMA_VERSION = "match_state_remote_execution_profile.v1"
STRUCTURED_SCHEMA_VERSION = "match_state_structured_feature_profile.v1"
REQUIRED_CENTER_LABELS = {"rally_active", "non_play", "uncertain"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"文件不存在: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无法解析: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def require_schema(payload: dict[str, Any], expected: str, path: Path) -> None:
    actual = payload.get("schema_version")
    if actual != expected:
        raise ValueError(f"{path} schema_version={actual!r}，需要 {expected!r}")


def read_clip_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return records, [f"clips 文件不存在: {path}"]
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: {exc}")
                continue
            if not isinstance(value, dict):
                errors.append(f"{path}:{line_number}: clip 必须是对象")
                continue
            records.append(value)
    return records, errors


def _validate_split(
    dataset: dict[str, Any],
    split: dict[str, Any],
    dataset_path: Path,
    split_path: Path,
) -> list[str]:
    errors: list[str] = []
    take_ids = {str(item["capture_take_id"]) for item in dataset.get("takes", [])}
    assignment = split.get("assignment", {})
    if not isinstance(assignment, dict):
        return [f"{split_path}: assignment 必须是对象"]
    assigned_ids = set(assignment)
    if assigned_ids != take_ids:
        errors.append(
            f"{split_path}: assignment 覆盖不一致，missing={sorted(take_ids - assigned_ids)}, "
            f"extra={sorted(assigned_ids - take_ids)}"
        )
    if set(assignment.values()) != {"train", "validation", "test"}:
        errors.append(f"{split_path}: assignment 必须同时包含 train/validation/test")
    if split.get("dataset_manifest_sha256") != sha256_file(dataset_path):
        errors.append(f"{split_path}: dataset_manifest_sha256 不匹配")
    media_owners: dict[str, set[str]] = {}
    for take in dataset.get("takes", []):
        split_name = assignment.get(take.get("capture_take_id"))
        for media in take.get("media", []):
            uri = media.get("logical_uri")
            if uri and split_name:
                media_owners.setdefault(uri, set()).add(str(split_name))
    leakage = {uri: sorted(owners) for uri, owners in media_owners.items() if len(owners) > 1}
    if leakage:
        errors.append(f"{split_path}: logical_media_uri 跨 split 泄漏: {leakage}")
    if split.get("leakage_audit", {}).get("status") != "passed":
        errors.append(f"{split_path}: leakage_audit 未通过")
    return errors


def validate_bundle(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "dataset_manifest": args.dataset_manifest,
        "rgb_clip_manifest": args.rgb_manifest,
        "group_split": args.group_split,
        "dual_sync_report": args.dual_sync_report,
        "label_profile": args.label_profile,
        "remote_execution_profile": args.remote_profile,
        "structured_feature_profile": args.structured_profile,
        "training_profile": args.training_profile,
    }
    payloads = {name: load_json(path) for name, path in paths.items()}
    require_schema(payloads["dataset_manifest"], DATASET_SCHEMA_VERSION, paths["dataset_manifest"])
    require_schema(payloads["rgb_clip_manifest"], RGB_MANIFEST_SCHEMA_VERSION, paths["rgb_clip_manifest"])
    require_schema(payloads["group_split"], SPLIT_SCHEMA_VERSION, paths["group_split"])
    require_schema(payloads["dual_sync_report"], SYNC_SCHEMA_VERSION, paths["dual_sync_report"])
    require_schema(payloads["label_profile"], LABEL_SCHEMA_VERSION, paths["label_profile"])
    require_schema(payloads["remote_execution_profile"], REMOTE_SCHEMA_VERSION, paths["remote_execution_profile"])
    require_schema(payloads["structured_feature_profile"], STRUCTURED_SCHEMA_VERSION, paths["structured_feature_profile"])
    require_schema(payloads["training_profile"], TRAINING_SCHEMA_VERSION, paths["training_profile"])

    dataset = payloads["dataset_manifest"]
    rgb = payloads["rgb_clip_manifest"]
    split = payloads["group_split"]
    sync = payloads["dual_sync_report"]
    training = payloads["training_profile"]
    errors: list[str] = []

    clips_path = args.rgb_manifest.parent / str(rgb.get("clips_file", ""))
    clips, clip_errors = read_clip_records(clips_path)
    errors.extend(clip_errors)
    if rgb.get("clips_jsonl_sha256") != sha256_file(clips_path):
        errors.append(f"{args.rgb_manifest}: clips_jsonl_sha256 不匹配")
    if int(rgb.get("clip_count", -1)) != len(clips):
        errors.append(f"{args.rgb_manifest}: clip_count 与实际行数不一致")
    if rgb.get("dataset_manifest_id") != dataset.get("manifest_id"):
        errors.append("RGB manifest 与 dataset manifest 的 manifest_id 不一致")
    if sync.get("overall_status") != "passed":
        errors.append(f"{args.dual_sync_report}: overall_status 未通过")
    if int(sync.get("passed_count", -1)) != int(sync.get("session_count", -2)):
        errors.append(f"{args.dual_sync_report}: 并非所有场次同步检查通过")
    dataset_sessions = {str(take.get("source_session_id")) for take in dataset.get("takes", [])}
    sync_sessions = {str(item.get("source_session_id")) for item in sync.get("sessions", [])}
    if dataset_sessions != sync_sessions:
        errors.append(
            f"双摄同步报告覆盖场次不一致，missing={sorted(dataset_sessions - sync_sessions)}, "
            f"extra={sorted(sync_sessions - dataset_sessions)}"
        )

    errors.extend(_validate_split(dataset, split, args.dataset_manifest, args.group_split))
    if split.get("rgb_manifest_id") != rgb.get("manifest_id"):
        errors.append("group split 与 RGB manifest 的 manifest_id 不一致")
    if split.get("rgb_manifest_sha256") != sha256_file(args.rgb_manifest):
        errors.append("group split 与 RGB manifest 的 SHA-256 不一致")
    assignment = split.get("assignment", {})
    unknown_takes = sorted({clip.get("capture_take_id") for clip in clips} - set(assignment))
    if unknown_takes:
        errors.append(f"clips 中存在未切分的 CaptureTake: {unknown_takes}")
    invalid_labels = sorted({clip.get("center_label") for clip in clips} - REQUIRED_CENTER_LABELS)
    if invalid_labels:
        errors.append(f"clip center_label 非预期: {invalid_labels}")
    if training.get("data_contract", {}).get("group_unit") != split.get("group_unit"):
        errors.append("训练配置与 group split 的 group_unit 不一致")
    if training.get("temporal_input", {}).get("sampling_fps") != rgb.get("config", {}).get("target_rgb_fps_per_view"):
        errors.append("训练配置与 RGB manifest 的 sampling_fps 不一致")
    if training.get("temporal_input", {}).get("clip_duration_ms") != rgb.get("config", {}).get("clip_duration_ms"):
        errors.append("训练配置与 RGB manifest 的 clip_duration_ms 不一致")
    experiment_ids = [item.get("id") for item in training.get("experiment_matrix", [])]
    if len(experiment_ids) != len(set(experiment_ids)) or not {
        "rgb_only_v1",
        "structured_pose_ball_v1",
        "rgb_structured_fusion_v1",
    }.issubset(experiment_ids):
        errors.append("实验矩阵必须包含 RGB-only、结构化视觉和融合三组方案")
    required_remote_stages = set(payloads["remote_execution_profile"].get("remote_required_stages", []))
    if "model_training" not in required_remote_stages or "model_evaluation" not in required_remote_stages:
        errors.append("remote execution profile 未将训练和评估标记为 remote-required")

    center_counts: dict[str, int] = {}
    for clip in clips:
        label = str(clip.get("center_label"))
        center_counts[label] = center_counts.get(label, 0) + 1
    report = {
        "schema_version": "match_state_training_validation.v1",
        "status": "passed" if not errors else "failed",
        "validated_at": datetime.now(UTC).isoformat(),
        "artifacts": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
                "schema_version": payloads[name].get("schema_version"),
            }
            for name, path in paths.items()
        },
        "dataset": {
            "manifest_id": dataset.get("manifest_id"),
            "take_count": len(dataset.get("takes", [])),
            "rally_count": dataset.get("rally_count"),
            "clip_count": len(clips),
            "center_label_counts": center_counts,
            "group_split_id": split.get("split_id"),
        },
        "sync_gate": {
            "overall_status": sync.get("overall_status"),
            "session_count": sync.get("session_count"),
            "passed_count": sync.get("passed_count"),
        },
        "execution_policy": {
            "video_decode_performed": False,
            "local_training_performed": False,
            "remote_required": True,
        },
        "errors": errors,
    }
    return report


def _git_provenance(project_root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=project_root, check=True, capture_output=True, text=True
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        revision = "uncommitted-or-git-unavailable"
        dirty = True
    return {"revision": revision, "working_tree_dirty": dirty}


def package_job(args: argparse.Namespace) -> dict[str, Any]:
    report = validate_bundle(args)
    if report["status"] != "passed":
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    output_root = args.output
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_root = output_root / "manifests"
    manifest_root.mkdir(exist_ok=True)
    copied: dict[str, str] = {}
    for name, path in {
        "dataset_manifest": args.dataset_manifest,
        "rgb_clip_manifest": args.rgb_manifest,
        "group_split": args.group_split,
        "dual_sync_report": args.dual_sync_report,
        "label_profile": args.label_profile,
        "remote_execution_profile": args.remote_profile,
        "structured_feature_profile": args.structured_profile,
        "training_profile": args.training_profile,
    }.items():
        target = manifest_root / path.name
        shutil.copy2(path, target)
        copied[name] = str(target.relative_to(output_root))
    clips_path = args.rgb_manifest.parent / json.loads(args.rgb_manifest.read_text(encoding="utf-8"))["clips_file"]
    clips_target = manifest_root / clips_path.name
    shutil.copy2(clips_path, clips_target)
    copied["rgb_clips_jsonl"] = str(clips_target.relative_to(output_root))
    schema_source = args.model_package_schema
    schema_target = output_root / schema_source.name
    shutil.copy2(schema_source, schema_target)
    copied["model_package_schema"] = str(schema_target.relative_to(output_root))

    training_profile = load_json(args.training_profile)
    job_identity = {
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "rgb_clip_manifest_sha256": sha256_file(args.rgb_manifest),
        "group_split_sha256": sha256_file(args.group_split),
        "dual_sync_report_sha256": sha256_file(args.dual_sync_report),
        "structured_feature_profile_sha256": sha256_file(args.structured_profile),
        "training_profile_sha256": sha256_file(args.training_profile),
        "experiment_matrix": [item["id"] for item in training_profile["experiment_matrix"]],
    }
    job_id = f"msj_{hashlib.sha256(canonical_bytes(job_identity)).hexdigest()[:20]}"
    job = {
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "created_at": datetime.now(UTC).isoformat(),
        "job_identity": job_identity,
        "dataset_manifest_id": report["dataset"]["manifest_id"],
        "group_split_id": report["dataset"]["group_split_id"],
        "artifacts": copied,
        "media_contract": {
            "dataset_root_env": "MATCH_STATE_DATASET_ROOT",
            "media_paths_are_remote_relative_only": True,
            "video_clips_materialized_locally": False,
        },
        "code_provenance": _git_provenance(args.project_root),
        "execution": {
            "local_operations_completed": ["metadata_validation", "job_packaging"],
            "remote_operations_required": ["video_decode", "feature_loading", "training", "evaluation"],
            "training_started": False,
        },
        "validation_report": "training-validation.json",
    }
    (output_root / "training-validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_root / "training-job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="比赛状态实验的本地校验与远程任务打包 CLI")
    parser.add_argument("command", choices=["validate", "package"])
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--group-split", type=Path, required=True)
    parser.add_argument("--dual-sync-report", type=Path, required=True)
    parser.add_argument("--label-profile", type=Path, required=True)
    parser.add_argument("--remote-profile", type=Path, required=True)
    parser.add_argument("--structured-profile", type=Path, required=True)
    parser.add_argument("--training-profile", type=Path, required=True)
    parser.add_argument(
        "--model-package-schema",
        type=Path,
        required=False,
        default=Path("backend/app/resources/match_state_model_package.schema.v1.json"),
    )
    parser.add_argument("--output", type=Path, required=False, help="validate 输出报告或 package 目录")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            report = validate_bundle(args)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["status"] == "passed" else 1
        job = package_job(args)
        print(json.dumps({"status": "passed", "job_id": job["job_id"], "output": str(args.output)}, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
