"""Shared fixtures for BRD-F06 signing acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attest_core import Statement

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def statement(valid_statement_data: dict[str, Any]) -> Statement:
    """Return a fully populated, semantically valid Statement."""
    return Statement.model_validate(valid_statement_data)


@pytest.fixture
def valid_statement_data() -> dict[str, Any]:
    """Load a fresh copy of the normative valid Statement vector."""
    path = REPOSITORY_ROOT / "spec" / "testvectors" / "statement-valid" / "input.json"
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return value
