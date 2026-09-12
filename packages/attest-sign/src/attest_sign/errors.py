"""Stable, secret-safe signing diagnostics governed by BRD-F06."""

from __future__ import annotations

from typing import Final, Literal

SignErrorCode = Literal[
    "ERR-SIGN-301",
    "ERR-SIGN-302",
    "ERR-SIGN-303",
    "ERR-SIGN-304",
    "ERR-SIGN-305",
    "ERR-SIGN-306",
]

_ERROR_DETAILS: Final[dict[SignErrorCode, tuple[str, str]]] = {
    "ERR-SIGN-301": (
        "No ambient signing identity is available",
        "Add permissions: id-token: write to the workflow",
    ),
    "ERR-SIGN-302": (
        "Fulcio certificate request failed",
        "Check network access and the OIDC audience configuration",
    ),
    "ERR-SIGN-303": (
        "Transparency log submission failed",
        "Retry the workflow; do not disable transparency log submission",
    ),
    "ERR-SIGN-304": (
        "The signing attempt exceeded its hard deadline",
        "Check egress and proxy configuration",
    ),
    "ERR-SIGN-305": (
        "The produced bundle failed required-material validation",
        "Report this as a bug and do not use the produced bundle",
    ),
    "ERR-SIGN-306": (
        "Sigstore trust root or signing configuration could not be initialized",
        "Check the selected environment, trusted metadata cache, and network access",
    ),
}


class SignError(RuntimeError):
    """Represent one secret-safe public-operation failure (REQ-F06-130)."""

    code: SignErrorCode
    message: str
    remediation: str

    def __init__(self, *, code: SignErrorCode, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def sign_error(code: SignErrorCode) -> SignError:
    """Create a secret-safe error by stable project code (REQ-F06-130)."""
    message, remediation = _ERROR_DETAILS[code]
    return SignError(code=code, message=message, remediation=remediation)
