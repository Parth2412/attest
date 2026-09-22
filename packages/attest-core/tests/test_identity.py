"""Acceptance tests for the shared bounded identity-pattern grammar."""

from __future__ import annotations

import pytest

from attest_core import identity_pattern_matches, validate_identity_pattern

IDENTITY = "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main"


@pytest.mark.ac("AC-F01-200")
@pytest.mark.parametrize(
    ("pattern", "identity", "expected"),
    [
        (IDENTITY, IDENTITY, True),
        (IDENTITY, IDENTITY.upper(), False),
        ("spiffe://example.test/workload", "spiffe://example.test/workload", True),
        (IDENTITY, None, False),
        (
            "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/*",
            IDENTITY,
            True,
        ),
        (
            "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/*",
            "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/",
            False,
        ),
        (
            "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/*",
            "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/release/v1",
            False,
        ),
    ],
)
def test_identity_pattern_matching_is_exact_anchored_and_segment_bounded(
    pattern: str,
    identity: object,
    expected: bool,
) -> None:
    """REQ-F01-200: exact and bounded patterns have one deterministic matcher."""
    assert validate_identity_pattern(pattern) == pattern
    assert identity_pattern_matches(pattern, identity) is expected


@pytest.mark.ac("AC-F01-200")
@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "*",
        "https://github.com/*/Repo/.github/workflows/a.yml@refs/heads/main",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/**",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/ma?n",
        "https://github.com/Org/Repo/.github/workflows/a.yml@refs/heads/[main]",
        "https://example.com/workflow@refs/heads/*",
        None,
        3,
    ],
)
def test_identity_pattern_validator_rejects_unbounded_or_invalid_grammar(pattern: object) -> None:
    """REQ-F01-200: invalid and non-GitHub wildcard forms are rejected centrally."""
    with pytest.raises(ValueError, match="invalid workload identity pattern"):
        validate_identity_pattern(pattern)
