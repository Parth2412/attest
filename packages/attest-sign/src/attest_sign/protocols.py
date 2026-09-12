"""Public signing contracts governed by BRD-F06."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from attest_core.models.statement import Statement


class SigningEnvironment(StrEnum):
    """Select one explicit Sigstore service environment (REQ-F06-070)."""

    PRODUCTION = "production"
    STAGING = "staging"


@dataclass(frozen=True, slots=True)
class Bundle:
    """Carry validated bundle material and metadata (REQ-F06-050/070/110)."""

    raw: bytes
    environment: SigningEnvironment
    certificate_identity: str
    certificate_issuer: str
    log_index: int
    log_integrated_time: datetime | None


class Signer(Protocol):
    """Isolate callers from a concrete keyless implementation (REQ-F06-090)."""

    def sign(self, statement: Statement) -> Bundle:
        """Sign one validated Statement or raise a coded error (REQ-F06-100)."""
        ...
