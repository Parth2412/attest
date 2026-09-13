"""Real-bundle offline and historical acceptance tests for F-08."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never

import pytest
import requests
from sigstore.models import Bundle as SigstoreBundle

from attest_sign import (
    IdentityConstraint,
    ServiceTrustRoot,
    SuppliedTrustRoot,
    VerificationEnvironment,
    verify,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "f08"


class NetworkAttemptError(AssertionError):
    def __init__(self) -> None:
        super().__init__("verification attempted network access")


def _manifest() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return value


def _constraint() -> IdentityConstraint:
    manifest = _manifest()
    return IdentityConstraint(manifest["identity"], manifest["issuer"])


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _deny_network(*args: object, **kwargs: object) -> Never:
    del args, kwargs
    raise NetworkAttemptError


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests.sessions.Session, "request", _deny_network)


@pytest.mark.ac("AC-F08-030")
@pytest.mark.ac("AC-F08-150")
def test_earliest_bundle_verifies_after_certificate_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F08-030/150: verified bundle time, not wall clock, establishes validity."""
    raw = _fixture("historical-v0.1-trusted.sigstore.json")
    parsed = SigstoreBundle.from_json(raw)
    assert datetime.now(UTC) > parsed.signing_certificate.not_valid_after_utc
    _block_network(monkeypatch)

    result = verify(
        raw,
        _constraint(),
        SuppliedTrustRoot((FIXTURE_ROOT / "client-trust-config.json").read_text()),
    )

    assert result.status == "verified"
    assert result.failure_code is None
    assert result.statement is not None
    assert result.statement.predicate_type.endswith("/v0.1")


@pytest.mark.ac("AC-F08-080")
def test_real_bundle_verifies_offline_with_cached_and_supplied_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F08-080: both explicit offline trust sources need no service access."""
    raw = _fixture("historical-v0.1-trusted.sigstore.json")
    _block_network(monkeypatch)

    cached = verify(
        raw,
        _constraint(),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )
    supplied = verify(
        raw,
        _constraint(),
        SuppliedTrustRoot((FIXTURE_ROOT / "client-trust-config.json").read_text()),
    )
    wrong_environment = verify(
        raw,
        _constraint(),
        ServiceTrustRoot(VerificationEnvironment("production"), True),
    )

    assert cached.status == "verified"
    assert supplied.status == "verified"
    assert wrong_environment.status == "failed"
    assert wrong_environment.failure_code == "ERR-VERIFY-013"


@pytest.mark.ac("AC-F08-150")
def test_fixture_manifest_pins_provenance_and_exact_content_hashes() -> None:
    """REQ-F08-150: historical evidence is immutable and source-attributed."""
    manifest = _manifest()
    assert manifest["sigstoreVersion"] == "4.5.0"
    assert manifest["sourceRun"].startswith("https://github.com/Parth2412/attest/actions/runs/")
    assert len(manifest["sourceCommit"]) == 40
    for name, metadata in manifest["files"].items():
        assert hashlib.sha256(_fixture(name)).hexdigest() == metadata["sha256"]
