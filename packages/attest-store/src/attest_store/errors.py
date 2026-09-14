"""Stable, credential-safe storage diagnostics governed by BRD-F07."""

from __future__ import annotations

from typing import Final, Literal

StoreErrorCode = Literal[
    "ERR-STORE-401",
    "ERR-STORE-402",
    "ERR-STORE-403",
    "ERR-STORE-404",
    "ERR-STORE-405",
    "ERR-STORE-406",
]

_ERROR_DETAILS: Final[dict[StoreErrorCode, tuple[str, str]]] = {
    "ERR-STORE-401": (
        "The attestation ref push was rejected",
        "Grant contents: write for refs/attestations/* and retry the explicit push",
    ),
    "ERR-STORE-402": (
        "The configured storage backend is unreachable or exceeded its deadline",
        "Check registry, remote, authentication, proxy, and deadline configuration",
    ),
    "ERR-STORE-403": (
        "The ChangeSet Digest was not found",
        "Confirm the Bundle was stored or fetch refs/attestations/*",
    ),
    "ERR-STORE-404": (
        "The configured store is corrupted or unreadable",
        "Restore from the reported fallback path or another valid copy",
    ),
    "ERR-STORE-405": (
        "Storage input or configuration is invalid",
        "Supply a valid digest, UTC time, backend, location, subject, and deadline",
    ),
    "ERR-STORE-406": (
        "The primary and local fallback writes both failed; no durable copy was made",
        "Restore fallback write access and retry with the retained Bundle bytes",
    ),
}


class StoreError(RuntimeError):
    """Expose one stable storage code without backend diagnostics."""

    code: StoreErrorCode
    message: str
    remediation: str
    fallback_path: str | None

    def __init__(self, code: StoreErrorCode, *, fallback_path: str | None = None) -> None:
        self.code = code
        self.message, self.remediation = _ERROR_DETAILS[code]
        self.fallback_path = fallback_path
        detail = f"{code}: {self.message}. Remediation: {self.remediation}"
        if fallback_path is not None:
            detail = f"{detail}. Fallback: {fallback_path}"
        super().__init__(detail)

    def __reduce__(self) -> tuple[object, tuple[StoreErrorCode, str | None]]:
        """Preserve stable fields across the OCI and test process boundaries."""
        return _restore_store_error, (self.code, self.fallback_path)


def _restore_store_error(code: StoreErrorCode, fallback_path: str | None) -> StoreError:
    return StoreError(code, fallback_path=fallback_path)


def store_error(code: StoreErrorCode, *, fallback_path: str | None = None) -> StoreError:
    """Create the storage error identified by ``code``."""
    return StoreError(code, fallback_path=fallback_path)
