"""Research evidence indexing without app runtime bootstrap.

This package holds the pure helpers used by ``scripts/research_evidence.py``.
It must stay importable without initialising the database, models or the
application lifespan.
"""

from .classification import (
    EXPECTED_CONTAINERS,
    AdmissionError,
    ClassificationError,
    ClassificationEvidence,
    UnreadableMediaError,
    assert_formal_input_eligible,
    classify_path_for_admission,
    classify_usage_kind,
    extension_matches_container,
    probe_container,
)
from .identity import (
    ASSET_ID_HEX_CHARS,
    ASSET_ID_PREFIX,
    IdentityCollisionError,
    IdentityError,
    InvalidDigestError,
    asset_id_from_digest,
    assign_content_ids,
    group_by_content,
    normalize_sha256,
)
from .locations import (
    LOCATIONS_SCHEMA_VERSION,
    LOCATOR_SCHEME,
    LocationError,
    assert_no_local_paths,
    build_locator,
    find_local_paths,
    is_absolute_path,
    parse_locator,
    resolve_locator,
)

__all__ = [
    "ASSET_ID_HEX_CHARS",
    "ASSET_ID_PREFIX",
    "EXPECTED_CONTAINERS",
    "AdmissionError",
    "ClassificationError",
    "ClassificationEvidence",
    "IdentityCollisionError",
    "IdentityError",
    "InvalidDigestError",
    "LOCATIONS_SCHEMA_VERSION",
    "LOCATOR_SCHEME",
    "LocationError",
    "UnreadableMediaError",
    "assert_formal_input_eligible",
    "assert_no_local_paths",
    "asset_id_from_digest",
    "assign_content_ids",
    "build_locator",
    "classify_path_for_admission",
    "classify_usage_kind",
    "extension_matches_container",
    "find_local_paths",
    "group_by_content",
    "is_absolute_path",
    "normalize_sha256",
    "parse_locator",
    "probe_container",
    "resolve_locator",
]
