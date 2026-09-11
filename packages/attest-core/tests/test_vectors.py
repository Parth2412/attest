"""Inventory tests for the normative F-01 vector corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

VECTOR_ROOT = Path(__file__).resolve().parents[3] / "spec" / "testvectors"
REQUIRED_VECTORS = {
    "csd1-empty",
    "csd1-mode-change",
    "csd1-modify-delete",
    "csd1-path-ordering",
    "csd1-rebase-stability",
    "csd1-rename",
    "csd1-single-add",
    "csd1-squash-stability",
    "csd1-submodule",
    "csd1-symlink",
    "csd1-unicode-paths",
    "jcs-canonical",
    "statement-invalid-schema-cases",
    "statement-invalid-semantic-cases",
    "statement-valid",
}


@pytest.mark.ac("AC-F01-160")
@pytest.mark.vectors
@pytest.mark.parametrize("name", sorted(REQUIRED_VECTORS))
def test_every_required_vector_directory_contains_real_fixtures(name: str) -> None:
    """REQ-F01-160: placeholders cannot satisfy the normative vector inventory."""
    path = VECTOR_ROOT / name
    assert path.is_dir()
    assert any(item.is_file() and item.name != ".gitkeep" for item in path.iterdir())


@pytest.mark.ac("AC-F01-160")
@pytest.mark.vectors
def test_structural_and_semantic_invalid_vector_classes_exist() -> None:
    """REQ-F01-160: both ADR-021 invalid-vector classes are populated."""
    assert list(VECTOR_ROOT.glob("statement-invalid-schema-*"))
    assert list(VECTOR_ROOT.glob("statement-invalid-semantic-*"))
