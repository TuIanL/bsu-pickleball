#!/usr/bin/env python3
"""从录制时序元数据自动推导双摄同步校准（degraded）。

与 `calibrate_dual_camera_sync.py`（手动共享事件锚点，权威路径）不同：
本脚本从同步录制各 segment 的两路 `input_start_time` 推导两机位媒体时间轴的 offset，
产出 `dual_camera_sync_calibration.v1`，**quality 恒为 degraded**（自动推导未经人工锚点校验，
不冒充 authoritative good；按 P0 门控 `degraded → 允许融合但降权并输出诊断`）。

用法：
  python scripts/generate_dual_camera_sync.py --take ct_xxx
  python scripts/generate_dual_camera_sync.py --take ct_xxx --output /path/to/sync_calibration.json
  python scripts/generate_dual_camera_sync.py --session <sync-session-id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.dual_camera_sync import derive_sync_calibration_from_segment_timing


def _resolve_take_dir(take_id: str) -> Path:
    from app.database import get_session_factory
    from app.services.capture_take_service import get_capture_take

    db = get_session_factory()()
    try:
        take = get_capture_take(db, take_id)
        if take is None or not take.session_dir:
            raise SystemExit(f"take {take_id} not found or missing session_dir")
        return Path(take.session_dir)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--take", help="CaptureTake id（自动解析 session_dir/timeline/sync_calibration.json）")
    parser.add_argument("--session", help="双摄同步录制会话 id")
    parser.add_argument("--output", type=Path, help="输出路径（缺省为 take_dir/timeline/sync_calibration.json）")
    args = parser.parse_args()

    if not args.take and not args.session:
        parser.error("need --take or --session")

    from app.camera.sync_recorder_service import sync_recording_service

    session_id = args.session
    output = args.output
    if args.take:
        take_dir = _resolve_take_dir(args.take)
        if session_id is None:
            from app.database import get_session_factory
            from app.services.capture_take_service import get_capture_take

            db = get_session_factory()()
            try:
                take = get_capture_take(db, args.take)
                session_id = take.source_session_id
            finally:
                db.close()
        if output is None:
            output = take_dir / "timeline" / "sync_calibration.json"

    if not session_id:
        parser.error("could not resolve sync session id from take")
    session = sync_recording_service.get_session(session_id)
    if session is None:
        raise SystemExit(f"sync session {session_id} not found")

    payload = derive_sync_calibration_from_segment_timing(session.segments)
    output = output or Path("sync_calibration.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 degraded 双摄同步校准：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
