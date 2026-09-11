"""Structural JSON Schema generation governed by SPEC-001 §11."""

from __future__ import annotations

import json
from typing import Any, Final

from attest_core.errors import build_error
from attest_core.models.statement import Statement

_SUPPORTED_PREDICATE_VERSION: Final[str] = "0.1"
_DRAFT_2020_12: Final[str] = "https://json-schema.org/draft/2020-12/schema"


def generate_json_schema(predicate_version: str) -> dict[str, object]:
    """Generate the complete Statement schema or ERR-BUILD-205 (REQ-F01-120)."""
    if predicate_version != _SUPPORTED_PREDICATE_VERSION:
        raise build_error("ERR-BUILD-205")
    generated: dict[str, Any] = Statement.model_json_schema(by_alias=True, mode="validation")
    return {"$schema": _DRAFT_2020_12, **generated}


def render_json_schema(predicate_version: str) -> str:
    """Render deterministic generated schema text for drift checks (REQ-F01-130)."""
    return json.dumps(generate_json_schema(predicate_version), indent=2, sort_keys=True) + "\n"
