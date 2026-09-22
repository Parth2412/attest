"""Acceptance tests for RFC 8785 canonicalisation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attest_core.canonical import canonicalize
from attest_core.errors import BuildError

_MISSING_VECTOR_ROOT = "spec/testvectors directory is unavailable"


def _vector_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents):
        candidate = root / "spec" / "testvectors"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(_MISSING_VECTOR_ROOT)


VECTOR_ROOT = _vector_root()


@pytest.mark.ac("AC-F01-030")
@pytest.mark.vectors
def test_jcs_vectors_match_byte_for_byte() -> None:
    """REQ-F01-030: the pinned library matches independently sourced JCS fixtures."""
    cases: list[dict[str, Any]] = json.loads(
        (VECTOR_ROOT / "jcs-canonical" / "cases.json").read_text(encoding="utf-8")
    )
    for case in cases:
        assert canonicalize(case["input"]) == case["expected"].encode("utf-8"), case["name"]


@pytest.mark.ac("AC-F01-040")
@pytest.mark.parametrize(
    "value",
    [
        {"a": 1.5},
        {"nested": [1, {"value": 1.5}]},
        {"nested": [1, {"value": float("nan")}]},
        {"value": float("inf")},
        {"value": float("-inf")},
        {"value": "\udcff"},
        {"\udcff": "surrogate-key"},
        {1: "non-string-key"},
        {"value": object()},
        {"value": 2**53},
    ],
)
def test_noncanonical_values_raise_err_build_201(value: Any) -> None:
    """REQ-F01-040: forbidden numeric and Unicode values fail with one code."""
    with pytest.raises(BuildError) as captured:
        canonicalize(value)
    assert captured.value.code == "ERR-BUILD-201"
