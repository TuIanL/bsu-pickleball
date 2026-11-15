"""Stable content identity for research evidence assets.

Asset identity is derived from the content digest only. The same bytes keep the
same id across platforms, mount points and duplicate copies; a path never
participates in identity, because a path is a location rather than an identity.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

ASSET_ID_PREFIX = "a_"
ASSET_ID_HEX_CHARS = 12


class IdentityError(ValueError):
    """Base error for content identity construction."""


class InvalidDigestError(IdentityError):
    """Raised when a digest is not a lowercase 64-character SHA-256 hex string."""


class IdentityCollisionError(IdentityError):
    """Raised when two distinct digests resolve to the same short asset id."""


def normalize_sha256(value: object) -> str:
    """Return a canonical lowercase digest or raise InvalidDigestError."""
    if not isinstance(value, str):
        raise InvalidDigestError(f"digest must be a string, got {type(value).__name__}")
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise InvalidDigestError(
            f"digest must be 64 lowercase hex characters, got {value!r}"
        )
    return normalized


def asset_id_from_digest(value: str) -> str:
    """Derive a stable asset id from a content digest.

    Identical content yields an identical id regardless of where it lives.
    Distinct content yields distinct ids unless the leading characters collide;
    that case is rejected by ``assign_content_ids`` instead of being silently
    aliased.
    """
    return f"{ASSET_ID_PREFIX}{normalize_sha256(value)[:ASSET_ID_HEX_CHARS]}"


def assign_content_ids(digests_by_locator: Mapping[str, str]) -> dict[str, str]:
    """Map every locator to its content asset id, rejecting prefix collisions."""
    resolved: dict[str, str] = {}
    seen: dict[str, str] = {}
    for locator in sorted(digests_by_locator):
        digest = normalize_sha256(digests_by_locator[locator])
        asset_id = f"{ASSET_ID_PREFIX}{digest[:ASSET_ID_HEX_CHARS]}"
        previous = seen.get(asset_id)
        if previous is not None and previous != digest:
            raise IdentityCollisionError(
                f"asset id {asset_id} would stand for two digests: {previous} and {digest}"
            )
        seen[asset_id] = digest
        resolved[locator] = asset_id
    return resolved


def group_by_content(digests_by_locator: Mapping[str, str]) -> dict[str, list[str]]:
    """Group locators by content asset id.

    Identical content found at several paths collapses into one identity, which
    is how duplicate copies are detected without comparing or trusting paths.
    """
    grouped: dict[str, list[str]] = {}
    for locator, asset_id in assign_content_ids(digests_by_locator).items():
        grouped.setdefault(asset_id, []).append(locator)
    return {
        asset_id: sorted(locators) for asset_id, locators in sorted(grouped.items())
    }
