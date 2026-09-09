#!/usr/bin/env python3
"""把 canonical JSONL 一次性转换为可复用的紧凑结构化张量缓存。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from match_state_structured_model import VECTOR_SCHEMA_VERSION, read_sequences, sha256_file, vectorize_record


def main() -> int:
    parser = argparse.ArgumentParser(description="生成结构化比赛状态数值张量缓存")
    parser.add_argument("--sequence-manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest, sequences = read_sequences(args.sequence_manifest)
    source_root = args.dataset_root / manifest["source"]["canonical_feature_root"]
    expected = {}
    for item in sequences:
        source = item["source"]
        expected[str(source["feature_file"])] = {
            "sha256": source["feature_sha256"],
            "size_bytes": int(source["feature_size_bytes"]),
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name, identity in sorted(expected.items()):
        source_path = source_root / name
        if source_path.stat().st_size != identity["size_bytes"] or sha256_file(source_path) != identity["sha256"]:
            raise SystemExit(f"源 canonical feature 身份不一致: {source_path}")
        output_path = args.output_dir / f"{Path(name).stem}.npz"
        if output_path.exists() and not args.force:
            with np.load(output_path) as cached:
                record_count = int(cached["timestamps_ms"].shape[0])
            entries[name] = {**identity, "tensor_file": output_path.name, "record_count": record_count}
            print(json.dumps({"source": name, "status": "cache_hit", "records": record_count}), flush=True)
            continue
        players = []
        player_masks = []
        balls = []
        qualities = []
        timestamps = []
        with source_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                player, player_mask, ball, quality = vectorize_record(record)
                players.append(player)
                player_masks.append(player_mask)
                balls.append(ball)
                qualities.append(quality)
                timestamps.append(float(record["canonical_timestamp_ms"]))
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            np.savez(
                handle,
                players=np.asarray(players, dtype=np.float32),
                player_mask=np.asarray(player_masks, dtype=np.float32),
                ball=np.asarray(balls, dtype=np.float32),
                quality=np.asarray(qualities, dtype=np.float32),
                timestamps_ms=np.asarray(timestamps, dtype=np.float64),
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
        entries[name] = {**identity, "tensor_file": output_path.name, "record_count": len(timestamps)}
        print(json.dumps({"source": name, "status": "created", "records": len(timestamps)}), flush=True)
    cache_manifest = {
        "schema_version": "match_state_structured_tensor_cache.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "vector_schema": VECTOR_SCHEMA_VERSION,
        "sequence_manifest_id": manifest["manifest_id"],
        "sequence_manifest_sha256": sha256_file(args.sequence_manifest),
        "entries": entries,
    }
    cache_manifest["artifact_checksums"] = {
        entry["tensor_file"]: {"sha256": sha256_file(args.output_dir / entry["tensor_file"]), "size_bytes": (args.output_dir / entry["tensor_file"]).stat().st_size}
        for entry in entries.values()
    }
    output_manifest = args.output_dir / "manifest.json"
    output_manifest.write_text(json.dumps(cache_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "manifest": str(output_manifest), "sources": len(entries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
