"""Strict JSON decoding for untrusted collector inputs."""

from __future__ import annotations

import json
from typing import Any

_DUPLICATE_PROPERTY = "JSON object contains a duplicate property"
_NON_STANDARD_NUMBER = "JSON contains a non-standard numeric value"


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(_DUPLICATE_PROPERTY)
        value[key] = item
    return value


def _constant(_value: str) -> object:
    raise ValueError(_NON_STANDARD_NUMBER)


def decode_json(text: str) -> object:
    """Decode one standard JSON value while rejecting duplicate object names."""
    value: object = json.loads(
        text,
        object_pairs_hook=_object,
        parse_constant=_constant,
    )
    return value
