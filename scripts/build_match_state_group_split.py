#!/usr/bin/env python3
"""按完整 CaptureTake 生成防泄漏主切分和 leave-one-take-out 评估折。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "match_state_group_split.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _take_stats(dataset: dict[str, Any], clips_path: Path) -> dict[str, dict[str, Any]]:
    stats = {
        take["capture_take_id"]: {
            "capture_take_id": take["capture_take_id"],
            "source_session_id": take["source_session_id"],
            "duration_ms": int(take["duration_ms"]),
            "rally_count": int(take["retained_rally_count"]),
            "logical_media_uris": sorted(item["logical_uri"] for item in take["media"]),
            "clip_count": 0,
            "center_label_counts": Counter(),
        }
        for take in dataset["takes"]
    }
    with clips_path.open(encoding="utf-8") as handle:
        for line in handle:
            clip = json.loads(line)
            item = stats[clip["capture_take_id"]]
            item["clip_count"] += 1
            item["center_label_counts"][clip["center_label"]] += 1
    for item in stats.values():
        item["center_label_counts"] = dict(item["center_label_counts"])
    return stats


def _aggregate(take_ids: list[str], stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    labels: Counter[str] = Counter()
    for take_id in take_ids:
        labels.update(stats[take_id]["center_label_counts"])
    return {
        "take_count": len(take_ids),
        "duration_ms": sum(stats[take_id]["duration_ms"] for take_id in take_ids),
        "rally_count": sum(stats[take_id]["rally_count"] for take_id in take_ids),
        "clip_count": sum(stats[take_id]["clip_count"] for take_id in take_ids),
        "center_label_counts": dict(labels),
    }


def _distribution_cost(
    take_ids: list[str],
    stats: dict[str, dict[str, Any]],
    global_stats: dict[str, Any],
    target_share: float,
) -> float:
    value = _aggregate(take_ids, stats)
    cost = 0.0
    for key, weight in (("clip_count", 2.0), ("duration_ms", 1.0), ("rally_count", 1.0)):
        actual_share = value[key] / global_stats[key]
        cost += weight * abs(actual_share - target_share) / max(target_share, 1e-9)
    for label, global_count in global_stats["center_label_counts"].items():
        global_ratio = global_count / global_stats["clip_count"]
        actual_ratio = value["center_label_counts"].get(label, 0) / max(value["clip_count"], 1)
        label_weight = 0.5 if label == "uncertain" else 1.0
        cost += label_weight * abs(actual_ratio - global_ratio)
    return cost


def _choose_primary_split(stats: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    take_ids = sorted(stats)
    global_stats = _aggregate(take_ids, stats)
    best: tuple[float, str, str] | None = None
    for validation_id, test_id in itertools.permutations(take_ids, 2):
        train_ids = [item for item in take_ids if item not in {validation_id, test_id}]
        score = (
            _distribution_cost(train_ids, stats, global_stats, 5 / 7)
            + _distribution_cost([validation_id], stats, global_stats, 1 / 7)
            + _distribution_cost([test_id], stats, global_stats, 1 / 7)
        )
        candidate = (round(score, 12), validation_id, test_id)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    validation_id, test_id = best[1], best[2]
    return {
        "train": [item for item in take_ids if item not in {validation_id, test_id}],
        "validation": [validation_id],
        "test": [test_id],
    }


def _cross_validation_folds(stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    take_ids = sorted(stats)
    global_stats = _aggregate(take_ids, stats)
    folds: list[dict[str, Any]] = []
    for fold_index, test_id in enumerate(take_ids, start=1):
        candidates = [item for item in take_ids if item != test_id]
        validation_id = min(
            candidates,
            key=lambda item: (
                _distribution_cost([item], stats, global_stats, 1 / 7),
                item,
            ),
        )
        folds.append(
            {
                "fold": fold_index,
                "train": [item for item in take_ids if item not in {test_id, validation_id}],
                "validation": [validation_id],
                "test": [test_id],
            }
        )
    return folds


def main() -> int:
    parser = argparse.ArgumentParser(description="生成比赛状态整场防泄漏切分")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--rgb-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    rgb_manifest = json.loads(args.rgb_manifest.read_text(encoding="utf-8"))
    clips_path = args.rgb_manifest.parent / rgb_manifest["clips_file"]
    stats = _take_stats(dataset, clips_path)
    primary = _choose_primary_split(stats)
    folds = _cross_validation_folds(stats)
    assignment = {
        take_id: split
        for split, take_ids in primary.items()
        for take_id in take_ids
    }
    all_take_ids = set(stats)
    if set(assignment) != all_take_ids or len(assignment) != len(all_take_ids):
        raise ValueError("主切分未覆盖每个 CaptureTake 恰好一次")
    media_owners: dict[str, set[str]] = defaultdict(set)
    for take_id, item in stats.items():
        for uri in item["logical_media_uris"]:
            media_owners[uri].add(assignment[take_id])
    leakage = {uri: sorted(owners) for uri, owners in media_owners.items() if len(owners) > 1}
    if leakage:
        raise ValueError(f"检测到媒体跨集合泄漏: {leakage}")

    immutable = {
        "schema_version": SCHEMA_VERSION,
        "dataset_manifest_id": dataset["manifest_id"],
        "rgb_manifest_id": rgb_manifest["manifest_id"],
        "dataset_manifest_sha256": _sha256_file(args.dataset_manifest),
        "rgb_manifest_sha256": _sha256_file(args.rgb_manifest),
        "clips_jsonl_sha256": _sha256_file(clips_path),
        "group_unit": "capture_take_id",
        "primary_split": primary,
        "assignment": assignment,
        "leave_one_take_out_folds": folds,
        "take_stats": [stats[take_id] for take_id in sorted(stats)],
        "split_stats": {
            split: _aggregate(take_ids, stats) for split, take_ids in primary.items()
        },
        "leakage_audit": {
            "capture_take_overlap_count": 0,
            "logical_media_uri_overlap_count": 0,
            "status": "passed",
        },
    }
    split_id = f"mss_{hashlib.sha256(_canonical_bytes(immutable)).hexdigest()[:20]}"
    output = {
        **immutable,
        "split_id": split_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "note": "Primary 5/1/1 split for model selection; leave-one-take-out folds for robustness reporting.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "split_id": split_id,
                "primary_split": primary,
                "split_stats": output["split_stats"],
                "leakage_audit": output["leakage_audit"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
