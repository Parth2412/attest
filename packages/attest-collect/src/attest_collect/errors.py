"""Stable public collector errors governed by BRD-F02 and ADR-033."""

from __future__ import annotations

from typing import Final, Literal

CollectErrorCode = Literal[
    "ERR-COLLECT-101",
    "ERR-COLLECT-102",
    "ERR-COLLECT-103",
    "ERR-COLLECT-104",
    "ERR-COLLECT-105",
    "ERR-COLLECT-106",
]

_ERROR_DETAILS: Final[dict[CollectErrorCode, tuple[str, str]]] = {
    "ERR-COLLECT-101": (
        "The selected diff-base commit is unavailable in this shallow repository",
        "Set fetch-depth: 0 in the checkout configuration and retry",
    ),
    "ERR-COLLECT-102": (
        "The supplied path is not a Git repository",
        "Run inside a repository or supply its path explicitly",
    ),
    "ERR-COLLECT-103": (
        "A requested Git revision cannot be resolved to a commit",
        "Check that the revision exists and has been fetched",
    ),
    "ERR-COLLECT-104": (
        "The requested Git backend is unknown or unavailable",
        "Select auto, pygit2, or subprocess; install attest-collect[pygit2] or ensure Git is on "
        "PATH",
    ),
    "ERR-COLLECT-105": (
        "Repository identity is unavailable or cannot be normalised",
        "Supply a canonical HTTPS or supported Git remote URL explicitly",
    ),
    "ERR-COLLECT-106": (
        "A Git operation failed after collector boundary validation",
        "Check repository integrity and permissions, then retry",
    ),
}


class CollectError(RuntimeError):
    """Represent a stable BRD-F02 public-operation failure (REQ-F02-190)."""

    code: CollectErrorCode
    message: str
    remediation: str

    def __init__(self, *, code: CollectErrorCode, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def collect_error(code: CollectErrorCode) -> CollectError:
    """Create the BRD-F02 error identified by ``code`` (REQ-F02-190)."""
    message, remediation = _ERROR_DETAILS[code]
    return CollectError(code=code, message=message, remediation=remediation)
