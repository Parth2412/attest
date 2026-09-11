"""ChangeSet digest algorithm CSD-1 governed by SPEC-001 §5."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from attest_core.canonical import JsonValue, canonicalize
from attest_core.constants import DIGEST_ALGORITHM
from attest_core.models.changeset import ChangeSetEntry, ChangeSetRecord
from attest_core.path import decode_git_path


def _validated_sorted_entries(
    entries: Sequence[ChangeSetEntry],
) -> tuple[ChangeSetEntry, ...]:
    validated = tuple(ChangeSetEntry.model_validate(entry.model_dump()) for entry in entries)
    return tuple(sorted(validated, key=lambda entry: decode_git_path(entry.path)))


def build_changeset_record(entries: Sequence[ChangeSetEntry]) -> ChangeSetRecord:
    """Build the exact sorted context-free CSD-1 record (REQ-F01-050/060)."""
    return ChangeSetRecord(
        algorithm=DIGEST_ALGORITHM,
        entries=_validated_sorted_entries(entries),
    )


def compute_changeset_digest(record: ChangeSetRecord) -> str:
    """Compute the lowercase SHA-256 CSD-1 digest (REQ-F01-050/060)."""
    validated_record = ChangeSetRecord.model_validate(record.model_dump())
    canonical_record = build_changeset_record(validated_record.entries)
    wire_value: JsonValue = canonical_record.model_dump()
    return sha256(canonicalize(wire_value)).hexdigest()
