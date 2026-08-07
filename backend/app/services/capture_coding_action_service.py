"""CaptureCodingAction 服务层 —— 持久化命令日志、幂等性。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_coding_action import CaptureCodingAction, CodingActionStatus

# 命令动作 ID 前缀
_ID_PREFIX = "ca"


# 生成带前缀的唯一 ID（ca_ + 12 位随机十六进制）
def _generate_id() -> str:
    return f"{_ID_PREFIX}_{uuid4().hex[:12]}"


# 根据动作类型与负载计算请求哈希，用于幂等去重
def compute_request_hash(action_type: str, payload: dict) -> str:
    raw = json.dumps({"action": action_type, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


# 按 take 与客户端动作 ID 查找已存在的命令动作（幂等判断）
def find_existing_action(db: Session, capture_take_id: str, client_action_id: str) -> CaptureCodingAction | None:
    return (
        db.query(CaptureCodingAction)
        .filter(
            CaptureCodingAction.capture_take_id == capture_take_id,
            CaptureCodingAction.client_action_id == client_action_id,
        )
        .first()
    )


# 创建一条命令动作记录并写入数据库（状态为 executed）
def create_action_record(
    db: Session,
    *,
    capture_take_id: str,
    client_action_id: str,
    action_type: str,
    timestamp_ms: int,
    payload_json: dict | None = None,
    request_hash: str,
    revision_before: int,
) -> CaptureCodingAction:
    now = datetime.now(UTC)
    action = CaptureCodingAction(
        id=_generate_id(),
        capture_take_id=capture_take_id,
        client_action_id=client_action_id,
        action_type=action_type,
        timestamp_ms=timestamp_ms,
        payload_json=json.dumps(payload_json or {}, ensure_ascii=False),
        request_hash=request_hash,
        status=CodingActionStatus.executed,
        revision_before=revision_before,
        created_at=now,
    )
    db.add(action)
    db.flush()
    return action


# 标记命令动作执行完成，记录执行后的版本号与结果
def complete_action_record(
    db: Session,
    action: CaptureCodingAction,
    *,
    revision_after: int,
    result_json: str | None = None,
) -> None:
    action.status = CodingActionStatus.executed
    action.revision_after = revision_after
    action.result_json = result_json
    action.completed_at = datetime.now(UTC)
    db.flush()


# 将命令动作标记为已撤销（undone），清空后续版本与完成时间
def mark_action_undone(db: Session, action: CaptureCodingAction) -> None:
    action.status = CodingActionStatus.undone
    action.revision_after = None
    action.completed_at = None
    db.flush()


# 获取最近一条可撤销的命令动作（非 undo 类型且已执行）
def get_last_undoable_action(db: Session, capture_take_id: str) -> CaptureCodingAction | None:
    return (
        db.query(CaptureCodingAction)
        .filter(
            CaptureCodingAction.capture_take_id == capture_take_id,
            CaptureCodingAction.status == CodingActionStatus.executed,
            CaptureCodingAction.action_type.notin_(["undo"]),
        )
        .order_by(CaptureCodingAction.created_at.desc())
        .first()
    )


# 列出某个 take 下的全部命令动作，按创建时间升序
def list_actions_for_take(db: Session, capture_take_id: str) -> list[CaptureCodingAction]:
    return (
        db.query(CaptureCodingAction)
        .filter(CaptureCodingAction.capture_take_id == capture_take_id)
        .order_by(CaptureCodingAction.created_at.asc())
        .all()
    )
