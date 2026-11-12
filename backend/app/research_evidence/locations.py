"""Local location mapping for research evidence assets.

The shareable manifest only carries logical ``asset://`` locators. Absolute
machine paths live in ``locations.local.json``, which is never exported with the
package, so a shared index cannot leak a personal directory layout.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOCATIONS_SCHEMA_VERSION = "pb.research-evidence-locations.v1.0"
LOCATOR_SCHEME = "asset://"

_ROOT_ID_PATTERN = re.compile(r"^root_[a-z0-9_]+$")
_ASSET_ID_PATTERN = re.compile(r"^a_[a-z0-9_]+$")
_POSIX_ABSOLUTE = re.compile(r"^/")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC = re.compile(r"^\\\\")
# Free text such as a note may embed a path; split on separators that cannot be
# part of a path so each candidate token can be classified exactly.
_TEXT_BREAK = re.compile(r"""[\s"'`,;()\[\]{}<>|]+""")

SourceKind = Literal["repository", "external_disk", "windows_machine", "derived"]


class LocationError(ValueError):
    """Raised when a locator or source root cannot be resolved safely."""


def is_absolute_path(value: str) -> bool:
    """Return True for POSIX, Windows drive-letter and UNC absolute paths."""
    if not isinstance(value, str) or not value:
        return False
    return bool(
        _POSIX_ABSOLUTE.match(value)
        or _WINDOWS_ABSOLUTE.match(value)
        or _WINDOWS_UNC.match(value)
    )


def _normalize_relative_path(relative_path: str) -> str:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise LocationError("relative path must be a non-empty string")
    if is_absolute_path(relative_path):
        raise LocationError(
            f"relative path must not be absolute, got {relative_path!r}"
        )
    normalized = relative_path.replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise LocationError(
            f"relative path must not traverse upwards, got {relative_path!r}"
        )
    if not parts:
        raise LocationError(f"relative path has no usable segments: {relative_path!r}")
    return "/".join(parts)


def build_locator(root_id: str, relative_path: str) -> str:
    """Build a portable logical locator from a source root and relative path."""
    if not _ROOT_ID_PATTERN.fullmatch(root_id or ""):
        raise LocationError(
            f"root id must match root_<lower snake case>, got {root_id!r}"
        )
    return f"{LOCATOR_SCHEME}{root_id}/{_normalize_relative_path(relative_path)}"


def parse_locator(locator: str) -> tuple[str, str]:
    """Split a logical locator into ``(root_id, relative_path)``."""
    if not isinstance(locator, str) or not locator.startswith(LOCATOR_SCHEME):
        raise LocationError(
            f"locator must start with {LOCATOR_SCHEME!r}, got {locator!r}"
        )
    remainder = locator[len(LOCATOR_SCHEME) :]
    root_id, separator, relative_path = remainder.partition("/")
    if not separator:
        raise LocationError(f"locator is missing a relative path: {locator!r}")
    if not _ROOT_ID_PATTERN.fullmatch(root_id):
        raise LocationError(f"locator has an invalid root id: {locator!r}")
    return root_id, _normalize_relative_path(relative_path)


def resolve_locator(locator: str, source_roots: dict[str, str]) -> Path:
    """Resolve a locator against authorised roots, refusing to escape them."""
    root_id, relative_path = parse_locator(locator)
    root_raw = source_roots.get(root_id)
    if root_raw is None:
        raise LocationError(f"locator references an unauthorised root: {root_id!r}")

    root = Path(root_raw)
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise LocationError(f"locator escapes its source root: {locator!r}")
    return candidate


def _contains_local_path(value: str) -> bool:
    """Detect a local path even when it is embedded in free text."""
    if is_absolute_path(value):
        return True
    for token in _TEXT_BREAK.split(value):
        if not token or token.startswith(LOCATOR_SCHEME):
            continue
        if is_absolute_path(token):
            return True
    return False


def find_local_paths(payload: Any, _path: str = "") -> list[str]:
    """Collect every string field that carries an absolute machine path.

    Logical ``asset://`` locators are skipped: they are the portable form that
    is allowed to travel inside a shared package.
    """
    found: list[str] = []
    if isinstance(payload, str):
        if _contains_local_path(payload):
            found.append(f"{_path or '<root>'}={payload}")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            found.extend(find_local_paths(value, f"{_path}/{key}" if _path else str(key)))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            found.extend(find_local_paths(value, f"{_path}[{index}]"))
    return found


def assert_no_local_paths(payload: Any) -> None:
    """Fail when a payload that is about to be shared contains local paths."""
    offenders = find_local_paths(payload)
    if offenders:
        joined = "; ".join(offenders[:5])
        raise LocationError(
            f"shareable payload contains absolute local paths: {joined}"
        )


class SourceRoot(BaseModel):
    """An explicitly authorised directory that the tool may read."""

    model_config = ConfigDict(extra="forbid")

    root_id: str
    path: str
    source_kind: SourceKind

    @field_validator("root_id")
    @classmethod
    def _validate_root_id(cls, value: str) -> str:
        if not _ROOT_ID_PATTERN.fullmatch(value):
            raise ValueError("root_id must match root_<lower snake case>")
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not is_absolute_path(value):
            raise ValueError("source root path must be absolute")
        return value


class AssetLocation(BaseModel):
    """Where one content asset lives on this machine."""

    model_config = ConfigDict(extra="forbid")

    locator: str
    relative_path: str
    source_root_id: str
    alternate_locators: list[str] = Field(default_factory=list)

    @field_validator("locator")
    @classmethod
    def _validate_locator(cls, value: str) -> str:
        parse_locator(value)
        return value

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return _normalize_relative_path(value)

    @field_validator("alternate_locators")
    @classmethod
    def _validate_alternates(cls, value: list[str]) -> list[str]:
        for locator in value:
            parse_locator(locator)
        return value

    @model_validator(mode="after")
    def _check_root_matches(self) -> "AssetLocation":
        root_id, parsed_relative = parse_locator(self.locator)
        if root_id != self.source_root_id:
            raise ValueError("locator root and source_root_id disagree")
        if parsed_relative != self.relative_path:
            raise ValueError("locator path and relative_path disagree")
        return self


class LocalLocationFile(BaseModel):
    """Contents of ``locations.local.json``.

    This file is intentionally separate from the manifest and must never be
    copied into a shared package.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pb.research-evidence-locations.v1.0"] = (
        LOCATIONS_SCHEMA_VERSION
    )
    package_id: str
    source_roots: dict[str, SourceRoot]
    assets: dict[str, AssetLocation]

    @field_validator("package_id")
    @classmethod
    def _validate_package_id(cls, value: str) -> str:
        if not re.fullmatch(r"^pkg_[0-9a-f]{12}$", value):
            raise ValueError("package_id must match pkg_<12 lowercase hex>")
        return value

    @field_validator("assets")
    @classmethod
    def _validate_asset_keys(cls, value: dict[str, AssetLocation]) -> dict[str, AssetLocation]:
        for asset_id in value:
            if not _ASSET_ID_PATTERN.fullmatch(asset_id):
                raise ValueError(f"invalid asset id key: {asset_id!r}")
        return value

    @model_validator(mode="after")
    def _check_roots_declared(self) -> "LocalLocationFile":
        declared = set(self.source_roots)
        used = {asset.source_root_id for asset in self.assets.values()}
        missing = used - declared
        if missing:
            raise ValueError(f"assets reference undeclared roots: {sorted(missing)}")
        for root_key, root in self.source_roots.items():
            if root_key != root.root_id:
                raise ValueError("source_roots key must equal its root_id")
        return self
