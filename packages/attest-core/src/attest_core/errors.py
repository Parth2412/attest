"""Coded domain errors governed by GLOSS-001 §6 and BRD-F01."""

from __future__ import annotations

from typing import Final

_ERROR_DETAILS: Final[dict[str, tuple[str, str]]] = {
    "ERR-BUILD-201": (
        "Value cannot be represented by the canonical JSON profile",
        "Use JSON integers and UTF-8-representable strings; report collector output as a bug",
    ),
    "ERR-BUILD-202": (
        "Git object ID must contain exactly 40 lowercase hexadecimal characters",
        "Supply the full 40-character Git object ID",
    ),
    "ERR-BUILD-203": (
        "Statement subject digest does not match the predicate ChangeSet digest",
        "Rebuild the Statement from a single ChangeSet Record",
    ),
    "ERR-BUILD-204": (
        "A closed enumeration contains an unknown value",
        "Upgrade attest or file an issue for the new value",
    ),
    "ERR-BUILD-205": (
        "Predicate schema version is unsupported",
        "Use predicate version 0.1 or upgrade attest",
    ),
}


class BuildError(ValueError):
    """Represent an F-01 build failure with REQ-F01-150 diagnostics."""

    code: str
    message: str
    remediation: str

    def __init__(self, *, code: str, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def build_error(code: str) -> BuildError:
    """Create the BRD-F01 error identified by ``code`` (REQ-F01-150)."""
    message, remediation = _ERROR_DETAILS[code]
    return BuildError(code=code, message=message, remediation=remediation)
