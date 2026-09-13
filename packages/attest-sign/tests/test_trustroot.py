"""Acceptance tests for explicit F-08 trust-root selection."""

from __future__ import annotations

from typing import ClassVar, cast

import pytest

from attest_sign import (
    ServiceTrustRoot,
    SuppliedTrustRoot,
    VerificationEnvironment,
)
from attest_sign import trustroot as module


class _FakeVerifier:
    production_calls: ClassVar[list[bool]] = []
    staging_calls: ClassVar[list[bool]] = []

    def __init__(self, *, trusted_root: object) -> None:
        self.trusted_root = trusted_root

    @classmethod
    def production(cls, *, offline: bool = False) -> _FakeVerifier:
        cls.production_calls.append(offline)
        return cls(trusted_root="production")

    @classmethod
    def staging(cls, *, offline: bool = False) -> _FakeVerifier:
        cls.staging_calls.append(offline)
        return cls(trusted_root="staging")


@pytest.mark.ac("AC-F08-080")
def test_service_root_uses_only_the_selected_environment_and_explicit_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F08-080: environment roots are neither inferred nor retried."""
    monkeypatch.setattr(module, "Verifier", _FakeVerifier)
    _FakeVerifier.production_calls = []
    _FakeVerifier.staging_calls = []

    production = module.load_verifier(
        ServiceTrustRoot(VerificationEnvironment("production"), False)
    )
    staging = module.load_verifier(ServiceTrustRoot(VerificationEnvironment.STAGING, True))

    assert cast(_FakeVerifier, production).trusted_root == "production"
    assert cast(_FakeVerifier, staging).trusted_root == "staging"
    assert _FakeVerifier.production_calls == [False]
    assert _FakeVerifier.staging_calls == [True]


@pytest.mark.ac("AC-F08-080")
def test_supplied_client_trust_json_uses_public_parser_without_service_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F08-080: caller-supplied material is parsed exactly once and locally."""
    observed: list[str] = []

    class FakeClientTrustConfig:
        trusted_root = "supplied-root"

        @classmethod
        def from_json(cls, raw: str) -> FakeClientTrustConfig:
            observed.append(raw)
            return cls()

    monkeypatch.setattr(module, "ClientTrustConfig", FakeClientTrustConfig)
    monkeypatch.setattr(module, "Verifier", _FakeVerifier)
    _FakeVerifier.production_calls = []
    _FakeVerifier.staging_calls = []

    verifier = module.load_verifier(SuppliedTrustRoot('{"trustedRoot":{}}'))

    assert cast(_FakeVerifier, verifier).trusted_root == "supplied-root"
    assert observed == ['{"trustedRoot":{}}']
    assert _FakeVerifier.production_calls == []
    assert _FakeVerifier.staging_calls == []
