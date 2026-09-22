"""Stable, sanitised application-boundary diagnostics for F-10."""

from __future__ import annotations

from typing import Final, Literal

from attest_cli.exit_codes import ExitCode

CliErrorCode = Literal[
    "ERR-CONFIG-001",
    "ERR-CONFIG-002",
    "ERR-CONFIG-003",
    "ERR-CONFIG-004",
    "ERR-CONFIG-005",
    "ERR-CONFIG-006",
    "ERR-INTERNAL-001",
]

_ERROR_DETAILS: Final[dict[CliErrorCode, tuple[str, str, ExitCode]]] = {
    "ERR-CONFIG-001": (
        "Invocation or resolved configuration is invalid or conflicting",
        "Correct the documented command options and configuration values",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-CONFIG-002": (
        "Configuration input is unsafe, unreadable, malformed, or unsupported",
        "Use a bounded regular file containing the version 1 closed configuration vocabulary",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-CONFIG-003": (
        "Input artifact is unsafe, unreadable, malformed, oversized, or unsupported",
        "Supply a bounded regular file in the documented artifact format and version",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-CONFIG-004": (
        "Output target is unsafe, already exists, unwritable, or could not be published atomically",
        "Choose a writable regular-file target and use --overwrite only when replacement is "
        "intended",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-CONFIG-005": (
        "Mandatory verification identity and issuer constraints are unresolved",
        "Configure both verification identity and issuer before verification",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-CONFIG-006": (
        "A required local diagnostic capability is unavailable or invalid",
        "Install or configure the reported local capability and retry",
        ExitCode.USAGE_ERROR,
    ),
    "ERR-INTERNAL-001": (
        "An unexpected internal failure occurred",
        "Retry once and report the command, version, and stable error code if it persists",
        ExitCode.INTERNAL_ERROR,
    ),
}


class CliError(RuntimeError):
    """Carry one public error without retaining unsafe exception text."""

    code: CliErrorCode
    message: str
    remediation: str
    exit_code: ExitCode

    def __init__(self, code: CliErrorCode) -> None:
        self.code = code
        self.message, self.remediation, self.exit_code = _ERROR_DETAILS[code]
        super().__init__(f"{code}: {self.message}. Remediation: {self.remediation}")


def cli_error(code: CliErrorCode) -> CliError:
    """Construct a stable CLI-boundary error."""
    return CliError(code)
