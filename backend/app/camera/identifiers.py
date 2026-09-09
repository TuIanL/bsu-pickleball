"""Validation helpers for user-controlled camera identifiers."""

from __future__ import annotations

import re
from pathlib import Path

_CAMERA_ID_RE = re.compile(r"^[^/\\\x00-\x1f\x7f]+$")


def validate_camera_id(camera_id: str) -> str:
    value = camera_id.strip()
    if not value or value in {".", ".."} or not _CAMERA_ID_RE.fullmatch(value):
        raise ValueError("camera_id must be a non-empty filename-safe identifier")
    if Path(value).is_absolute():
        raise ValueError("camera_id must not be an absolute path")
    return value
