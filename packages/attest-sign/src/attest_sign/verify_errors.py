"""Stable, secret-safe verification diagnostics governed by BRD-F08."""

from __future__ import annotations

from typing import Final, Literal

VerifyErrorCode = Literal[
    "ERR-VERIFY-001",
    "ERR-VERIFY-007",
    "ERR-VERIFY-008",
    "ERR-VERIFY-009",
    "ERR-VERIFY-010",
    "ERR-VERIFY-011",
    "ERR-VERIFY-012",
    "ERR-VERIFY-013",
]

_ERROR_DETAILS: Final[dict[VerifyErrorCode, tuple[str, str]]] = {
    "ERR-VERIFY-001": (
        "The Sigstore bundle is malformed or incomplete",
        "Supply a complete parseable Sigstore bundle",
    ),
    "ERR-VERIFY-007": (
        "The verified DSSE payload is not a supported attest Statement",
        "Use a supported attest predicate version and in-toto payload type",
    ),
    "ERR-VERIFY-008": (
        "The verified Statement failed its versioned structural schema",
        "Reject the attestation and obtain a structurally valid bundle",
    ),
    "ERR-VERIFY-009": (
        "The verified Statement failed semantic validation",
        "Reject the attestation and obtain a semantically valid bundle",
    ),
    "ERR-VERIFY-010": (
        "Repository ChangeSet recomputation failed or did not match",
        "Check the repository and caller-selected base and head revisions",
    ),
    "ERR-VERIFY-011": (
        "The identity constraint is invalid",
        "Supply a non-empty exact issuer and an exact identity or bounded workflow glob",
    ),
    "ERR-VERIFY-012": (
        "The selected Sigstore trust material is unavailable or invalid",
        "Refresh the selected environment explicitly or supply valid trust configuration JSON",
    ),
    "ERR-VERIFY-013": (
        "Sigstore cryptographic verification failed",
        "Reject the bundle and inspect the signer and trust configuration",
    ),
}


class VerifyError(ValueError):
    """Represent a coded public verification configuration failure."""

    code: VerifyErrorCode
    message: str
    remediation: str

    def __init__(self, *, code: VerifyErrorCode, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def verify_error(code: VerifyErrorCode) -> VerifyError:
    """Create a stable verification error without upstream diagnostic material."""
    message, remediation = _ERROR_DETAILS[code]
    return VerifyError(code=code, message=message, remediation=remediation)
