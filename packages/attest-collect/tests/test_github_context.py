"""Fail-closed GitHub ChangeSet-context tests for BRD-F04."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from attest_collect import GitHubHttpClient, GitHubToken
from attest_collect.errors import CollectError, collect_error
from attest_collect.github import (
    GitHubChangeSetContext,
    GitHubPullRequestInput,
    JsonObject,
    parse_github_pull_request_event,
    resolve_github_changeset_context,
)
from attest_core import JsonValue

FIXTURES = Path(__file__).parent / "fixtures" / "github"
REPOSITORY = "acme/widgets"
PR_NUMBER = 7
BASE = "1" * 40
MERGE_BASE = BASE
HEAD = "4" * 40
TOKEN = "github_pat_context_test_secret"


def _fixture(name: str) -> JsonObject:
    return cast(JsonObject, json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _event_bytes(value: object | None = None) -> bytes:
    event = _fixture("pull-request-event.json") if value is None else value
    return json.dumps(event, separators=(",", ":")).encode()


def _request() -> GitHubPullRequestInput:
    return GitHubPullRequestInput(
        repository=REPOSITORY,
        pr_number=PR_NUMBER,
        base_revision=BASE,
        head_revision=HEAD,
        target_branch="main",
    )


@dataclass(slots=True)
class StaticContextAdapter:
    pull_requests: list[JsonObject]
    pages: tuple[JsonObject, ...]
    calls: list[tuple[object, ...]] = field(default_factory=list)
    failure: Exception | None = None

    def fetch_pull_request(self, repo: str, pr_number: int) -> JsonObject:
        self.calls.append(("pull-request", repo, pr_number))
        if self.failure is not None:
            raise self.failure
        return deepcopy(self.pull_requests.pop(0))

    def fetch_comparison_pages(
        self,
        repo: str,
        base_revision: str,
        head_revision: str,
    ) -> tuple[JsonObject, ...]:
        self.calls.append(("comparison", repo, base_revision, head_revision))
        if self.failure is not None:
            raise self.failure
        return deepcopy(self.pages)


def _adapter() -> StaticContextAdapter:
    pull_request = _fixture("pull-request.json")
    return StaticContextAdapter(
        pull_requests=[deepcopy(pull_request), deepcopy(pull_request)],
        pages=(_fixture("compare-page-1.json"), _fixture("compare-page-2.json")),
    )


@pytest.mark.ac("AC-F04-150")
def test_recorded_event_and_paginated_comparison_resolve_exact_context() -> None:
    request = parse_github_pull_request_event((FIXTURES / "pull-request-event.json").read_bytes())
    adapter = _adapter()

    result = resolve_github_changeset_context(adapter, request)

    assert result == GitHubChangeSetContext(
        repository=REPOSITORY,
        pr_number=PR_NUMBER,
        base_revision=BASE,
        head_revision=HEAD,
        merge_base_revision=MERGE_BASE,
        target_branch="main",
        change_author_ids=frozenset({"101", "102", "201", "202"}),
    )
    assert adapter.calls == [
        ("pull-request", REPOSITORY, PR_NUMBER),
        ("comparison", REPOSITORY, BASE, HEAD),
        ("pull-request", REPOSITORY, PR_NUMBER),
    ]


@pytest.mark.ac("AC-F04-150")
@pytest.mark.parametrize(
    "case",
    [
        "not-utf8",
        "duplicate-key",
        "wrong-root",
        "missing-pull-request",
        "boolean-number",
        "uppercase-base",
        "invalid-target",
        "repository-mismatch",
    ],
)
def test_malformed_or_inconsistent_event_is_rejected(case: str) -> None:
    if case == "not-utf8":
        payload = b"\xff"
    elif case == "duplicate-key":
        payload = b'{"number":7,"number":8}'
    elif case == "wrong-root":
        payload = _event_bytes([])
    else:
        event = _fixture("pull-request-event.json")
        pull_request = cast(dict[str, JsonValue], event["pull_request"])
        base = cast(dict[str, JsonValue], pull_request["base"])
        if case == "missing-pull-request":
            del event["pull_request"]
        elif case == "boolean-number":
            event["number"] = True
        elif case == "uppercase-base":
            base["sha"] = BASE.upper().replace("1", "A")
        elif case == "invalid-target":
            base["ref"] = "feature/*"
        else:
            base_repo = cast(dict[str, JsonValue], base["repo"])
            base_repo["full_name"] = "acme/other"
        payload = _event_bytes(event)

    with pytest.raises(CollectError) as captured:
        parse_github_pull_request_event(payload)

    assert captured.value.code == "ERR-COLLECT-126"


@pytest.mark.ac("AC-F04-150")
@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("repository", "not-a-repository"),
        ("pr_number", True),
        ("base_revision", "A" * 40),
        ("head_revision", "short"),
        ("target_branch", "feature/*"),
    ],
)
def test_explicit_input_is_validated(field_name: str, value: object) -> None:
    values: dict[str, object] = {
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "base_revision": BASE,
        "head_revision": HEAD,
        "target_branch": "main",
    }
    values[field_name] = value

    with pytest.raises(CollectError) as captured:
        GitHubPullRequestInput(**cast(Any, values))

    assert captured.value.code == "ERR-COLLECT-126"


def _set_pr_field(response: JsonObject, case: str) -> None:
    base = cast(dict[str, JsonValue], response["base"])
    head = cast(dict[str, JsonValue], response["head"])
    if case == "number":
        response["number"] = 8
    elif case == "repository":
        repository = cast(dict[str, JsonValue], base["repo"])
        repository["full_name"] = "acme/other"
    elif case == "base":
        base["sha"] = "0" * 40
    elif case == "head":
        head["sha"] = "5" * 40
    else:
        base["ref"] = "release"


@pytest.mark.ac("AC-F04-150")
@pytest.mark.parametrize("case", ["number", "repository", "base", "head", "target"])
def test_pull_request_binding_mismatch_returns_no_context(case: str) -> None:
    wrong = _fixture("pull-request.json")
    _set_pr_field(wrong, case)
    adapter = _adapter()
    adapter.pull_requests[0] = wrong

    with pytest.raises(CollectError) as captured:
        resolve_github_changeset_context(adapter, _request())

    assert captured.value.code == "ERR-COLLECT-127"
    assert adapter.calls == [("pull-request", REPOSITORY, PR_NUMBER)]


@pytest.mark.ac("AC-F04-150")
def test_pull_request_change_after_comparison_returns_no_context() -> None:
    adapter = _adapter()
    _set_pr_field(adapter.pull_requests[1], "head")

    with pytest.raises(CollectError) as captured:
        resolve_github_changeset_context(adapter, _request())

    assert captured.value.code == "ERR-COLLECT-127"
    assert len(adapter.calls) == 3


def _comparison_case(case: str) -> tuple[JsonObject, ...]:
    first = _fixture("compare-page-1.json")
    second = _fixture("compare-page-2.json")
    first_commits = cast(list[JsonValue], first["commits"])
    second_commits = cast(list[JsonValue], second["commits"])
    head_commit = cast(dict[str, JsonValue], second_commits[0])
    if case == "wrong-base":
        base_commit = cast(dict[str, JsonValue], first["base_commit"])
        base_commit["sha"] = "0" * 40
    elif case == "wrong-head":
        head_commit["sha"] = "5" * 40
    elif case == "total-drift":
        second["total_commits"] = 4
    elif case == "missing-page":
        return (first,)
    elif case == "duplicate-commit":
        first_commit = cast(dict[str, JsonValue], first_commits[0])
        head_commit["sha"] = first_commit["sha"]
    elif case == "capped":
        first["ahead_by"] = 4
        second["ahead_by"] = 4
    elif case == "missing-merge-base":
        del first["merge_base_commit"]
    elif case == "unmapped-author":
        first_commit = cast(dict[str, JsonValue], first_commits[0])
        first_commit["author"] = None
        first_commit["commit"] = {"author": {"name": "Alice", "email": "alice@example.test"}}
    else:
        head_commit["committer"] = {"id": "202", "login": "release-service"}
    return first, second


@pytest.mark.ac("AC-F04-150")
@pytest.mark.parametrize(
    "case",
    [
        "wrong-base",
        "wrong-head",
        "total-drift",
        "missing-page",
        "duplicate-commit",
        "capped",
        "missing-merge-base",
        "unmapped-author",
        "string-committer-id",
    ],
)
def test_incomplete_or_identity_unmapped_comparison_returns_no_context(case: str) -> None:
    adapter = _adapter()
    adapter.pages = _comparison_case(case)

    with pytest.raises(CollectError) as captured:
        resolve_github_changeset_context(adapter, _request())

    assert captured.value.code == "ERR-COLLECT-127"


@pytest.mark.ac("AC-F04-150")
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (collect_error("ERR-COLLECT-121"), "ERR-COLLECT-121"),
        (collect_error("ERR-COLLECT-123"), "ERR-COLLECT-123"),
        (collect_error("ERR-COLLECT-122"), "ERR-COLLECT-127"),
        (collect_error("ERR-COLLECT-125"), "ERR-COLLECT-127"),
        (RuntimeError("private response"), "ERR-COLLECT-127"),
    ],
)
def test_context_boundary_preserves_auth_rate_errors_and_sanitises_other_failures(
    failure: Exception,
    expected: str,
) -> None:
    adapter = _adapter()
    adapter.failure = failure

    with pytest.raises(CollectError) as captured:
        resolve_github_changeset_context(adapter, _request())

    assert captured.value.code == expected
    assert "private response" not in str(captured.value)


def _compare_url(page: int) -> str:
    return (
        f"https://api.github.com/repos/{REPOSITORY}/compare/{BASE}...{HEAD}"
        f"?per_page=100&page={page}"
    )


def _compare_links(*, next_page: int | None, last_page: int) -> str:
    values: list[str] = []
    if next_page is not None:
        values.append(f'<{_compare_url(next_page)}>; rel="next"')
    values.append(f'<{_compare_url(last_page)}>; rel="last"')
    return ", ".join(values)


@pytest.mark.ac("AC-F04-150")
def test_http_adapter_uses_exact_pr_and_paginated_compare_endpoints() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/pulls/7"):
            return httpx.Response(200, json=_fixture("pull-request.json"))
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            headers={
                "Link": _compare_links(
                    next_page=2 if page == 1 else None,
                    last_page=2,
                )
            },
            json=_fixture(f"compare-page-{page}.json"),
        )

    client = GitHubHttpClient(GitHubToken(TOKEN), transport=httpx.MockTransport(handler))
    with client:
        result = resolve_github_changeset_context(client, _request())

    assert result.merge_base_revision == MERGE_BASE
    assert calls == [
        f"https://api.github.com/repos/{REPOSITORY}/pulls/{PR_NUMBER}",
        _compare_url(1),
        _compare_url(2),
        f"https://api.github.com/repos/{REPOSITORY}/pulls/{PR_NUMBER}",
    ]


@pytest.mark.ac("AC-F04-150")
def test_http_compare_pagination_rejects_a_missing_expected_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Link": _compare_links(next_page=None, last_page=2)},
            json=_fixture("compare-page-1.json"),
        )

    client = GitHubHttpClient(GitHubToken(TOKEN), transport=httpx.MockTransport(handler))
    with client, pytest.raises(CollectError) as captured:
        client.fetch_comparison_pages(REPOSITORY, BASE, HEAD)

    assert captured.value.code == "ERR-COLLECT-122"


def test_context_result_rejects_invalid_construction() -> None:
    with pytest.raises(CollectError) as captured:
        GitHubChangeSetContext(
            repository=REPOSITORY,
            pr_number=PR_NUMBER,
            base_revision=BASE,
            head_revision=HEAD,
            merge_base_revision="invalid",
            target_branch="main",
            change_author_ids=frozenset({"101"}),
        )

    assert captured.value.code == "ERR-COLLECT-127"
