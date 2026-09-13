"""Required real-bundle adversarial suite for F-08."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Never, cast

import pytest
import requests
from hypothesis import given, settings
from hypothesis import strategies as st

from attest_sign import (
    IdentityConstraint,
    RepositoryConstraint,
    ServiceTrustRoot,
    SuppliedTrustRoot,
    VerificationEnvironment,
    verify,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "f08"


class NetworkAttemptError(AssertionError):
    def __init__(self) -> None:
        super().__init__("adversarial verification attempted network access")


def _manifest() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return value


def _fixture(name: str = "historical-v0.1-trusted.sigstore.json") -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _trust_root() -> SuppliedTrustRoot:
    return SuppliedTrustRoot((FIXTURE_ROOT / "client-trust-config.json").read_text())


def _constraint(*, identity: str | None = None, issuer: str | None = None) -> IdentityConstraint:
    manifest = _manifest()
    return IdentityConstraint(identity or manifest["identity"], issuer or manifest["issuer"])


def _wire(raw: bytes | None = None) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(raw or _fixture())
    return value


def _render(wire: dict[str, Any]) -> bytes:
    return json.dumps(wire, separators=(",", ":")).encode()


def _payload(wire: dict[str, Any]) -> dict[str, Any]:
    envelope = wire["dsseEnvelope"]
    value: dict[str, Any] = json.loads(base64.b64decode(envelope["payload"]))
    return value


def _replace_payload(wire: dict[str, Any], payload: dict[str, Any]) -> None:
    wire["dsseEnvelope"]["payload"] = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def _deny_network(*args: object, **kwargs: object) -> Never:
    del args, kwargs
    raise NetworkAttemptError


@pytest.fixture(autouse=True)
def _network_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests.sessions.Session, "request", _deny_network)


@pytest.mark.ac("AC-F08-040")
@pytest.mark.adversarial
def test_valid_bundle_from_different_identity_fails_closed() -> None:
    """REQ-F08-040: a genuine signature never bypasses the expected identity."""
    sources = (
        _trust_root(),
        ServiceTrustRoot(VerificationEnvironment.STAGING, True),
    )
    results = [
        verify(
            _fixture(),
            _constraint(identity=_manifest()["identity"] + "-attacker"),
            source,
        )
        for source in sources
    ]

    assert all(result.status == "failed" for result in results)
    assert all(result.failure_code == "ERR-VERIFY-013" for result in results)


@pytest.mark.ac("AC-F08-060")
@pytest.mark.adversarial
def test_near_miss_issuer_reaches_crypto_and_fails() -> None:
    """REQ-F08-060: a nonempty near-miss issuer is matched exactly by Sigstore."""
    result = verify(
        _fixture(),
        _constraint(issuer=_manifest()["issuer"] + "/near-miss"),
        _trust_root(),
    )

    assert result.failure_code == "ERR-VERIFY-013"
    assert [check.name for check in result.checks] == ["bundle-structure", "sigstore-dsse"]


@pytest.mark.ac("AC-F08-070")
@pytest.mark.adversarial
@pytest.mark.parametrize("mode", ["removed", "tampered"])
def test_inclusion_proof_removal_or_tampering_fails_offline(mode: str) -> None:
    """REQ-F08-070: embedded inclusion evidence is mandatory and cryptographic."""
    wire = _wire()
    entry = wire["verificationMaterial"]["tlogEntries"][0]
    if mode == "removed":
        entry.pop("inclusionProof")
    else:
        proof = entry["inclusionProof"]
        root_hash = proof["rootHash"]
        proof["rootHash"] = ("A" if root_hash[0] != "A" else "B") + root_hash[1:]

    result = verify(_render(wire), _constraint(), _trust_root())

    assert result.failure_code == "ERR-VERIFY-013"
    assert result.checks[-1].name == "sigstore-dsse"


@pytest.mark.ac("AC-F08-110")
@pytest.mark.adversarial
def test_valid_bundle_against_different_changeset_fails(
    tmp_path: Path,
) -> None:
    """REQ-F08-110: a genuine bundle cannot validate a different committed diff."""
    subprocess.run(["git", "-C", os.fspath(tmp_path), "init", "-q"], check=True)
    tracked = tmp_path / "different.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", os.fspath(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(tmp_path),
            "-c",
            "user.name=Adversarial Test",
            "-c",
            "user.email=adversarial@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    base = subprocess.run(
        ["git", "-C", os.fspath(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tracked.write_text("head\n", encoding="utf-8")
    subprocess.run(["git", "-C", os.fspath(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(tmp_path),
            "-c",
            "user.name=Adversarial Test",
            "-c",
            "user.email=adversarial@example.invalid",
            "commit",
            "-qm",
            "head",
        ],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", os.fspath(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = verify(
        _fixture(),
        _constraint(),
        _trust_root(),
        RepositoryConstraint(tmp_path, base, head),
    )

    assert result.failure_code == "ERR-VERIFY-010"
    assert result.checks[-1].name == "changeset-recomputation"


@pytest.mark.ac("AC-F08-120")
@pytest.mark.adversarial
def test_valid_untrusted_environment_bundle_is_never_plain_verified() -> None:
    """REQ-F08-120: a genuine local-environment Statement retains lower trust."""
    result = verify(
        _fixture("historical-v0.1-untrusted.sigstore.json"),
        _constraint(),
        _trust_root(),
    )

    assert result.status == "verified-untrusted-environment"
    assert result.failure_code is None


@pytest.mark.adversarial
@pytest.mark.parametrize("case", ["payload", "signature", "subject", "truncated"])
def test_bundle_tampering_cases_fail_with_exact_codes(case: str) -> None:
    """BRD-F08 §7: payload, signature, subject, and truncation attacks fail."""
    raw = _fixture()
    expected = "ERR-VERIFY-013"
    if case == "truncated":
        mutated = raw[: len(raw) // 2]
        expected = "ERR-VERIFY-001"
    else:
        wire = _wire(raw)
        if case == "signature":
            donor = _wire(_fixture("historical-v0.1-untrusted.sigstore.json"))
            wire["dsseEnvelope"]["signatures"] = donor["dsseEnvelope"]["signatures"]
        else:
            payload = _payload(wire)
            if case == "payload":
                payload["predicate"]["collection"]["collector"]["name"] = "modified"
            else:
                payload["subject"][0]["digest"]["sha256"] = "f" * 64
            _replace_payload(wire, payload)
        mutated = _render(wire)

    result = verify(mutated, _constraint(), _trust_root())

    assert result.status == "failed"
    assert result.failure_code == expected


@pytest.mark.adversarial
def test_signed_extra_predicate_field_fails_structural_schema() -> None:
    """BRD-F08 §7: a signed but structurally extended v0.1 payload fails step 4."""
    result = verify(
        _fixture("structural-extra-field.sigstore.json"),
        _constraint(),
        _trust_root(),
    )

    assert result.failure_code == "ERR-VERIFY-008"
    assert result.checks[-1].name == "structural-schema"


@pytest.mark.ac("AC-F08-100")
@pytest.mark.adversarial
def test_signed_digest_mismatch_fails_semantic_model() -> None:
    """REQ-F08-100: a schema-valid digest mismatch reaches and fails step 5."""
    result = verify(
        _fixture("semantic-digest-mismatch.sigstore.json"),
        _constraint(),
        _trust_root(),
    )

    assert result.failure_code == "ERR-VERIFY-009"
    assert result.checks[-1].name == "semantic-model"


@pytest.mark.ac("AC-F08-090")
@pytest.mark.adversarial
def test_signed_unknown_predicate_fails_payload_dispatch() -> None:
    """REQ-F08-090: a genuine signature cannot enable best-effort version parsing."""
    result = verify(
        _fixture("unknown-predicate.sigstore.json"),
        _constraint(),
        _trust_root(),
    )

    assert result.failure_code == "ERR-VERIFY-007"
    assert result.checks[-1].name == "statement-payload"


@pytest.mark.ac("AC-F08-080")
@pytest.mark.adversarial
def test_leaf_certificate_is_rejected_by_an_untrusted_environment_root() -> None:
    """REQ-F08-080: trust roots are selected once and never fall back."""
    result = verify(
        _fixture(),
        _constraint(),
        ServiceTrustRoot(VerificationEnvironment("production"), True),
    )

    assert result.failure_code == "ERR-VERIFY-013"


@pytest.mark.adversarial
@settings(max_examples=20, deadline=None)
@given(st.integers(min_value=0, max_value=63))
def test_payload_base64_mutations_never_verify(position: int) -> None:
    """BRD-F08 §7: mutations across the encoded signed payload fail closed."""
    wire = _wire()
    encoded = cast(str, wire["dsseEnvelope"]["payload"])
    index = position % len(encoded)
    replacement = "A" if encoded[index] != "A" else "B"
    wire["dsseEnvelope"]["payload"] = encoded[:index] + replacement + encoded[index + 1 :]

    result = verify(_render(wire), _constraint(), _trust_root())

    assert result.status == "failed"
