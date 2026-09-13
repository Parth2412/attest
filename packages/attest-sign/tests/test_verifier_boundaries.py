"""Static security-boundary tests for F-08 verification."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from attest_sign import verify

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SIGN_SOURCE = REPOSITORY_ROOT / "packages" / "attest-sign" / "src" / "attest_sign"


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


@pytest.mark.ac("AC-F08-040")
def test_identity_constraint_is_required_and_no_bypass_surface_exists() -> None:
    """REQ-F08-040: verification has no identity omission or bypass surface."""
    signature = inspect.signature(verify)
    assert signature.parameters["constraint"].default is inspect.Parameter.empty
    assert signature.parameters["trust_root"].default is inspect.Parameter.empty

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPOSITORY_ROOT / "packages").rglob("*.py"))
    ).lower()
    forbidden = (
        "skip" + "-identity",
        "skip" + "_identity",
        "unsafe" + "-no-op",
        "unsafe" + "noop",
        "allow" + "-any-identity",
        "allow" + "_any_identity",
    )
    assert all(token not in source for token in forbidden)


@pytest.mark.ac("AC-F08-130")
def test_signer_and_verifier_share_no_non_core_module() -> None:
    """REQ-F08-130: signer and verifier have independent adapter paths."""
    verifier_modules = {
        "attest_sign.verifier",
        "attest_sign.trustroot",
        "attest_sign.repository",
        "attest_sign.verify_errors",
    }
    signer_modules = {
        "attest_sign.sigstore_signer",
        "attest_sign.dsse",
        "attest_sign.errors",
        "attest_sign.protocols",
    }
    verifier_imports = set().union(
        *(_imports(SIGN_SOURCE / f"{name.rsplit('.', 1)[1]}.py") for name in verifier_modules)
    )
    signer_imports = set().union(
        *(_imports(SIGN_SOURCE / f"{name.rsplit('.', 1)[1]}.py") for name in signer_modules)
    )

    assert verifier_imports.isdisjoint(signer_modules)
    assert signer_imports.isdisjoint(verifier_modules)
