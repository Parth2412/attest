"""Acceptance tests for the Sigstore-native DSSE boundary."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from attest_core import JsonValue, Statement, canonicalize
from attest_sign.dsse import to_sigstore_statement

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "attest_sign"


@pytest.mark.ac("AC-F06-010")
def test_dsse_receives_exact_canonical_statement_bytes(statement: Statement) -> None:
    """REQ-F06-010: Sigstore receives the exact canonical Statement bytes."""
    expected = canonicalize(cast(JsonValue, statement.model_dump()))
    sentinel = object()

    with patch("attest_sign.dsse.SigstoreStatement", return_value=sentinel) as constructor:
        result = to_sigstore_statement(statement)

    constructor.assert_called_once_with(expected)
    assert result is sentinel


@pytest.mark.ac("AC-F06-020")
def test_only_sigstore_owns_dsse_and_pae_construction() -> None:
    """REQ-F06-020: production code calls sign_dsse without alternate DSSE machinery."""
    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in SOURCE_ROOT.glob("*.py")}

    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("securesystemslib") for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("securesystemslib")
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                assert node.name not in {"pae", "_pae"}

    signer_tree = trees[SOURCE_ROOT / "sigstore_signer.py"]
    calls = [
        node.func.attr
        for node in ast.walk(signer_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "sign_dsse" in calls
    assert "pae" not in calls
