"""Project-wide constants. Governed by SPEC-001 and ADR-013."""

from typing import Final

# ADR-013: v0.x URIs are explicitly unstable. Replace <org> at bootstrap.
# This MUST remain the single definition; never inline this string (REQ-F05-040).
PREDICATE_TYPE_V0_1: Final[str] = "https://parth2412.github.io/attest/ai-authorship/v0.1"

IN_TOTO_STATEMENT_TYPE: Final[str] = "https://in-toto.io/Statement/v1"
DSSE_PAYLOAD_TYPE: Final[str] = "application/vnd.in-toto+json"

SUBJECT_NAME: Final[str] = "changeset"
DIGEST_ALGORITHM: Final[str] = "CSD-1"
SCHEMA_VERSION: Final[str] = "0.1.0"

ATTESTATION_REF_PREFIX: Final[str] = "refs/attestations"  # ADR-014
