"""Atomic, identity-constrained Sigstore verification governed by BRD-F08."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Literal, cast

from cryptography.x509 import SubjectAlternativeName, UniformResourceIdentifier
from sigstore.models import Bundle as _SigstoreBundle
from sigstore.verify.policy import Identity

from attest_core import Statement, identity_pattern_matches, validate_identity_pattern
from attest_core import validate_statement_structure as _validate_statement_structure
from attest_core.constants import DSSE_PAYLOAD_TYPE, PREDICATE_TYPE_V0_1
from attest_sign.repository import (
    RepositoryConstraint,
    recompute_changeset_digest,
)
from attest_sign.trustroot import TrustRootSource, load_verifier
from attest_sign.verify_errors import VerifyErrorCode, verify_error

CheckName = Literal[
    "bundle-structure",
    "sigstore-dsse",
    "statement-payload",
    "structural-schema",
    "semantic-model",
    "changeset-recomputation",
]
CheckResult = Literal["passed", "failed", "skipped"]
VerificationStatus = Literal["verified", "verified-untrusted-environment", "failed"]

_CHECK_NAMES: Final[tuple[CheckName, ...]] = (
    "bundle-structure",
    "sigstore-dsse",
    "statement-payload",
    "structural-schema",
    "semantic-model",
    "changeset-recomputation",
)
_PREDICATE_REGISTRY: dict[str, tuple[str, type[Statement]]] = {
    PREDICATE_TYPE_V0_1: ("0.1", Statement),
}


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


@dataclass(frozen=True, slots=True)
class IdentityConstraint:
    """Require an exact issuer and exact or bounded identity (REQ-F08-040/050/060)."""

    identity_pattern: str
    issuer: str

    def __post_init__(self) -> None:
        if not _is_nonempty_string(self.issuer):
            raise verify_error("ERR-VERIFY-011")
        try:
            validate_identity_pattern(self.identity_pattern)
        except ValueError:
            raise verify_error("ERR-VERIFY-011") from None


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """Record one attempted verification step (REQ-F08-020)."""

    name: CheckName
    result: CheckResult
    code: VerifyErrorCode | None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Return an ordered, sanitized verification decision (REQ-F08-020/120/140)."""

    status: VerificationStatus
    checks: list[CheckOutcome]
    statement: Statement | None
    failure_code: VerifyErrorCode | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: bool


class _MalformedBundleError(ValueError):
    """Signal preflight structure that is not a Sigstore bundle."""


class _MissingInclusionProofError(ValueError):
    """Preserve the normative step-2 classification for an omitted proof."""


class _InvalidStatementPayloadError(ValueError):
    """Signal a non-attest or unsupported verified payload."""


def _passed(name: CheckName) -> CheckOutcome:
    return CheckOutcome(name=name, result="passed", code=None)


def _failed(name: CheckName, code: VerifyErrorCode) -> CheckOutcome:
    return CheckOutcome(name=name, result="failed", code=code)


def _failure(
    checks: list[CheckOutcome],
    name: CheckName,
    code: VerifyErrorCode,
) -> VerificationResult:
    return VerificationResult(
        status="failed",
        checks=[*checks, _failed(name, code)],
        statement=None,
        failure_code=code,
        verified_identity=None,
        verified_issuer=None,
        transparency_log_verified=False,
    )


def _parse_bundle(raw: bytes) -> _SigstoreBundle:
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict):
        raise _MalformedBundleError
    wire = cast(dict[str, object], decoded)  # pragma: no mutate - cast is runtime-neutral
    envelope = wire.get("dsseEnvelope")
    material = wire.get("verificationMaterial")
    if not isinstance(envelope, dict) or not isinstance(material, dict):
        raise _MalformedBundleError
    if "certificate" not in material and "x509CertificateChain" not in material:
        raise _MalformedBundleError
    entries = material.get("tlogEntries")
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise _MalformedBundleError
    if "inclusionProof" not in entries[0]:
        raise _MissingInclusionProofError
    return _SigstoreBundle.from_json(raw)


