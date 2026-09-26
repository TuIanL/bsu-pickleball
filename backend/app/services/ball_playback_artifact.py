"""Small, JSON-safe playback projection of the immutable forensic artifact."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

_DIAGNOSTIC_KEYS = {"counters", "failure_reason", "pipeline", "quality_gate_version", "overall_status"}


def playback_path(source: Path) -> Path:
    return source.with_suffix(".playback.json")


def playback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def safe(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [safe(item) for item in value]
        return value

    return safe({**payload, "diagnostics": {
        key: value for key, value in (payload.get("diagnostics") or {}).items()
        if key in _DIAGNOSTIC_KEYS
    }})
