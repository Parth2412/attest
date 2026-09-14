"""Public storage models and protocols governed by BRD-F07 and ADR-043."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from attest_store._metadata import validate_digest, validate_location, validate_stored_time
from attest_store.errors import store_error

type StoreBackend = Literal["git-ref", "filesystem", "oci"]


@dataclass(frozen=True, slots=True)
class StoreRef:
    """Locate one exact, integrity-bound stored Bundle (REQ-F07-010)."""

    backend: StoreBackend
    digest: str
    bundle_digest: str
    location: str
    stored_at: datetime

    def __post_init__(self) -> None:
        if self.backend not in ("git-ref", "filesystem", "oci"):
            raise store_error("ERR-STORE-405")
        validate_digest(self.digest)
        validate_digest(self.bundle_digest)
        validate_location(self.location)
        validate_stored_time(self.stored_at)


@runtime_checkable
class AttestationStore(Protocol):
    """Provide backend-neutral exact Bundle persistence (REQ-F07-010)."""

    def put(self, digest: str, bundle: bytes) -> StoreRef:
        """Store one Bundle idempotently or raise a coded error."""
        ...

    def get(self, digest: str) -> list[bytes]:
        """Return every exact Bundle for one ChangeSet Digest."""
        ...

    def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
        """Return deterministic storage locators, inclusively filtered by time."""
        ...
