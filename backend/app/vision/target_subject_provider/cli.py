from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .preflight import ProviderPreflightError
from .provider import run_video_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export reviewable target-player candidates without product state.")
    parser.add_argument("--request", required=True, type=Path, help="Provider request JSON path.")
    parser.add_argument("--output", required=True, type=Path, help="New provider result JSON path.")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = run_video_provider(
            request,
            request_dir=args.request.resolve().parent,
            output_path=args.output.resolve(),
        )
    except (OSError, ValueError, ProviderPreflightError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "sample_id": result["sample_id"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
