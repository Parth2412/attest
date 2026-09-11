"""Shared fixtures for the F-01 core-domain conformance suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VECTOR_ROOT = REPOSITORY_ROOT / "spec" / "testvectors"


@pytest.fixture
def valid_statement_data() -> dict[str, Any]:
    """Return a fresh copy of the fully populated normative Statement vector."""
    path = VECTOR_ROOT / "statement-valid" / "input.json"
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return value
