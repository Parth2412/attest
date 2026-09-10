"""CLI exit codes. NORMATIVE — GLOSS-001 §7. Frozen; changing one is a major version bump."""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL_ERROR = 1
    USAGE_ERROR = 2
    POLICY_VIOLATION = 3
    VERIFICATION_FAILURE = 4
    ATTESTATION_NOT_FOUND = 5
    TRANSIENT_FAILURE = 6
