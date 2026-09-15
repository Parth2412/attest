"""Acceptance tests for F-08 parse-only Bundle inspection."""

from __future__ import annotations

import base64
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from attest_core import Statement
from attest_policy import VerificationView
from attest_sign import InspectionResult, inspect_bundle
from attest_sign import verifier as module

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "f08"
CHECK_NAMES = [
    "bundle-structure",
    "statement-payload",
    "structural-schema",
    "semantic-model",
]


def _fixture(name: str = "historical-v0.1-trusted.sigstore.json") -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _wire(raw: bytes | None = None) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(raw or _fixture())
    return value


def _render(wire: dict[str, Any]) -> bytes:
    return json.dumps(wire, separators=(",", ":")).encode()


@pytest.mark.ac("AC-F08-170")
def test_valid_bundle_inspects_as_unverified_identity() -> None:
    """REQ-F08-170: parse-only success is explicit and lists four ordered checks."""
    result = inspect_bundle(_fixture())

    assert isinstance(result, InspectionResult)
    assert result.status == "unverified-identity"
    assert [check.name for check in result.checks] == CHECK_NAMES
    assert [check.result for check in result.checks] == ["passed"] * 4
    assert all(check.code is None for check in result.checks)
    assert isinstance(result.statement, Statement)
    assert result.failure_code is None


@pytest.mark.ac("AC-F08-170")
def test_signature_tampering_does_not_turn_inspection_into_verification() -> None:
    """REQ-F08-170: structurally valid signature bytes are not cryptographically checked."""
    wire = _wire()
    wire["dsseEnvelope"]["signatures"][0]["sig"] = base64.b64encode(bytes(64)).decode()

    result = inspect_bundle(_render(wire))

    assert result.status == "unverified-identity"
    assert result.failure_code is None
    assert isinstance(result.statement, Statement)


@pytest.mark.ac("AC-F08-170")
@pytest.mark.parametrize(
    ("fixture_name", "failure_code", "attempted_checks"),
    [
        ("unknown-predicate.sigstore.json", "ERR-VERIFY-007", CHECK_NAMES[:2]),
        ("structural-extra-field.sigstore.json", "ERR-VERIFY-008", CHECK_NAMES[:3]),
        ("semantic-digest-mismatch.sigstore.json", "ERR-VERIFY-009", CHECK_NAMES),
    ],
)
def test_inspection_stops_at_the_exact_payload_schema_or_model_failure(
    fixture_name: str,
    failure_code: str,
    attempted_checks: list[str],
) -> None:
    """REQ-F08-170: parsing failures retain deterministic check order and codes."""
    result = inspect_bundle(_fixture(fixture_name))

    assert result.status == "failed"
    assert [check.name for check in result.checks] == attempted_checks
    assert [check.result for check in result.checks[:-1]] == ["passed"] * (len(result.checks) - 1)
    assert result.checks[-1].result == "failed"
    assert result.checks[-1].code == failure_code
    assert result.statement is None
    assert result.failure_code == failure_code


@pytest.mark.ac("AC-F08-170")
@pytest.mark.parametrize("raw", [b"{", b"[]", b"{}"])
def test_malformed_bundle_fails_the_first_inspection_check(raw: bytes) -> None:
    """REQ-F08-170: malformed Bundle input stops at the structure boundary."""
    result = inspect_bundle(raw)

    assert result.status == "failed"
    assert [(check.name, check.result, check.code) for check in result.checks] == [
        ("bundle-structure", "failed", "ERR-VERIFY-001")
    ]
    assert result.statement is None
    assert result.failure_code == "ERR-VERIFY-001"


@pytest.mark.ac("AC-F08-170")
@pytest.mark.parametrize(
    "wire",
    [
        [],
        {"dsseEnvelope": []},
        {"dsseEnvelope": {}},
        {"dsseEnvelope": {"payloadType": 3, "payload": "e30="}},
        {"dsseEnvelope": {"payloadType": "application/vnd.in-toto+json", "payload": 3}},
        {"dsseEnvelope": {"payloadType": "application/vnd.in-toto+json", "payload": "%%%"}},
    ],
)
def test_malformed_dsse_payload_shape_remains_a_bundle_failure(
    monkeypatch: pytest.MonkeyPatch,
    wire: object,
) -> None:
    """REQ-F08-170: malformed envelope encoding never reaches Statement parsing."""

    def parsed(raw: bytes) -> object:
        del raw
        return object()

    monkeypatch.setattr(module, "_parse_bundle", parsed)

    result = inspect_bundle(json.dumps(wire).encode())

    assert result.failure_code == "ERR-VERIFY-001"
    assert [check.name for check in result.checks] == ["bundle-structure"]


@pytest.mark.ac("AC-F08-170")
def test_inspection_has_no_verification_inputs_or_sigstore_verifier_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F08-170: inspection cannot select trust or invoke identity verification."""
    signature = inspect.signature(inspect_bundle)
    assert list(signature.parameters) == ["bundle"]

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError

    monkeypatch.setattr(module, "load_verifier", forbidden)
    monkeypatch.setattr(module, "Identity", forbidden)

    result = inspect_bundle(_fixture())

    assert result.status == "unverified-identity"


@pytest.mark.ac("AC-F08-170")
def test_inspection_result_cannot_satisfy_policy_verification_view() -> None:
    """REQ-F08-170: parse-only output lacks every trusted policy-evidence field."""
    result = inspect_bundle(_fixture())
    required_members = set(VerificationView.__annotations__)

    assert {"verified_identity", "verified_issuer", "transparency_log_verified"} <= (
        required_members
    )
    assert not all(hasattr(result, member) for member in required_members)
    assert not hasattr(result, "verified_identity")
    assert not hasattr(result, "verified_issuer")
    assert not hasattr(result, "transparency_log_verified")
