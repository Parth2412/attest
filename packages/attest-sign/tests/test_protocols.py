"""Acceptance tests for the public F-06 signing contract."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from attest_core import Statement
from attest_sign import Bundle, Signer, SigningEnvironment, SigstoreSigner
from attest_sign.errors import SignError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.ac("AC-F06-070")
def test_signing_environment_is_explicit_and_reportable() -> None:
    """REQ-F06-070: the concrete signer has no implicit environment."""
    parameters = inspect.signature(SigstoreSigner).parameters

    assert parameters["environment"].default is inspect.Parameter.empty
    assert parameters["attempt_timeout"].default == timedelta(seconds=120)
    assert {item.value for item in SigningEnvironment} == {"production", "staging"}

    with pytest.raises(SignError) as captured:
        SigstoreSigner(environment=cast(SigningEnvironment, "staging"))
    assert captured.value.code == "ERR-SIGN-306"


@pytest.mark.ac("AC-F06-090")
def test_public_signing_api_is_keyless_only() -> None:
    """REQ-F06-090: no key, key-path, or token input exists in the public API."""
    constructor_parameters = set(inspect.signature(SigstoreSigner).parameters)
    sign_parameters = set(inspect.signature(SigstoreSigner.sign).parameters)
    protocol_parameters = set(inspect.signature(Signer.sign).parameters)

    assert constructor_parameters == {"environment", "attempt_timeout"}
    assert sign_parameters == {"self", "statement"}
    assert protocol_parameters == {"self", "statement"}


@pytest.mark.ac("AC-F06-110")
def test_bundle_metadata_is_immutable_and_constraint_ready(statement: Statement) -> None:
    """REQ-F06-110: the result carries immutable identity-constraint metadata."""

    class FakeSigner:
        def sign(self, supplied: Statement) -> Bundle:
            assert supplied is statement
            return Bundle(
                raw=b"{}",
                environment=SigningEnvironment.STAGING,
                certificate_identity="https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main",
                certificate_issuer="https://token.actions.githubusercontent.com",
                log_index=7,
                log_integrated_time=None,
            )

    signer: Signer = FakeSigner()
    result = signer.sign(statement)

    assert result.certificate_identity.startswith("https://github.com/")
    assert result.certificate_issuer == "https://token.actions.githubusercontent.com"
    with pytest.raises(FrozenInstanceError):
        result.log_index = 8  # type: ignore[misc]  # intentional immutability probe


def test_timeout_configuration_must_be_positive() -> None:
    """REQ-F06-120: invalid deadlines fail at the public configuration boundary."""
    for timeout in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(SignError) as captured:
            SigstoreSigner(
                environment=SigningEnvironment.STAGING,
                attempt_timeout=timeout,
            )
        assert captured.value.code == "ERR-SIGN-306"


@pytest.mark.ac("AC-F06-070")
def test_live_signing_tests_and_workflow_are_staging_only() -> None:
    """REQ-F06-070: executable tests cannot configure production signing."""
    test_root = REPOSITORY_ROOT / "packages" / "attest-sign" / "tests"
    for path in test_root.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "PRODUCTION", path

    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "e2e-sign.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "id-token: write" in workflow
    assert "ATTEST_SIGSTORE_E2E=1" in workflow

    executable_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in [*test_root.glob("test_*.py"), workflow_path]
    )
    production_domain_suffix = "." + "sigstore.dev"
    assert production_domain_suffix not in executable_sources
