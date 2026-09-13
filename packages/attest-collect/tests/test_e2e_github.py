"""Live GitHub read-only smoke test, enabled only by the dedicated workflow."""

from __future__ import annotations

import os

import pytest

from attest_collect import collect_github, load_github_token
from attest_collect._github_http import GitHubHttpClient
from attest_collect.github import GitHubForgeAdapter, GitHubReviewContext, ReviewContextKind


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("ATTEST_GITHUB_E2E") != "1",
    reason="live GitHub collection runs only in the dedicated read-only workflow",
)
def test_live_github_reviews_rules_and_checks_are_readable() -> None:
    repository = os.environ["ATTEST_GITHUB_REPOSITORY"]
    head_sha = os.environ["ATTEST_GITHUB_HEAD_SHA"]
    base_branch = os.environ["ATTEST_GITHUB_BASE_BRANCH"]
    pr_number = int(os.environ["ATTEST_GITHUB_PR"])
    context = GitHubReviewContext(
        kind=ReviewContextKind.PULL_REQUEST,
        repository=repository,
        head_sha=head_sha,
        base_branch=base_branch,
        change_author_ids=frozenset(),
        pr_number=pr_number,
    )

    with GitHubHttpClient(
        load_github_token(),
        request_timeout=15.0,
        operation_deadline=120.0,
    ) as client:
        result = collect_github(GitHubForgeAdapter(client), context)

    assert result.review.state != "unknown"
    assert result.checks
    assert not {"ERR-COLLECT-122", "ERR-COLLECT-123", "ERR-COLLECT-125"} & {
        warning.code for warning in result.warnings
    }
