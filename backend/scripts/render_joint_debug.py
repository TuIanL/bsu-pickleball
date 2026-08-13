"""Render persisted joint debug evidence without rerunning analysis."""

from __future__ import annotations

import argparse

from app.services.joint_debug_renderer import JointDebugRenderInputs, render_joint_debug_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", action="append", required=True, metavar="VIEW_ID=PATH")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--trajectory", required=True)
    parser.add_argument("--diagnostics", required=True)
    parser.add_argument("--canonical-frame", required=True)
    parser.add_argument("--timing-mapping", required=True)
    parser.add_argument("--output-video", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()
    videos: dict[str, str] = {}
    for raw in args.video:
        view_id, separator, path = raw.partition("=")
        if not separator or not view_id or not path:
            parser.error(f"--video must use VIEW_ID=PATH: {raw}")
        videos[view_id] = path
    summary = render_joint_debug_artifacts(
        JointDebugRenderInputs(
            video_paths=videos,
            trace_path=args.trace,
            trajectory_path=args.trajectory,
            diagnostics_path=args.diagnostics,
            canonical_frame_path=args.canonical_frame,
            timing_mapping_path=args.timing_mapping,
            output_video_path=args.output_video,
            summary_path=args.summary,
            fps=args.fps,
        )
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