def _exact_identity(bundle: _SigstoreBundle, constraint: IdentityConstraint) -> str:
    if "*" not in constraint.identity_pattern:
        return constraint.identity_pattern
    extension = bundle.signing_certificate.extensions.get_extension_for_class(
        SubjectAlternativeName
    )
    identities = extension.value.get_values_for_type(UniformResourceIdentifier)
    matches = [
        identity
        for identity in identities
        if identity_pattern_matches(constraint.identity_pattern, identity)
    ]
    if len(matches) != 1:
        raise ValueError
    return matches[0]


def _statement_payload(payload_type: str, payload: bytes) -> tuple[dict[str, object], str]:
    if payload_type != DSSE_PAYLOAD_TYPE:
        raise _InvalidStatementPayloadError
    decoded: object = json.loads(payload)
    if not isinstance(decoded, dict):
        raise _InvalidStatementPayloadError
    value = cast(dict[str, object], decoded)  # pragma: no mutate - cast is runtime-neutral
    predicate_type = value.get("predicateType")
    if not isinstance(predicate_type, str) or predicate_type not in _PREDICATE_REGISTRY:
        raise _InvalidStatementPayloadError
    return value, predicate_type


def verify(
    bundle: bytes,
    constraint: IdentityConstraint,
    trust_root: TrustRootSource,
    repository: RepositoryConstraint | None = None,
) -> VerificationResult:
    """Run six identity-bound checks and stop at first failure (REQ-F08-010 through 150)."""
    if not isinstance(constraint, IdentityConstraint):
        raise verify_error("ERR-VERIFY-011")
    checks: list[CheckOutcome] = []
    try:
        parsed_bundle = _parse_bundle(bundle)
    except _MissingInclusionProofError:
        checks.append(_passed(_CHECK_NAMES[0]))
        return _failure(checks, _CHECK_NAMES[1], "ERR-VERIFY-013")
    except Exception:
        return _failure(checks, _CHECK_NAMES[0], "ERR-VERIFY-001")
    checks.append(_passed(_CHECK_NAMES[0]))

    try:
        sigstore_verifier = load_verifier(trust_root)
    except Exception:
        return _failure(checks, _CHECK_NAMES[1], "ERR-VERIFY-012")
    try:
        exact_identity = _exact_identity(parsed_bundle, constraint)
        policy = Identity(identity=exact_identity, issuer=constraint.issuer)
        payload_type, payload = sigstore_verifier.verify_dsse(parsed_bundle, policy=policy)
    except Exception:
        return _failure(checks, _CHECK_NAMES[1], "ERR-VERIFY-013")
    checks.append(_passed(_CHECK_NAMES[1]))

    try:
        statement_wire, predicate_type = _statement_payload(payload_type, payload)
    except Exception:
        return _failure(checks, _CHECK_NAMES[2], "ERR-VERIFY-007")
    checks.append(_passed(_CHECK_NAMES[2]))

    predicate_version, model_type = _PREDICATE_REGISTRY[predicate_type]
    try:
        _validate_statement_structure(statement_wire, predicate_version)
    except Exception:
        return _failure(checks, _CHECK_NAMES[3], "ERR-VERIFY-008")
    checks.append(_passed(_CHECK_NAMES[3]))

    try:
        statement = model_type.model_validate(statement_wire)
    except Exception:
        return _failure(checks, _CHECK_NAMES[4], "ERR-VERIFY-009")
    checks.append(_passed(_CHECK_NAMES[4]))

    if repository is None:
        checks.append(CheckOutcome(name=_CHECK_NAMES[5], result="skipped", code=None))
    else:
        try:
            digest = recompute_changeset_digest(repository)
        except Exception:
            return _failure(checks, _CHECK_NAMES[5], "ERR-VERIFY-010")
        if digest != statement.predicate.change_set.digest:
            return _failure(checks, _CHECK_NAMES[5], "ERR-VERIFY-010")
        checks.append(_passed(_CHECK_NAMES[5]))

    status: VerificationStatus = (
        "verified"
        if statement.predicate.collection.environment.trusted
        else "verified-untrusted-environment"
    )
    return VerificationResult(
        status=status,
        checks=checks,
        statement=statement,
        failure_code=None,
        verified_identity=exact_identity,
        verified_issuer=constraint.issuer,
        transparency_log_verified=True,
    )
