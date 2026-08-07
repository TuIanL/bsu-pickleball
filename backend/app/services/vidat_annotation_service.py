"""生成可复现 Vidat 标注包的纯服务层。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.capture_take import CaptureTake, CaptureTakeStatus
from app.models.capture_track import CaptureTrack, TrackRole
from app.models.media_fragment import MediaFragment
from app.models.track_finalization import FinalizationStatus, TrackFinalization
from app.models.vidat_annotation import VidatAnnotationPackage, VidatImportAudit, VidatImportPreview
from app.services.video_service import video_service

VIDAT_SCHEMA_VERSION = "pickleball-vidat-v1"
EVENT_LABELS = {
    "set_start": (1, "盘开始", "#E74C3C"),
    "set_end": (2, "盘结束", "#C0392B"),
    "game_start": (3, "局开始", "#3498DB"),
    "game_end": (4, "局结束", "#2980B9"),
    "rally_start": (5, "回合", "#2ECC71"),
    "rally_end": (6, "回合结果", "#27AE60"),
    "score_correction": (7, "比分修正", "#F39C12"),
    "timeout_start": (8, "暂停", "#95A5A6"),
    "non_play_start": (9, "非比赛", "#BDC3C7"),
    "side_change": (10, "换边", "#9B59B6"),
    "session_note": (11, "备注", "#7F8C8D"),
    "custom_marker": (12, "自定义标记", "#888888"),
}


class VidatPackageError(ValueError):
    pass


def _metadata(action: dict, index: int) -> dict:
    try:
        value = json.loads(action.get("description") or "{}")
    except json.JSONDecodeError as exc:
        raise VidatPackageError(f"第 {index + 1} 个 action 的 metadata 不是 JSON") from exc
    if not isinstance(value, dict) or not value.get("event_type"):
        raise VidatPackageError(f"第 {index + 1} 个 action 缺少 event_type metadata")
    return value


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_hierarchy(operations: list[dict]) -> None:
    level = {"set_start": 0, "game_start": 1, "rally_start": 2}
    ranges = [item for item in operations if item["event_type"] in level]
    for event_type in level:
        same = sorted(
            (item for item in ranges if item["event_type"] == event_type), key=lambda x: (x["start_ms"], x["end_ms"])
        )
        for previous, current in zip(same, same[1:], strict=False):
            if current["start_ms"] < previous["end_ms"]:
                raise VidatPackageError(f"{event_type} 范围存在同层重叠")
    for child_type, parent_type in (("game_start", "set_start"), ("rally_start", "game_start")):
        parents = [item for item in ranges if item["event_type"] == parent_type]
        for child in (item for item in ranges if item["event_type"] == child_type):
            if parents and not any(
                parent["start_ms"] <= child["start_ms"] and child["end_ms"] <= parent["end_ms"] for parent in parents
            ):
                raise VidatPackageError(f"{child_type} 未完整包含在 {parent_type} 范围内")


def _coding_actions(operations: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for operation in operations:
        event_type, payload = operation["event_type"], operation["payload"]
        common = {"operation_index": operation["index"], "event_ids": operation["event_ids"]}
        if event_type == "set_start":
            actions.extend(
                [
                    {"action": "start_set", "timestamp_ms": operation["start_ms"], "payload": common},
                    {"action": "end_set", "timestamp_ms": operation["end_ms"], "payload": common},
                ]
            )
        elif event_type == "game_start":
            actions.extend(
                [
                    {
                        "action": "start_game",
                        "timestamp_ms": operation["start_ms"],
                        "payload": {**common, "initial_server_team": payload.get("initial_server_team", "A")},
                    },
                    {"action": "end_game", "timestamp_ms": operation["end_ms"], "payload": common},
                ]
            )
        elif event_type == "rally_start":
            validity, winner = payload.get("validity", "valid"), payload.get("winner")
            result = "rally_replay" if validity == "replay" else f"rally_result_{str(winner or 'A').lower()}"
            actions.extend(
                [
                    {"action": "start_next_rally", "timestamp_ms": operation["start_ms"], "payload": common},
                    {"action": result, "timestamp_ms": operation["end_ms"], "payload": common},
                ]
            )
        elif event_type == "score_correction":
            score = payload.get("score_after", payload)
            actions.append(
                {
                    "action": "correct_score",
                    "timestamp_ms": operation["start_ms"],
                    "payload": {
                        **common,
                        "score_a": score.get("a", score.get("score_a")),
                        "score_b": score.get("b", score.get("score_b")),
                        "server_team": score.get("server_team"),
                        "reason": payload.get("reason", "Vidat 导入"),
                    },
                }
            )
        elif event_type in {"session_note", "custom_marker", "side_change"}:
            action = "change_side" if event_type == "side_change" else "add_note"
            actions.append(
                {
                    "action": action,
                    "timestamp_ms": operation["start_ms"],
                    "payload": {
                        **common,
                        "event_type": event_type,
                        "label": operation["label"],
                        "note": operation["note"],
                        "payload": payload,
                    },
                }
            )
    priority = {
        "start_set": 0,
        "start_game": 1,
        "start_next_rally": 2,
        "correct_score": 3,
        "rally_result_a": 4,
        "rally_result_b": 4,
        "rally_replay": 4,
        "end_game": 5,
        "end_set": 6,
    }
    return sorted(
        actions,
        key=lambda item: (item["timestamp_ms"], priority.get(item["action"], 3), item["payload"]["operation_index"]),
    )


def _score_summary(coding_actions: list[dict], ruleset: str | None = None) -> dict:
    from app.services.scoring_fsm import (
        HYBRID_21_RULESET,
        ScoringAction,
        ScoringState,
        initial_game_state,
        reduce_scoring_state_for_ruleset,
    )

    ruleset = ruleset or HYBRID_21_RULESET
    state = ScoringState(server_team=None, score_a=0, score_b=0)
    affected = []
    for item in coding_actions:
        action, payload = item["action"], item["payload"]
        try:
            if action == "start_game":
                state = initial_game_state(state, payload.get("initial_server_team", "A"))
            elif action in {"rally_result_a", "rally_result_b"}:
                state = reduce_scoring_state_for_ruleset(
                    state, ScoringAction(type="rally_result", winner=action[-1].upper(), validity="valid"), ruleset
                )
                affected.append(
                    {
                        "timestamp_ms": item["timestamp_ms"],
                        "score_a": state.score_a,
                        "score_b": state.score_b,
                        "games_won_a": state.games_won_a,
                        "games_won_b": state.games_won_b,
                    }
                )
            elif action == "rally_replay":
                state = reduce_scoring_state_for_ruleset(
                    state, ScoringAction(type="rally_result", validity="replay"), ruleset
                )
            elif action == "correct_score":
                state = reduce_scoring_state_for_ruleset(
                    state,
                    ScoringAction(
                        type="correct_score",
                        target_server_team=payload["server_team"],
                        target_score_a=payload["score_a"],
                        target_score_b=payload["score_b"],
                    ),
                    ruleset,
                )
        except (TypeError, ValueError) as exc:
            raise VidatPackageError(f"候选计分动作无法重放: {exc}") from exc
    return {
        "affected_scores": affected,
        "final": {
            "score_a": state.score_a,
            "score_b": state.score_b,
            "games_won_a": state.games_won_a,
            "games_won_b": state.games_won_b,
            "match_status": state.match_status,
            "match_winner": state.match_winner,
        },
    }


def parse_vidat_annotation(
    package: VidatAnnotationPackage, annotation: dict, *, validate_hierarchy: bool = True
) -> list[dict]:
    """校验 Vidat action，并转换成稳定排序的语义操作。"""
    manifest = json.loads(package.manifest_json)
    identity = annotation.get("pickleball_manifest") or {}
    for key, expected in (("package_id", package.id), ("capture_take_id", package.capture_take_id)):
        if identity.get(key) not in (None, expected):
            raise VidatPackageError(f"标注文件 {key} 与标注包不一致")
    video = annotation.get("annotation", {}).get("video", {})
    expected_fps = float(manifest["video"]["fps"])
    if abs(float(video.get("fps", 0)) - expected_fps) > 0.01:
        raise VidatPackageError("标注文件 FPS 与标注包不一致")
    allowed_ids = {value[0] for value in EVENT_LABELS.values()}
    actions = annotation.get("annotation", {}).get("actionAnnotationList")
    if not isinstance(actions, list):
        raise VidatPackageError("标注文件缺少 actionAnnotationList")
    operations = []
    for index, action in enumerate(actions):
        action_id = action.get("action")
        start, end = action.get("start"), action.get("end")
        if action_id == 0:
            # Vidat requires a default action as the first annotation. It is
            # a visual baseline, not a project timeline event.
            continue
        if (
            action_id not in allowed_ids
            or isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or start < 0
            or end <= start
        ):
            raise VidatPackageError(f"第 {index + 1} 个 action 的标签或时间范围无效")
        max_seconds = float(video.get("duration") or manifest["video"]["duration"])
        if end > max_seconds + 0.001:
            raise VidatPackageError(f"第 {index + 1} 个 action 超出视频时间边界")
        meta = _metadata(action, index)
        if meta["event_type"] not in EVENT_LABELS:
            raise VidatPackageError(f"第 {index + 1} 个 action 的事件类型不受支持")
        if EVENT_LABELS[meta["event_type"]][0] != action_id:
            raise VidatPackageError(f"第 {index + 1} 个 action 的标签 ID 与 event_type 不匹配")
        payload = meta.get("payload") or {}
        if not isinstance(payload, dict):
            raise VidatPackageError(f"第 {index + 1} 个 action payload 无效")
        if meta["event_type"] == "rally_start" and payload.get("winner") not in (None, "A", "B"):
            raise VidatPackageError(f"第 {index + 1} 个回合胜者必须为 A、B 或空")
        operations.append(
            {
                "index": index,
                "event_ids": meta.get("event_ids") or [],
                "event_type": meta["event_type"],
                "start_ms": round(float(start) * 1000),
                "end_ms": round(float(end) * 1000),
                "payload": payload,
                "label": meta.get("label", ""),
                "note": meta.get("note", ""),
            }
        )
    operations = sorted(operations, key=lambda item: (item["start_ms"], item["end_ms"], item["index"]))
    if validate_hierarchy:
        _validate_hierarchy(operations)
    return operations


def create_import_preview(db: Session, package: VidatAnnotationPackage, annotation: dict) -> VidatImportPreview:
    operations = parse_vidat_annotation(package, annotation)
    # 旧包可能正是因为历史层级错误才需要 Vidat 修复；它只用于差异基线。
    old_operations = parse_vidat_annotation(package, json.loads(package.annotation_json), validate_hierarchy=False)
    old_by_id = {tuple(item["event_ids"]): item for item in old_operations if item["event_ids"]}
    changes = []
    for operation in operations:
        old = old_by_id.pop(tuple(operation["event_ids"]), None)
        if old is None:
            changes.append({"kind": "added", "after": operation})
        elif {key: operation[key] for key in ("event_type", "start_ms", "end_ms", "payload")} != {
            key: old[key] for key in ("event_type", "start_ms", "end_ms", "payload")
        }:
            winner_changed = old["payload"].get("winner") != operation["payload"].get("winner")
            score_changed = old["event_type"] == "score_correction" and old["payload"] != operation["payload"]
            if old["event_type"] != operation["event_type"]:
                kind = "category_changed"
            elif winner_changed:
                kind = "winner_changed"
            elif score_changed:
                kind = "score_anchor_changed"
            elif (old["start_ms"], old["end_ms"]) != (operation["start_ms"], operation["end_ms"]):
                kind = "moved"
            else:
                kind = "changed"
            changes.append({"kind": kind, "before": old, "after": operation, "winner_changed": winner_changed})
    changes.extend({"kind": "removed", "before": operation} for operation in old_by_id.values())
    canonical = _canonical_json(annotation)
    coding_actions = _coding_actions(operations)
    from app.models.live_coding_state import LiveCodingState

    live_state = db.get(LiveCodingState, package.capture_take_id)
    ruleset = getattr(live_state, "scoring_ruleset_version", None)
    summary = _score_summary(coding_actions, ruleset)
    conflicts = []
    if coding_actions:
        from app.models.capture_coding_action import CaptureCodingAction

        start_ms = min(item["timestamp_ms"] for item in coding_actions)
        end_ms = max(item["timestamp_ms"] for item in coding_actions)
        manual = (
            db.query(CaptureCodingAction)
            .filter(
                CaptureCodingAction.capture_take_id == package.capture_take_id,
                CaptureCodingAction.timestamp_ms.between(start_ms, end_ms),
                CaptureCodingAction.annotation_package_id.is_(None),
            )
            .all()
        )
        conflicts = [
            {
                "coding_action_id": item.id,
                "action": item.action_type,
                "timestamp_ms": item.timestamp_ms,
                "resolution": "preserved",
            }
            for item in manual
        ]
    preview = VidatImportPreview(
        id=f"vip_{uuid4().hex[:12]}",
        package_id=package.id,
        content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        token=token_urlsafe(24),
        annotation_json=canonical,
        preview_json=json.dumps(
            {
                "operations": operations,
                "coding_actions": coding_actions,
                "changes": changes,
                "blocking_errors": [],
                "conflicts": conflicts,
                "score_summary": summary,
            },
            ensure_ascii=False,
        ),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(preview)
    db.flush()
    return preview


def confirm_import_preview(
    db: Session, package: VidatAnnotationPackage, token: str, annotation: dict | None = None
) -> VidatImportAudit:
    preview = (
        db.query(VidatImportPreview)
        .filter(
            VidatImportPreview.package_id == package.id,
            VidatImportPreview.token == token,
        )
        .first()
    )
    now = datetime.now(UTC)
    if preview is None or preview.consumed or preview.expires_at.replace(tzinfo=UTC) <= now:
        raise VidatPackageError("确认令牌无效、已使用或已过期")
    submitted = _canonical_json(annotation) if annotation is not None else preview.annotation_json
    if hashlib.sha256(submitted.encode()).hexdigest() != preview.content_hash:
        raise VidatPackageError("确认内容与预览不一致，请重新生成预览")
    snapshot = json.loads(preview.preview_json)
    audit = VidatImportAudit(
        id=f"via_{uuid4().hex[:12]}",
        package_id=package.id,
        preview_id=preview.id,
        content_hash=preview.content_hash,
        operations_json=json.dumps(snapshot["operations"], ensure_ascii=False),
    )
    db.add(audit)
    db.flush()
    _apply_import_plan(db, package, audit, snapshot)
    preview.consumed = True
    package.annotation_json = preview.annotation_json
    package.normalized_snapshot_json = json.dumps(snapshot, ensure_ascii=False)
    package.imported_at = now
    db.flush()
    return audit


def _apply_import_plan(db: Session, package: VidatAnnotationPackage, audit: VidatImportAudit, plan: dict) -> None:
    """将已验证计划作为单一事务的可追溯投影写入。"""
    from app.models.capture_coding_action import CaptureCodingAction, CodingActionStatus
    from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
    from app.models.capture_take import CaptureTake
    from app.models.live_coding_state import LiveCodingState
    from app.models.timeline_event import SessionTimelineEvent, TimelineEventSource, TimelineEventType
    from app.services.capture_coding_action_service import compute_request_hash

    take = db.get(CaptureTake, package.capture_take_id)
    if take is None:
        raise VidatPackageError("CaptureTake 不存在")
    # 只替换该包上一次导入的投影，其他人工/算法数据保留。
    db.query(CaptureCodingAction).filter(CaptureCodingAction.annotation_package_id == package.id).delete(
        synchronize_session=False
    )
    db.query(SessionTimelineEvent).filter(SessionTimelineEvent.annotation_package_id == package.id).delete(
        synchronize_session=False
    )
    db.query(CaptureSegment).filter(CaptureSegment.annotation_package_id == package.id).delete(
        synchronize_session=False
    )

    base_revision = take.revision
    for offset, item in enumerate(plan["coding_actions"]):
        payload = item["payload"]
        record = CaptureCodingAction(
            id=f"ca_vidat_{audit.id[-8:]}_{offset:04d}",
            capture_take_id=take.id,
            client_action_id=f"vidat:{package.id}:{audit.id}:{offset}",
            action_type=item["action"],
            timestamp_ms=item["timestamp_ms"],
            payload_json=json.dumps(payload, ensure_ascii=False),
            request_hash=compute_request_hash(item["action"], payload),
            status=CodingActionStatus.executed,
            revision_before=base_revision + offset,
            revision_after=base_revision + offset + 1,
            result_json="{}",
            completed_at=datetime.now(UTC),
            source="vidat_import",
            annotation_package_id=package.id,
            vidat_import_audit_id=audit.id,
        )
        db.add(record)
    take.revision = base_revision + len(plan["coding_actions"])

    range_types = {
        "set_start": (TimelineEventType.set_start, TimelineEventType.set_end, SegmentType.set),
        "game_start": (TimelineEventType.game_start, TimelineEventType.game_end, SegmentType.game),
        "rally_start": (TimelineEventType.rally_start, TimelineEventType.rally_end, SegmentType.rally),
    }
    segment_rows: list[tuple[dict, CaptureSegment]] = []
    ordinals = {SegmentType.set: 0, SegmentType.game: 0, SegmentType.rally: 0}
    for operation in plan["operations"]:
        event_type = operation["event_type"]
        if event_type in range_types:
            start_type, end_type, segment_type = range_types[event_type]
            ordinals[segment_type] += 1
            start_id, end_id = (
                f"te_vidat_{audit.id[-8:]}_{operation['index']:04d}_s",
                f"te_vidat_{audit.id[-8:]}_{operation['index']:04d}_e",
            )
            start_event = SessionTimelineEvent(
                id=start_id,
                field_session_id=take.field_session_id,
                capture_take_id=take.id,
                recording_session_id=take.source_session_id,
                timestamp_ms=operation["start_ms"],
                event_type=start_type,
                source=TimelineEventSource.vidat_import,
                label=operation["label"],
                note=operation["note"],
                payload_json=json.dumps(operation["payload"], ensure_ascii=False),
                annotation_package_id=package.id,
                vidat_import_audit_id=audit.id,
            )
            end_event = SessionTimelineEvent(
                id=end_id,
                field_session_id=take.field_session_id,
                capture_take_id=take.id,
                recording_session_id=take.source_session_id,
                timestamp_ms=operation["end_ms"],
                event_type=end_type,
                source=TimelineEventSource.vidat_import,
                payload_json=json.dumps(operation["payload"], ensure_ascii=False),
                annotation_package_id=package.id,
                vidat_import_audit_id=audit.id,
            )
            segment = CaptureSegment(
                id=f"seg_vidat_{audit.id[-8:]}_{operation['index']:04d}",
                capture_take_id=take.id,
                segment_type=segment_type,
                ordinal=ordinals[segment_type],
                label=operation["label"],
                start_event_id=start_id,
                end_event_id=end_id,
                start_ms=operation["start_ms"],
                end_ms=operation["end_ms"],
                status=SegmentStatus.corrected,
                edit_status=EditStatus.active,
                source=SegmentSource.vidat_import,
                annotation_package_id=package.id,
                vidat_import_audit_id=audit.id,
            )
            db.add_all([start_event, end_event, segment])
            segment_rows.append((operation, segment))
        else:
            try:
                timeline_type = TimelineEventType(event_type)
            except ValueError:
                timeline_type = TimelineEventType.custom_marker
            db.add(
                SessionTimelineEvent(
                    id=f"te_vidat_{audit.id[-8:]}_{operation['index']:04d}",
                    field_session_id=take.field_session_id,
                    capture_take_id=take.id,
                    recording_session_id=take.source_session_id,
                    timestamp_ms=operation["start_ms"],
                    event_type=timeline_type,
                    source=TimelineEventSource.vidat_import,
                    label=operation["label"],
                    note=operation["note"],
                    payload_json=json.dumps(operation["payload"], ensure_ascii=False),
                    annotation_package_id=package.id,
                    vidat_import_audit_id=audit.id,
                )
            )
    db.flush()
    for operation, segment in segment_rows:
        if segment.segment_type == SegmentType.game:
            parent = next(
                (
                    row
                    for op, row in segment_rows
                    if row.segment_type == SegmentType.set
                    and op["start_ms"] <= operation["start_ms"]
                    and operation["end_ms"] <= op["end_ms"]
                ),
                None,
            )
            segment.parent_segment_id = parent.id if parent else None
        elif segment.segment_type == SegmentType.rally:
            parent = next(
                (
                    row
                    for op, row in segment_rows
                    if row.segment_type == SegmentType.game
                    and op["start_ms"] <= operation["start_ms"]
                    and operation["end_ms"] <= op["end_ms"]
                ),
                None,
            )
            segment.parent_segment_id = parent.id if parent else None

    final = plan["score_summary"]["final"]
    state = db.get(LiveCodingState, take.id)
    if state is None:
        state = LiveCodingState(capture_take_id=take.id)
        db.add(state)
    state.revision = take.revision
    state.score_a, state.score_b = final["score_a"], final["score_b"]
    state.games_won_a, state.games_won_b = final["games_won_a"], final["games_won_b"]
    state.match_status, state.match_winner = final["match_status"], final["match_winner"]
    state.set_ordinal, state.game_ordinal, state.rally_ordinal = (
        ordinals[SegmentType.set],
        ordinals[SegmentType.game],
        ordinals[SegmentType.rally],
    )
    state.current_set_segment_id = state.current_game_segment_id = state.current_rally_segment_id = None
    state.match_phase = "completed" if final["match_status"] == "completed" else "idle"


def vidat_config() -> dict:
    # objectLabelData 必须多于 1 个条目，VIDAT 才会在 Mode 下拉里显示 object /
    # skeleton 模式，从而暴露「copy from left to right」等双关键帧工具。
    # skeletonTypeData 为空时 skeleton 模式不会出现。
    return {
        "objectLabelData": [
            {"id": 0, "name": "default", "color": "#00FF00"},
            {"id": 1, "name": "player0", "color": "#66CCFF"},
            {"id": 2, "name": "player1", "color": "#39C5BB"},
            {"id": 3, "name": "court", "color": "#114514"},
        ],
        "actionLabelData": [
            {"id": 0, "name": "default", "color": "#00FF00", "objects": [0, 1, 2, 3]},
            *[
                {"id": action_id, "name": f"{label} ({event_type})", "color": color, "objects": [0, 1, 2, 3]}
                for event_type, (action_id, label, color) in EVENT_LABELS.items()
            ],
        ],
        "skeletonTypeData": [
            {
                "id": 0,
                "name": "human",
                "description": "open pose",
                "color": "#00FF00",
                "pointList": [
                    {"id": 0, "name": "nose", "x": 0, "y": -30},
                    {"id": 1, "name": "left eye", "x": -3, "y": -35},
                    {"id": 2, "name": "right eye", "x": 3, "y": -35},
                    {"id": 3, "name": "left ear", "x": -7, "y": -32},
                    {"id": 4, "name": "right ear", "x": 7, "y": -32},
                    {"id": 5, "name": "left shoulder", "x": -13, "y": -20},
                    {"id": 6, "name": "right shoulder", "x": 13, "y": -20},
                    {"id": 7, "name": "left wrist", "x": -15, "y": 10},
                    {"id": 8, "name": "right wrist", "x": 15, "y": 10},
                    {"id": 9, "name": "left hip", "x": -8, "y": 10},
                    {"id": 10, "name": "right hip", "x": 8, "y": 10},
                    {"id": 11, "name": "left knee", "x": -9, "y": 30},
                    {"id": 12, "name": "right knee", "x": 9, "y": 30},
                    {"id": 13, "name": "left ankle", "x": -10, "y": 45},
                    {"id": 14, "name": "right ankle", "x": 10, "y": 45},
                ],
                "edgeList": [
                    {"id": 0, "from": 0, "to": 1},
                    {"id": 1, "from": 0, "to": 2},
                    {"id": 2, "from": 0, "to": 3},
                    {"id": 3, "from": 0, "to": 4},
                    {"id": 4, "from": 0, "to": 9},
                    {"id": 5, "from": 0, "to": 10},
                    {"id": 6, "from": 5, "to": 7},
                    {"id": 7, "from": 5, "to": 6},
                    {"id": 8, "from": 6, "to": 8},
                    {"id": 9, "from": 9, "to": 11},
                    {"id": 10, "from": 11, "to": 13},
                    {"id": 11, "from": 10, "to": 12},
                    {"id": 12, "from": 12, "to": 14},
                ],
            }
        ],
    }


def _probe_video(path: Path) -> dict:
    timeout_seconds = max(15, int(os.getenv("PICKLEBALL_VIDAT_PROBE_TIMEOUT_SECONDS", "120")))
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration:stream=width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        numerator, denominator = stream.get("r_frame_rate", "30/1").split("/", 1)
        return {
            "fps": float(numerator) / float(denominator),
            "duration": float(payload["format"]["duration"]),
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
        }
    except subprocess.TimeoutExpired as exc:
        fallback = _probe_recording_sidecar(path)
        if fallback is not None:
            return fallback
        raise VidatPackageError(f"读取视频元数据超时（{timeout_seconds} 秒），且录制元数据不可用: {path}") from exc
    except (
        FileNotFoundError,
        subprocess.SubprocessError,
        KeyError,
        StopIteration,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise VidatPackageError(f"无法读取视频元数据: {exc}") from exc


def _probe_recording_sidecar(path: Path) -> dict | None:
    """Use capture metadata when a slow external volume blocks ffprobe."""
    candidates = (path.parent / "metadata" / "recording_session.json", path.parent / "manifest.json")
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            continue
        duration = payload.get("duration_sec")
        fps = payload.get("fps")
        resolution = str(payload.get("resolution") or "")
        if (
            not isinstance(duration, (int, float))
            or float(duration) <= 0
            or not isinstance(fps, (int, float))
            or float(fps) <= 0
        ):
            continue
        try:
            width, height = (int(value) for value in resolution.lower().split("x", 1))
        except (ValueError, AttributeError):
            continue
        return {"fps": float(fps), "duration": float(duration), "width": width, "height": height}
    return None


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    stat = path.stat()
    digest.update(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    with path.open("rb") as source:
        digest.update(source.read(1024 * 1024))
    return digest.hexdigest()


def resolve_primary_video(db: Session, take: CaptureTake) -> Path:
    track = (
        db.query(CaptureTrack)
        .filter(
            CaptureTrack.capture_take_id == take.id,
            CaptureTrack.role == TrackRole.primary,
        )
        .first()
    )
    if track is None:
        raise VidatPackageError("没有可用主机位轨道")
    finalization = (
        db.query(TrackFinalization)
        .filter(
            TrackFinalization.capture_track_id == track.id,
            TrackFinalization.status == FinalizationStatus.completed,
        )
        .order_by(TrackFinalization.completed_at.desc())
        .first()
    )
    candidates: list[Path] = []
    if finalization and finalization.output_path:
        candidates.append(Path(finalization.output_path))
    if track.video_id:
        metadata = video_service.get_video(track.video_id)
        if metadata:
            candidates.append(Path(metadata.path))
    # 外置存储的 Capture manifest 以 session_dir 作为稳定定位符。合并完成后
    # 的 <camera>_merged.mp4 可直接被 Vidat 使用，无需重新复制进项目目录。
    if take.session_dir:
        session_dir = Path(take.session_dir)
        if session_dir.is_dir():
            camera_prefix = str(track.camera_id).split("_")[0]
            candidates.extend(sorted(session_dir.glob(f"{camera_prefix}_merged.mp4")))
            candidates.extend(sorted(session_dir.glob("*_merged.mp4")))
    fragment = (
        db.query(MediaFragment)
        .filter(
            MediaFragment.capture_track_id == track.id,
        )
        .order_by(MediaFragment.fragment_index)
        .first()
    )
    if fragment:
        candidates.append(Path(fragment.file_path))
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate.resolve()
    raise VidatPackageError("主机位视频尚未就绪；请先完成视频合并或登记")


def _event_actions(db: Session, take_id: str, fps: float) -> list[dict]:
    from app.models.timeline_event import SessionTimelineEvent

    events = (
        db.query(SessionTimelineEvent)
        .filter(
            SessionTimelineEvent.capture_take_id == take_id,
            SessionTimelineEvent.is_undone.is_(False),
        )
        .order_by(SessionTimelineEvent.timestamp_ms)
        .all()
    )
    actions = []
    pair_end = {
        "set_start": "set_end",
        "game_start": "game_end",
        "rally_start": "rally_end",
        "timeout_start": "timeout_end",
        "non_play_start": "non_play_end",
    }
    pending = {start: [] for start in pair_end}

    def append_action(start_event, end_event=None):
        event_type = start_event.event_type.value
        label = EVENT_LABELS.get(event_type)
        if not label:
            return
        action_id, _, color = label
        # Vidat 2.x stores action boundaries in seconds. Only keyframeList and
        # video.frames use frame indices.
        start_time = round(start_event.timestamp_ms / 1000, 3)
        end_time = round((end_event.timestamp_ms if end_event else start_event.timestamp_ms) / 1000, 3)
        payload = json.loads(start_event.payload_json or "{}")
        if end_event:
            payload.update(json.loads(end_event.payload_json or "{}"))
        metadata = {
            "event_ids": [start_event.id] + ([end_event.id] if end_event else []),
            "event_type": event_type,
            "payload": payload,
            "label": start_event.label or (end_event.label if end_event else ""),
            "note": start_event.note or (end_event.note if end_event else ""),
        }
        actions.append(
            {
                "start": start_time,
                "end": max(start_time + 0.001, end_time),
                "action": action_id,
                "object": 0,
                "color": color,
                "description": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            }
        )

    for event in events:
        event_type = event.event_type.value
        if event_type in pair_end:
            pending[event_type].append(event)
            continue
        start_type = next((start for start, end in pair_end.items() if end == event_type), None)
        if start_type and pending[start_type]:
            append_action(pending[start_type].pop(0), event)
        else:
            append_action(event)
    for waiting in pending.values():
        for event in waiting:
            append_action(event)
    return actions


def create_annotation_package(db: Session, capture_take_id: str, *, copy_video: bool = False) -> VidatAnnotationPackage:
    take = db.get(CaptureTake, capture_take_id)
    if take is None:
        raise VidatPackageError("CaptureTake 不存在")
    # 允许 completed / partial / failed 的录制导出标注包：failed 可能只是后台合并
    # 或收尾步骤出错，主机位视频仍可能已生成并可用于 Vidat 标注。
    if take.status not in {CaptureTakeStatus.completed, CaptureTakeStatus.partial, CaptureTakeStatus.failed}:
        raise VidatPackageError("录制尚未完成")
    video = resolve_primary_video(db, take)
    info = _probe_video(video)
    root = get_settings().resolve_path(get_settings().data_dir) / "vidat-annotations" / take.id
    version = (
        db.query(func.max(VidatAnnotationPackage.version))
        .filter(VidatAnnotationPackage.capture_take_id == take.id)
        .scalar()
        or 0
    ) + 1
    package_id = f"vap_{uuid4().hex[:12]}"
    package_dir = root / f"v{version:03d}-{package_id[-6:]}"
    package_dir.mkdir(parents=True, exist_ok=False)
    video_path = package_dir / f"video{video.suffix.lower()}"
    if copy_video:
        shutil.copy2(video, video_path)
    else:
        os.symlink(video, video_path)
    actions = _event_actions(db, take.id, info["fps"])
    frames = max(1, round(info["duration"] * info["fps"]))
    actions = [action for action in actions if action["start"] < info["duration"]]
    for action in actions:
        action["end"] = min(round(info["duration"], 3), max(action["start"] + 0.001, action["end"]))
    actions.insert(
        0,
        {
            "start": 0,
            "end": round(info["duration"], 3),
            "action": 0,
            "object": 0,
            "color": "#00FF00",
            "description": "",
        },
    )
    annotation = {
        "version": "2.0.5",
        "annotation": {
            "video": {
                "src": f"video/{video_path.name}",
                "fps": round(info["fps"], 6),
                "frames": frames,
                "duration": round(info["duration"], 3),
                "width": info["width"],
                "height": info["height"],
            },
            "keyframeList": sorted(
                {
                    0,
                    frames,
                    *(round(a["start"] * info["fps"]) for a in actions),
                    *(round(a["end"] * info["fps"]) for a in actions),
                }
            ),
            "objectAnnotationListMap": {},
            "regionAnnotationListMap": {},
            "skeletonAnnotationListMap": {},
            "actionAnnotationList": actions,
        },
        "config": vidat_config(),
    }
    manifest = {
        "schema_version": VIDAT_SCHEMA_VERSION,
        "package_id": package_id,
        "capture_take_id": take.id,
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "timeline_revision": take.revision,
        "video": {"file": video_path.name, "source": str(video), "fingerprint": _fingerprint(video), **info},
    }
    annotation["pickleball_manifest"] = {
        "schema_version": VIDAT_SCHEMA_VERSION,
        "package_id": package_id,
        "capture_take_id": take.id,
        "video_fingerprint": manifest["video"]["fingerprint"],
    }
    (package_dir / "annotation.json").write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "config.json").write_text(json.dumps(vidat_config(), ensure_ascii=False, indent=2), encoding="utf-8")
    (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    package = VidatAnnotationPackage(
        id=package_id,
        capture_take_id=take.id,
        version=version,
        package_dir=str(package_dir),
        manifest_json=json.dumps(manifest, ensure_ascii=False),
        annotation_json=json.dumps(annotation, ensure_ascii=False),
    )
    db.add(package)
    return package


def publish_annotation_package(package: VidatAnnotationPackage, dist_root: Path) -> str:
    """将受管理标注包以链接方式发布给 Vidat 静态目录。"""
    root = dist_root.resolve()
    if not (root / "index.html").is_file():
        raise VidatPackageError("VIDAT_DIST 必须指向包含 index.html 的 Vidat dist 目录")
    package_dir = Path(package.package_dir).resolve()
    if not (package_dir / "manifest.json").is_file():
        raise VidatPackageError("标注包文件缺失")
    manifest = json.loads(package.manifest_json)
    source_annotation = json.loads(package.annotation_json)
    source_video = package_dir / manifest["video"]["file"]
    if not source_video.is_file():
        raise VidatPackageError("标注包视频引用已失效")
    annotation_payload = source_annotation.setdefault("annotation", {})
    actions = annotation_payload.setdefault("actionAnnotationList", [])
    if not actions or actions[0].get("action") != 0:
        duration = float(annotation_payload.get("video", {}).get("duration") or manifest["video"].get("duration", 0))
        actions.insert(
            0,
            {
                "start": 0,
                "end": max(0.001, round(duration, 3)),
                "action": 0,
                "object": 0,
                "color": "#00FF00",
                "description": "",
            },
        )
    suffix = source_video.suffix.lower()
    video_name = f"{package.id}{suffix}"
    annotation_name = f"{package.id}.json"
    config_name = f"{package.id}.json"
    worker_fps = max(1, round(float(manifest["video"].get("fps", 30))))
    source_annotation["annotation"]["video"]["src"] = f"video/{video_name}"
    for target, source, content in (
        (root / "video" / video_name, source_video, None),
        (root / "annotation" / annotation_name, None, source_annotation),
        (root / "config" / config_name, None, vidat_config()),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        if content is None:
            target.symlink_to(source)
        else:
            target.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    # Vidat resolves query parameters from the static site root. Include the
    # managed subdirectories so its loader requests the files we published.
    # V2 decodes the media in a worker and fills the shared frame cache used by
    # both canvases. Keep the worker FPS aligned with annotation.video.fps
    # otherwise a 60 FPS annotation asks for frame ids the 30 FPS worker never
    # produces, leaving the right canvas blank.
    # showObjects=true 暴露 object 模式（双关键帧 left/right 画面 + copy 按钮）；
    # mode=object 让标注包直接打开到双关键帧视图。showActions 仍保留，可下拉切回。
    return f"?video=video/{video_name}&config=config/{config_name}&annotation=annotation/{annotation_name}&mode=object&showActions=true&showObjects=true&showRegions=false&showSkeletons=true&decoder=v2&defaultfps={worker_fps}"  # noqa: E501
