"""Collection-environment metadata governed by BRD-F05 and ADR-036."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib import metadata
from typing import Final

from attest_core import Collection, CollectorRef, EnvironmentKind, EnvironmentRef
from attest_core.errors import build_error

_COLLECTOR_NAME: Final[str] = "attest"
_COLLECTOR_DISTRIBUTION: Final[str] = "attest-collect"
_GITHUB_SERVER_URL: Final[str] = "https://github.com"
_GITHUB_OIDC_ISSUER: Final[str] = "https://token.actions.githubusercontent.com"
_INVALID_ENVIRONMENT = "environ must be a string mapping or None"
_INVALID_CLOCK_TYPE = "clock must return a datetime"
_INVALID_CLOCK_TIMEZONE = "clock must return an aware datetime"


def utc_now() -> datetime:
    """Return the default aware UTC collection clock."""
    return datetime.now(UTC)


def _nonempty(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    return value if isinstance(value, str) and value else None


def _positive_decimal(environ: Mapping[str, str], name: str) -> int | None:
    value = _nonempty(environ, name)
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value, 10)
    return parsed if parsed >= 1 else None


def _github_environment(environ: Mapping[str, str]) -> EnvironmentRef:
    run_id = _nonempty(environ, "GITHUB_RUN_ID")
    run_attempt = _positive_decimal(environ, "GITHUB_RUN_ATTEMPT")
    workflow_ref = _nonempty(environ, "GITHUB_WORKFLOW_REF")
    event_name = _nonempty(environ, "GITHUB_EVENT_NAME")
    trusted = all(
        (
            environ.get("GITHUB_SERVER_URL") == _GITHUB_SERVER_URL,
            run_id is not None,
            run_attempt is not None,
            workflow_ref is not None,
            event_name is not None,
            _nonempty(environ, "ACTIONS_ID_TOKEN_REQUEST_URL") is not None,
            _nonempty(environ, "ACTIONS_ID_TOKEN_REQUEST_TOKEN") is not None,
        )
    )
    return EnvironmentRef(
        kind=EnvironmentKind.GITHUB_ACTIONS,
        trusted=trusted,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow_ref=workflow_ref,
        oidc_issuer=_GITHUB_OIDC_ISSUER if trusted else None,
        event_name=event_name,
    )


def _environment(environ: Mapping[str, str]) -> EnvironmentRef:
    if environ.get("GITHUB_ACTIONS") == "true":
        return _github_environment(environ)
    if environ.get("GITLAB_CI") == "true":
        return EnvironmentRef(kind=EnvironmentKind.GITLAB_CI, trusted=False)
    if environ.get("CI") == "true":
        return EnvironmentRef(kind=EnvironmentKind.OTHER, trusted=False)
    return EnvironmentRef(kind=EnvironmentKind.LOCAL, trusted=False)


def _require_environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    if environ is not None and not isinstance(environ, Mapping):
        raise TypeError(_INVALID_ENVIRONMENT)
    return os.environ if environ is None else environ


def _require_collection_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(_INVALID_CLOCK_TYPE)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_INVALID_CLOCK_TIMEZONE)
    return value.astimezone(UTC).replace(microsecond=0)


def collect_environment(
    environ: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], datetime] = utc_now,
) -> Collection:
    """Collect safe runtime context as a typed Collection (REQ-F05-050/060/070)."""
    try:
        source = _require_environment(environ)
        collector_version = metadata.version(_COLLECTOR_DISTRIBUTION)
        collected_at = _require_collection_time(clock())
        return Collection(
            collector=CollectorRef(name=_COLLECTOR_NAME, version=collector_version),
            collected_at=collected_at,
            environment=_environment(source),
        )
    except Exception as error:
        raise build_error("ERR-BUILD-211") from error
