"""Versioned, opt-in runtime evidence for joint visual acceptance runs."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping


JOINT_DEBUG_TRACE_SCHEMA = "joint_debug_trace.v1"
JOINT_DEBUG_TRACE_FILENAME = "joint_debug_trace.v1.json"
JOINT_DEBUG_MANIFEST_SCHEMA = "joint_debug_manifest.v1"
JOINT_DEBUG_MANIFEST_FILENAME = "joint_debug_manifest.json"


def build_joint_debug_trace(
    *,
    run_id: str,
    capture_take_id: str,
    reference_view_id: str,
    timing_authority_by_view: Mapping[str, str],
    sync_quality: str,
    execution_mode: str,
    authoritative_joint_eligible: bool,
    ticks: list[dict[str, object]],
) -> dict[str, object]:
    payload = {
        "schema_version": JOINT_DEBUG_TRACE_SCHEMA,
        "run_id": run_id,
        "capture_take_id": capture_take_id,
        "reference_view_id": reference_view_id,
        "timing_authority_by_view": dict(timing_authority_by_view),
        "sync_quality": sync_quality,
        "execution_mode": execution_mode,
        "authoritative_joint_eligible": authoritative_joint_eligible,
        "tick_count": len(ticks),
        "ticks": ticks,
    }
    validate_joint_debug_trace(payload)
    return payload


def validate_joint_debug_trace(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("joint debug trace must be an object")
    if payload.get("schema_version") != JOINT_DEBUG_TRACE_SCHEMA:
        raise ValueError(f"expected {JOINT_DEBUG_TRACE_SCHEMA}")
    for field in (
        "run_id",
        "capture_take_id",
        "reference_view_id",
        "timing_authority_by_view",
        "sync_quality",
        "execution_mode",
        "authoritative_joint_eligible",
    ):
        if field not in payload:
            raise ValueError(f"joint debug trace missing {field}")
    ticks = payload.get("ticks")
    if not isinstance(ticks, list):
        raise ValueError("joint debug trace ticks must be a list")
    if payload.get("tick_count") != len(ticks):
        raise ValueError("joint debug trace tick_count does not match ticks")
    for index, tick in enumerate(ticks):
        if not isinstance(tick, dict):
            raise ValueError(f"trace tick {index} must be an object")
        for field in (
            "canonical_tick",
            "reference_frame_index",
            "canonical_timestamp_ms",
            "authoritative_tick",
            "frame_status",
            "views",
            "global_predictions",
            "canonical_observations",
            "fused",
            "recovery",
        ):
            if field not in tick:
                raise ValueError(f"trace tick {index} missing {field}")
        if not isinstance(tick["frame_status"], dict) or not isinstance(tick["views"], dict):
            raise ValueError(f"trace tick {index} frame_status/views must be objects")
        for view_id, view in tick["views"].items():
            if not isinstance(view, dict):
                raise ValueError(f"trace tick {index}/{view_id} view must be an object")
            for field in (
                "status",
                "source_frame_index",
                "source_timestamp_ms",
                "mapped_take_timestamp_ms",
                "selection_error_ms",
                "timing_authority",
                "observations",
                "observation_status",
                "detections",
                "guidance",
                "bindings",
            ):
                if field not in view:
                    raise ValueError(f"trace tick {index}/{view_id} missing {field}")
            if not isinstance(view["observations"], list) or not isinstance(view["detections"], list):
                raise ValueError(f"trace tick {index}/{view_id} observations/detections must be lists")
            if not isinstance(view["guidance"], list) or not isinstance(view["bindings"], dict):
                raise ValueError(f"trace tick {index}/{view_id} guidance/bindings have invalid types")
            # debug-only 可选候选层：缺失 → 通过；存在但非 list → 失败（list 级校验，
            # 不做逐元素加强，保证历史 trace 全量兼容；元素形状由 producer 单测锁定）。
            candidate_detections = view.get("candidate_detections")
            if candidate_detections is not None and not isinstance(candidate_detections, list):
                raise ValueError(f"trace tick {index}/{view_id} candidate_detections must be a list")


def build_joint_debug_manifest(
    *,
    run_id: str,
    capture_take_id: str,
    trace_filename: str = JOINT_DEBUG_TRACE_FILENAME,
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "schema_version": JOINT_DEBUG_MANIFEST_SCHEMA,
        "run_id": run_id,
        "capture_take_id": capture_take_id,
        "trace_schema": JOINT_DEBUG_TRACE_SCHEMA,
        "trace_filename": trace_filename,
        "debug_trace_enabled": True,
        "config": dict(config or {}),
    }
    validate_joint_debug_manifest(payload)
    return payload


def validate_joint_debug_manifest(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("joint debug manifest must be an object")
    if payload.get("schema_version") != JOINT_DEBUG_MANIFEST_SCHEMA:
        raise ValueError(f"expected {JOINT_DEBUG_MANIFEST_SCHEMA}")
    for field in (
        "run_id",
        "capture_take_id",
        "trace_schema",
        "trace_filename",
        "debug_trace_enabled",
        "config",
    ):
        if field not in payload:
            raise ValueError(f"joint debug manifest missing {field}")
    if payload["trace_schema"] != JOINT_DEBUG_TRACE_SCHEMA:
        raise ValueError("joint debug manifest trace schema mismatch")
    if payload["debug_trace_enabled"] is not True:
        raise ValueError("joint debug manifest must describe an enabled trace")
    if not isinstance(payload["config"], dict):
        raise ValueError("joint debug manifest config must be an object")


def write_joint_debug_trace(path: str | os.PathLike[str], payload: dict[str, object]) -> Path:
    validate_joint_debug_trace(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", suffix=".part", delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(payload, handle, ensure_ascii=True, indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def load_joint_debug_trace(path: str | os.PathLike[str]) -> dict[str, object]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"joint debug trace missing: {target}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"joint debug trace unreadable: {target}: {exc}") from exc
    validate_joint_debug_trace(payload)
    return payload
