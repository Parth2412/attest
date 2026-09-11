"""RFC 8785 canonicalisation governed by SPEC-001 §4."""

from __future__ import annotations

import rfc8785

from attest_core.errors import build_error

type JsonScalar = bool | int | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def _validate_canonical_domain(value: object) -> None:
    if isinstance(value, float):
        raise build_error("ERR-BUILD-201")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")  # pragma: no mutate - codec aliases are behaviorally identical
        except UnicodeEncodeError as error:
            raise build_error("ERR-BUILD-201") from error
        return
    if isinstance(value, list):
        for item in value:
            _validate_canonical_domain(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _validate_canonical_domain(item)
        return
    raise build_error("ERR-BUILD-201")


def canonicalize(value: JsonValue) -> bytes:
    """Return RFC 8785 canonical bytes or ERR-BUILD-201 (REQ-F01-030/040)."""
    _validate_canonical_domain(value)
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError, TypeError) as error:
        raise build_error("ERR-BUILD-201") from error
