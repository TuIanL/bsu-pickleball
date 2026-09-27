"""CaptureSegment ORM 对象到 API 字典的单一映射来源。

片段编辑路由（`routes_segment_editing`）与片段列表路由（`routes_coding_actions`）
必须对外暴露同一份字段契约，因此映射被抽到本模块：列表路由此前从另一个路由模块
导入私有 helper，形成「路由 → 路由」的反向耦合，任一侧重命名都会静默打断另一侧。

字段名、兼容缺省值（`effective_*` 回退到原始值、`edit_version` 回退 0）与枚举取值
都与抽取前逐字保持一致；本模块只做序列化，不读写数据库。
"""

from __future__ import annotations


def segment_to_api_dict(seg) -> dict:
    """把一个 CaptureSegment（或兼容的测试替身）序列化为既有 API 字典。"""
    return {
        "id": seg.id,
        "capture_take_id": seg.capture_take_id,
        "segment_type": seg.segment_type.value if hasattr(seg.segment_type, "value") else seg.segment_type,
        "parent_segment_id": seg.parent_segment_id,
        "ordinal": seg.ordinal,
        "label": seg.label,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "corrected_start_ms": seg.corrected_start_ms,
        "corrected_end_ms": seg.corrected_end_ms,
        "corrected_at": seg.corrected_at.isoformat() if getattr(seg, "corrected_at", None) else None,
        "effective_start_ms": seg.effective_start_ms if hasattr(seg, "effective_start_ms") else seg.start_ms,
        "effective_end_ms": seg.effective_end_ms if hasattr(seg, "effective_end_ms") else seg.end_ms,
        "edit_version": seg.edit_version if hasattr(seg, "edit_version") else 0,
        "created_by_operation_id": getattr(seg, "created_by_operation_id", None),
        "edit_status": seg.edit_status.value
        if hasattr(seg.edit_status, "value")
        else getattr(seg, "edit_status", "active"),
        "status": seg.status.value if hasattr(seg.status, "value") else seg.status,
        "source": seg.source.value if hasattr(seg.source, "value") else seg.source,
        "segmentation_run_id": getattr(seg, "segmentation_run_id", None),
        "is_highlight": seg.is_highlight,
    }
