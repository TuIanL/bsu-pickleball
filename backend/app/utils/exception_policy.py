"""Declarative policies for deliberately isolated, non-fatal exceptions."""

from __future__ import annotations

from functools import wraps

from app.services.analysis_errors import JobCanceledError, StageTimeoutError, WorkerLeaseLostError
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def swallow(*, why: str, default: Any = None) -> Callable[[F], F]:
    """Return a decorator that catches ordinary exceptions with an auditable reason.

    Use only when a failure is intentionally non-fatal and the caller can safely
    continue with ``default``. The reason is attached to the wrapper for inspection.
    """
    if not why.strip():
        raise ValueError("swallow requires a non-empty reason")

    def decorate(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return function(*args, **kwargs)
            except (JobCanceledError, StageTimeoutError, WorkerLeaseLostError):
                raise
            except Exception:
                return default

        setattr(wrapped, "__swallow_why__", why.strip())
        return cast(F, wrapped)

    return decorate
