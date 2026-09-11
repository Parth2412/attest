"""Acceptance test for the pure attest-core import boundary."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parents[1] / "src" / "attest_core"
FORBIDDEN_ROOTS = {
    "attest_cli",
    "attest_collect",
    "attest_export",
    "attest_policy",
    "attest_sign",
    "attest_store",
    "httpx",
    "os",
    "pygit2",
    "sigstore",
}


@pytest.mark.ac("AC-F01-140")
def test_core_imports_no_io_or_sibling_packages() -> None:
    """REQ-F01-140: static imports preserve the pure core boundary."""
    violations: list[str] = []
    for path in sorted(CORE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            line_number: int | None = None
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                line_number = node.lineno
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names = [node.module]
                line_number = node.lineno
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN_ROOTS:
                    assert line_number is not None
                    violations.append(f"{path.relative_to(CORE_ROOT)}:{line_number}:{name}")
    assert violations == []
