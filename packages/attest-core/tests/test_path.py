"""Acceptance tests for canonical raw Git path representation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from attest_core.canonical import canonicalize
from attest_core.models import ChangeSetEntry, ChangeType
from attest_core.path import decode_git_path, encode_git_path


@pytest.mark.ac("AC-F01-180")
@pytest.mark.vectors
@pytest.mark.parametrize(
    ("raw", "encoded"),
    [
        (b"src/a.py", "src/a.py"),
        (b"docs/caf\xc3\xa9-\xff.md", "docs/caf%C3%A9-%FF.md"),
        (b"percent%.txt", "percent%25.txt"),
    ],
)
def test_git_paths_round_trip_through_model_and_canonicalization(raw: bytes, encoded: str) -> None:
    """REQ-F01-180: every raw-byte path has one canonical ASCII spelling."""
    assert encode_git_path(raw) == encoded
    assert decode_git_path(encoded) == raw
    entry = ChangeSetEntry(
        path=encoded,
        change_type=ChangeType.ADDED,
        old_mode=None,
        new_mode="100644",
        old_blob=None,
        new_blob="1" * 40,
    )
    assert encoded.encode("ascii") in canonicalize(entry.model_dump())


@pytest.mark.ac("AC-F01-180")
@pytest.mark.parametrize(
    "encoded",
    ["bad%", "bad%2", "bad%GG", "bad%ff", "percent%25%41.txt", "slash%2Fname", "café"],
)
def test_git_paths_reject_malformed_or_noncanonical_spellings(encoded: str) -> None:
    """REQ-F01-180: alternate spellings and direct non-ASCII text are invalid."""
    with pytest.raises(ValueError, match="Git path"):
        decode_git_path(encoded)
    with pytest.raises(ValidationError):
        ChangeSetEntry(
            path=encoded,
            change_type=ChangeType.ADDED,
            old_mode=None,
            new_mode="100644",
            old_blob=None,
            new_blob="1" * 40,
        )
