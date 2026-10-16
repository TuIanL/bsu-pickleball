"""Shared bearer-token authentication for all HTTP API routes."""

from __future__ import annotations

import ipaddress
import os
import secrets

from fastapi import Header, HTTPException, Request, status

API_TOKEN_ENV = "PICKLEBALL_API_TOKEN"
AUTH_DISABLED_ENV = "PICKLEBALL_AUTH_DISABLED"


def _auth_disabled() -> bool:
    return not os.environ.get(API_TOKEN_ENV, "").strip() and os.environ.get(AUTH_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def validate_api_auth_configuration() -> None:
    """Fail startup closed unless the operator configures a token or explicit bypass."""
    if _auth_disabled():
        return
    if not os.environ.get(API_TOKEN_ENV, "").strip():
        raise RuntimeError(
            f"{API_TOKEN_ENV} must be configured before starting the API. "
            f"Set {AUTH_DISABLED_ENV}=true only for an isolated development/test environment."
        )


def _require_token(authorization: str | None) -> None:
    if _auth_disabled():
        return
    expected = os.environ.get(API_TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "api_auth_unconfigured", "message": "API authentication is not configured."},
        )
    scheme, separator, supplied = (authorization or "").partition(" ")
    supplied_bytes = supplied.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if not separator or scheme.lower() != "bearer" or not secrets.compare_digest(supplied_bytes, expected_bytes):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "A valid bearer token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency and shared guard used by the application API boundary."""
    _require_token(authorization)


def local_documentation_enabled(request: Request) -> bool:
    """Allow documentation only for explicit local mode and a loopback request.

    Forwarded headers are deliberately ignored: a public proxy must not be able
    to opt in to local development documentation through client-supplied headers.
    """
    if os.environ.get("PICKLEBALL_LOCAL_DOCS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    if request.client is None or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False
