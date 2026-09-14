"""Generated policy schema conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]  # AC-F09-020: PyYAML lacks typing metadata
from jsonschema import (  # type: ignore[import-untyped]  # pinned dependency lacks typing metadata
    Draft202012Validator,
    ValidationError,
)

from attest_policy import render_policy_json_schema

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "spec" / "schemas" / "policy-v1.schema.json"


@pytest.mark.ac("AC-F09-020")
def test_generated_policy_schema_is_valid_matches_artifact_and_accepts_example(
    valid_policy_raw: bytes,
) -> None:
    rendered = render_policy_json_schema()
    schema: dict[str, Any] = json.loads(rendered)
    Draft202012Validator.check_schema(schema)
    assert SCHEMA_PATH.read_text(encoding="utf-8") == rendered
    Draft202012Validator(schema).validate(yaml.safe_load(valid_policy_raw))


@pytest.mark.ac("AC-F09-020")
def test_generated_schema_rejects_explicit_null_policy_fields(
    policy_data: dict[str, Any],
) -> None:
    policy_data["policies"][0]["description"] = None

    with pytest.raises(ValidationError):
        Draft202012Validator(json.loads(render_policy_json_schema())).validate(policy_data)
