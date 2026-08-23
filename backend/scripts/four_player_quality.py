#!/usr/bin/env python3
"""Build or compare four-player identification quality artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.vision.player_tracking_engine.four_player_quality import (
    FourPlayerIdentificationQuality,
    build_quality_from_joint_artifacts,
    compare_quality,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--job-id", required=True)
    build.add_argument("--trajectory", type=Path, required=True)
    build.add_argument("--roster", type=Path, required=True)
    build.add_argument("--display-diagnostics", type=Path)
    build.add_argument("--algorithm-version", default="legacy-joint-tracking-v2")
    build.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        artifact = build_quality_from_joint_artifacts(
            job_id=args.job_id,
            trajectory=_load(args.trajectory),
            roster=_load(args.roster),
            display_diagnostics=_load(args.display_diagnostics) if args.display_diagnostics else None,
            algorithm_version=args.algorithm_version,
        )
        _write(args.output, artifact.model_dump(mode="json"))
        return 0
    result = compare_quality(
        FourPlayerIdentificationQuality.model_validate(_load(args.baseline)),
        FourPlayerIdentificationQuality.model_validate(_load(args.candidate)),
    )
    _write(args.output, result.model_dump(mode="json"))
    return 0 if result.verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
