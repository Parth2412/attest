"""Workspace packaging smoke test required by BOOT-001 and ADR-023."""

import importlib

import pytest

WORKSPACE_MODULES = (
    "attest_core",
    "attest_collect",
    "attest_sign",
    "attest_store",
    "attest_policy",
    "attest_export",
    "attest_cli",
)


@pytest.mark.parametrize("module_name", WORKSPACE_MODULES)
def test_workspace_package_imports(module_name: str) -> None:
    """Every declared workspace distribution must expose its import package."""
    assert importlib.import_module(module_name).__name__ == module_name
