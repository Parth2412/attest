"""Sigstore signing and verification adapters for attest."""

from attest_sign.protocols import Bundle, Signer, SigningEnvironment
from attest_sign.repository import RepositoryConstraint
from attest_sign.sigstore_signer import SigstoreSigner
from attest_sign.trustroot import (
    ServiceTrustRoot,
    SuppliedTrustRoot,
    TrustRootSource,
    VerificationEnvironment,
)
from attest_sign.verifier import (
    CheckOutcome,
    IdentityConstraint,
    InspectionResult,
    VerificationResult,
    inspect_bundle,
    verify,
)

__all__ = [
    "Bundle",
    "CheckOutcome",
    "IdentityConstraint",
    "InspectionResult",
    "RepositoryConstraint",
    "ServiceTrustRoot",
    "Signer",
    "SigningEnvironment",
    "SigstoreSigner",
    "SuppliedTrustRoot",
    "TrustRootSource",
    "VerificationEnvironment",
    "VerificationResult",
    "inspect_bundle",
    "verify",
]
