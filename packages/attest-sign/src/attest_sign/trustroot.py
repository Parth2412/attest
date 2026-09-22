"""Explicit Sigstore trust-root loading governed by BRD-F08 and ADR-038."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sigstore.models import ClientTrustConfig
from sigstore.verify import Verifier


class _InvalidTrustRootError(ValueError):
    """Signal a trust-root contract value that cannot be loaded."""


class VerificationEnvironment(StrEnum):
    """Select exactly one Sigstore verification service environment (REQ-F08-080)."""

    PRODUCTION = "production"
    STAGING = "staging"


@dataclass(frozen=True, slots=True)
class ServiceTrustRoot:
    """Select service trust material and explicit TUF refresh behavior (REQ-F08-080)."""

    environment: VerificationEnvironment
    offline: bool


@dataclass(frozen=True, slots=True)
class SuppliedTrustRoot:
    """Carry a complete Sigstore client trust configuration as JSON (REQ-F08-080)."""

    client_trust_config_json: str


type TrustRootSource = ServiceTrustRoot | SuppliedTrustRoot


def load_verifier(source: TrustRootSource) -> Verifier:
    """Build a verifier from exactly the caller-selected trust source (REQ-F08-080)."""
    if isinstance(source, ServiceTrustRoot):
        if not isinstance(source.offline, bool):
            raise _InvalidTrustRootError
        if source.environment is VerificationEnvironment.PRODUCTION:
            return Verifier.production(offline=source.offline)
        if source.environment is VerificationEnvironment.STAGING:
            return Verifier.staging(offline=source.offline)
        raise _InvalidTrustRootError
    if isinstance(source, SuppliedTrustRoot):
        config = ClientTrustConfig.from_json(source.client_trust_config_json)
        return Verifier(trusted_root=config.trusted_root)
    raise _InvalidTrustRootError
