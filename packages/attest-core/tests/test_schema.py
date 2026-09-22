"""Acceptance tests for generated structural schema and runtime semantics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import (  # type: ignore[import-untyped]  # REQ-F01-120: pinned package lacks typing metadata
    Draft202012Validator,
    FormatChecker,
)
from pydantic import ValidationError

from attest_core.errors import BuildError
from attest_core.models import Statement
from attest_core.schema import generate_json_schema, render_json_schema

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VECTOR_ROOT = REPOSITORY_ROOT / "spec" / "testvectors"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_operation(base: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    value = cast(dict[str, Any], json.loads(json.dumps(base)))
    operations = case.get("operations", [case])
    for operation_case in operations:
        path: list[str | int] = operation_case["path"]
        parent: Any = value
        for part in path[:-1]:
            parent = parent[part]
        operation = operation_case["operation"]
        if operation == "remove":
            del parent[path[-1]]
        elif operation == "append-copy":
            target = parent[path[-1]]
            target.append(json.loads(json.dumps(target[operation_case["index"]])))
        else:
            parent[path[-1]] = operation_case["value"]
    return value


def _validator() -> Draft202012Validator:
    schema = generate_json_schema("0.1")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _coded_context(error: ValidationError) -> BuildError | None:
    for item in error.errors(include_url=False):
        context_error = item.get("ctx", {}).get("error")
        if isinstance(context_error, BuildError):
            return context_error
    return None


@pytest.mark.ac("AC-F01-120")
@pytest.mark.vectors
def test_generated_schema_and_runtime_validate_normative_statement_vectors() -> None:
    """REQ-F01-120: structural and semantic validation have explicit boundaries."""
    valid = _load_json(VECTOR_ROOT / "statement-valid" / "input.json")
    validator = _validator()
    validator.validate(valid)
    Statement.model_validate(valid)

    schema_cases: list[dict[str, Any]] = _load_json(
        VECTOR_ROOT / "statement-invalid-schema-cases" / "cases.json"
    )
    for case in schema_cases:
        invalid = _apply_operation(valid, case)
        schema_errors = list(validator.iter_errors(invalid))
        assert schema_errors, case["name"]
        with pytest.raises(ValidationError):
            Statement.model_validate(invalid)

    semantic_cases: list[dict[str, Any]] = _load_json(
        VECTOR_ROOT / "statement-invalid-semantic-cases" / "cases.json"
    )
    for case in semantic_cases:
        invalid = _apply_operation(valid, case)
        validator.validate(invalid)
        with pytest.raises(ValidationError) as semantic_capture:
            Statement.model_validate(invalid)
        expected_code = case.get("errorCode")
        if expected_code is not None:
            coded_error = _coded_context(semantic_capture.value)
            assert coded_error is not None, case["name"]
            assert coded_error.code == expected_code, case["name"]

    with pytest.raises(BuildError) as build_capture:
        generate_json_schema("0.2")
    assert build_capture.value.code == "ERR-BUILD-205"


@pytest.mark.ac("AC-F01-130")
def test_committed_schema_matches_deterministic_renderer() -> None:
    """REQ-F01-130: the committed schema is exactly generated output."""
    path = REPOSITORY_ROOT / "spec" / "schemas" / "ai-authorship-v0.1.schema.json"
    assert path.read_text(encoding="utf-8") == render_json_schema("0.1")
