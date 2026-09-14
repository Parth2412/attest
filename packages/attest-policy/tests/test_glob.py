"""Acceptance tests for attest-owned branch and raw-path glob semantics."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from attest_policy.glob import branch_pattern_matches, path_pattern_matches


@pytest.mark.ac("AC-F09-080")
@pytest.mark.parametrize(
    ("kind", "pattern", "value", "expected"),
    [
        ("branch", "release/*", "release/v1", True),
        ("branch", "release/*", "release/v1/hotfix", False),
        ("branch", "release/*", "Release/v1", False),
        ("branch", "release/**", "release/v1/hotfix", True),
        ("branch", "release/**", "release", False),
        ("path", "docs/**", "docs/a.md", True),
        ("path", "docs/**", "docs/api/a.md", True),
        ("path", "docs/**", "docs", False),
        ("path", "**/*.lock", "uv.lock", True),
        ("path", "**/*.lock", "nested/uv.lock", True),
        ("path", "**/*.lock", "uv.lock.bak", False),
        ("path", "**/auth/**", "auth/a.py", True),
        ("path", "**/auth/**", "src/auth/a.py", True),
        ("path", "**/auth/**", "src/author/a.py", False),
        ("path", "**", "anything", True),
        ("path", "src/%FF*.bin", "src/%FFraw.bin", True),
        ("path", "src/%2A.txt", "src/%2A.txt", True),
        ("path", "src/A*", "src/a.py", False),
        ("path", "src/*.py", "prefix/src/a.py", False),
    ],
)
def test_glob_table_is_case_sensitive_anchored_and_raw_byte_exact(
    kind: str,
    pattern: str,
    value: str,
    expected: bool,
) -> None:
    matcher = branch_pattern_matches if kind == "branch" else path_pattern_matches
    assert matcher(pattern, value) is expected


@pytest.mark.ac("AC-F09-080")
@pytest.mark.parametrize(
    "pattern",
    ["a?b", "a[b]", "a\\b", "***", "a**", "**b", "a/***/b"],
)
@pytest.mark.parametrize("matcher", [branch_pattern_matches, path_pattern_matches])
def test_invalid_glob_tokens_are_rejected(
    pattern: str,
    matcher: Callable[[str, str], bool],
) -> None:
    with pytest.raises(ValueError, match="invalid policy glob pattern"):
        matcher(pattern, "value")


@pytest.mark.ac("AC-F09-080")
def test_valid_policy_glob_is_not_limited_by_python_recursion_depth() -> None:
    value = "/".join("a" for _ in range(1_100))

    assert branch_pattern_matches(value, value) is True
    assert path_pattern_matches(value, value) is True
