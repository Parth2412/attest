"""Stable public collector diagnostics governed by BRD-F02, BRD-F03, and BRD-F04."""

from __future__ import annotations

from typing import Final, Literal

CollectErrorCode = Literal[
    "ERR-COLLECT-101",
    "ERR-COLLECT-102",
    "ERR-COLLECT-103",
    "ERR-COLLECT-104",
    "ERR-COLLECT-105",
    "ERR-COLLECT-106",
    "ERR-COLLECT-115",
    "ERR-COLLECT-121",
    "ERR-COLLECT-122",
    "ERR-COLLECT-123",
    "ERR-COLLECT-124",
    "ERR-COLLECT-125",
    "ERR-COLLECT-126",
    "ERR-COLLECT-127",
]

CollectDiagnosticCode = Literal[
    "ERR-COLLECT-101",
    "ERR-COLLECT-102",
    "ERR-COLLECT-103",
    "ERR-COLLECT-104",
    "ERR-COLLECT-105",
    "ERR-COLLECT-106",
    "ERR-COLLECT-111",
    "ERR-COLLECT-112",
    "ERR-COLLECT-113",
    "ERR-COLLECT-114",
    "ERR-COLLECT-115",
    "ERR-COLLECT-116",
    "ERR-COLLECT-117",
    "ERR-COLLECT-118",
    "ERR-COLLECT-121",
    "ERR-COLLECT-122",
    "ERR-COLLECT-123",
    "ERR-COLLECT-124",
    "ERR-COLLECT-125",
    "ERR-COLLECT-126",
    "ERR-COLLECT-127",
]

_ERROR_DETAILS: Final[dict[CollectDiagnosticCode, tuple[str, str]]] = {
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
    "ERR-COLLECT-111": (
        "A sidecar claim file is malformed",
        "Validate the file against the sidecar claim schema",
    ),
    "ERR-COLLECT-112": (
        "The sidecar claims directory cannot be read",
        "Check the claims directory type and permissions",
    ),
    "ERR-COLLECT-113": (
        "A Git trailer claim is malformed",
        "Correct the trailer token and claim grammar",
    ),
    "ERR-COLLECT-114": (
        "A duplicate claim identifier was discarded",
        "Ensure claim emitters generate unique identifiers",
    ),
    "ERR-COLLECT-115": (
        "A changed path is not canonical",
        "Supply the canonical percent-encoded Git path",
    ),
    "ERR-COLLECT-116": (
        "A Git AI note is unreadable, unsupported, or malformed",
        "Fetch and validate the configured Git AI notes ref",
    ),
    "ERR-COLLECT-117": (
        "A manual claim is malformed",
        "Correct the manual claim grammar",
    ),
    "ERR-COLLECT-118": (
        "A claim collector failed unexpectedly",
        "Check the named collector and retry",
    ),
    "ERR-COLLECT-121": (
        "GitHub authentication failed or is ambiguously configured",
        "Configure exactly one token source with pull-request, checks, and metadata read access",
    ),
    "ERR-COLLECT-122": (
        "GitHub pagination is incomplete or internally inconsistent",
        "Retry the collection and report the response sequence if the failure persists",
    ),
    "ERR-COLLECT-123": (
        "The GitHub rate-limit deadline was exceeded",
        "Increase the collection deadline or reduce request frequency",
    ),
    "ERR-COLLECT-124": (
        "Pull-request context is missing or inconsistent",
        "Supply an explicit pull-request number or direct-push context",
    ),
    "ERR-COLLECT-125": (
        "GitHub request failed or returned an invalid response",
        "Check GitHub availability and the documented response contract, then retry",
    ),
    "ERR-COLLECT-126": (
        "Pull-request context input is malformed, unsupported, or inconsistent",
        "Supply an exact GitHub pull-request event or complete explicit repository, PR, base, "
        "head, and target inputs",
    ),
    "ERR-COLLECT-127": (
        "The forge PR/comparison cannot prove one consistent ChangeSet, merge base, and immutable "
        "author/committer identity set",
        "Retry a stable PR; ensure every commit identity is associated with a GitHub account and "
        "reduce or split an API-capped change",
    ),
}


class CollectError(RuntimeError):
    """Represent a stable collector public-operation failure."""

    code: CollectErrorCode
    message: str
    remediation: str

    def __init__(self, *, code: CollectErrorCode, message: str, remediation: str) -> None:
        self.code = code
        self.message = message
        self.remediation = remediation
        super().__init__(f"{code}: {message}. Remediation: {remediation}")


def collect_error(code: CollectErrorCode) -> CollectError:
    """Create the stable collector error identified by ``code``."""
    message, remediation = _ERROR_DETAILS[code]
    return CollectError(code=code, message=message, remediation=remediation)


def collect_diagnostic_details(code: CollectDiagnosticCode) -> tuple[str, str]:
    """Return stable public text for one collector diagnostic."""
    return _ERROR_DETAILS[code]
