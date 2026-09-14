"""Stable policy diagnostics governed by BRD-F09."""

from __future__ import annotations

from typing import Final, Literal

PolicyErrorCode = Literal[
    "ERR-POLICY-601",
    "ERR-POLICY-602",
    "ERR-POLICY-603",
    "ERR-POLICY-604",
    "ERR-POLICY-610",
]

_ERROR_DETAILS: Final[dict[PolicyErrorCode, tuple[str, str]]] = {
    "ERR-POLICY-601": (
        "Policy input is unsafe, malformed, ambiguous, or exceeds a resource limit",
        "Correct the policy using the version 1 closed vocabulary",
    ),
    "ERR-POLICY-602": (
        "Policy version is unsupported",
        "Use policy version 1 or upgrade attest",
    ),
    "ERR-POLICY-603": (
        "The explicitly configured policy source is unavailable",
        "Check the configured path and its permissions",
    ),
    "ERR-POLICY-604": (
        "Policy context or verification input is inconsistent",
        "Supply the validated target, complete ordered paths, and one coherent verification view",
    ),
    "ERR-POLICY-610": (
        "A blocking policy was violated",
        "Address the reported failed policy predicates",
    ),
}


class PolicyError(ValueError):
    """Expose a stable code and remediation without policy content (REQ-F09-090)."""

    code: PolicyErrorCode
    message: str
    remediation: str

    def __init__(self, *, code: PolicyErrorCode, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def policy_error(code: PolicyErrorCode) -> PolicyError:
    """Create the coded policy error identified by ``code``."""
    message, remediation = _ERROR_DETAILS[code]
    return PolicyError(code=code, message=message, remediation=remediation)
