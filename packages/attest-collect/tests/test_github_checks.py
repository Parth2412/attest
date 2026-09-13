"""GitHub protection and check normalization tests for BRD-F04."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from attest_collect._github_http import GitHubHttpClient, GitHubToken
from attest_collect.errors import CollectError
from attest_collect.github import GitHubForgeAdapter, JsonObject
from attest_core import JsonValue, canonicalize

FIXTURES = Path(__file__).parent / "fixtures" / "github"
HEAD_SHA = "2" * 40
PRIVATE_CLASSIC_FAILURE = "private classic failure"
PRIVATE_RULES_FAILURE = "private rules failure"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler: Any) -> GitHubHttpClient:
    return GitHubHttpClient(
        GitHubToken("github_pat_fixture_token"),
        transport=httpx.MockTransport(handler),
        request_timeout=5.0,
        operation_deadline=30.0,
    )


def _protection(*, count: int) -> JsonObject:
    value = deepcopy(cast(JsonObject, _fixture("branch-protection.json")))
    reviews = cast(dict[str, JsonValue], value["required_pull_request_reviews"])
    reviews["required_approving_review_count"] = count
    return value


@pytest.mark.ac("AC-F04-100")
@pytest.mark.parametrize(
    ("rules", "protection_status", "protection_count", "expected", "warning_codes"),
    [
        (_fixture("branch-rules.json"), 200, 0, True, []),
        ([], 200, 1, True, []),
        ([], 200, 0, False, []),
        ([], 404, 0, False, []),
        ([], 403, 0, "unknown", ["ERR-COLLECT-121"]),
        (_fixture("branch-rules.json"), 403, 0, True, ["ERR-COLLECT-121"]),
    ],
)
def test_required_combines_rulesets_and_classic_protection(
    rules: list[JsonObject],
    protection_status: int,
    protection_count: int,
    expected: bool | str,
    warning_codes: list[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/branches/main"):
            return httpx.Response(200, json=rules)
        if request.url.path.endswith("/branches/main/protection"):
            if protection_status == 404:
                return httpx.Response(404, json={"message": "Not Found"})
            if protection_status == 403:
                return httpx.Response(403, json={"message": "Forbidden"})
            return httpx.Response(200, json=_protection(count=protection_count))
        raise AssertionError(request.url)

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_review_requirement("acme/widgets", "main")

    assert result.required == expected
    assert [warning.code for warning in result.warnings] == warning_codes


@pytest.mark.ac("AC-F04-140")
def test_every_terminal_check_rerun_is_collected_with_exact_digest() -> None:
    suites_page_1 = cast(JsonObject, _fixture("check-suites-page-1.json"))
    suites_page_2 = cast(JsonObject, _fixture("check-suites-page-2.json"))
    runs_501 = cast(JsonObject, _fixture("check-runs-501.json"))
    runs_502 = cast(JsonObject, _fixture("check-runs-502.json"))
    suite_url = (
        "https://api.github.com/repos/acme/widgets/commits/"
        f"{HEAD_SHA}/check-suites?per_page=100&page="
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-suites"):
            page = int(request.url.params["page"])
            if page == 1:
                links = f'<{suite_url}2>; rel="next", <{suite_url}2>; rel="last"'
                return httpx.Response(200, headers={"Link": links}, json=suites_page_1)
            return httpx.Response(200, json=suites_page_2)
        if request.url.path.endswith("/check-suites/501/check-runs"):
            assert request.url.params["filter"] == "all"
            return httpx.Response(200, json=runs_501)
        if request.url.path.endswith("/check-suites/502/check-runs"):
            assert request.url.params["filter"] == "all"
            return httpx.Response(200, json=runs_502)
        raise AssertionError(request.url)

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_checks("acme/widgets", HEAD_SHA)

    assert [(check.name, check.run_id, check.conclusion) for check in result.checks] == [
        ("lint", "9004", "failure"),
        ("security", "9003", "failure"),
        ("security", "9005", "success"),
        ("unit-tests", "9001", "success"),
    ]
    assert [warning.code for warning in result.warnings] == ["WARN-COLLECT-005"]
    raw_success = cast(list[JsonObject], runs_501["check_runs"])[0]
    expected_digest = sha256(canonicalize(cast(JsonValue, raw_success))).hexdigest()
    unit_check = next(check for check in result.checks if check.run_id == "9001")
    assert unit_check.details_digest == expected_digest


def test_check_suite_total_count_mismatch_is_incomplete() -> None:
    body = cast(JsonObject, _fixture("check-suites-page-1.json"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        GitHubForgeAdapter(client).fetch_checks("acme/widgets", HEAD_SHA)

    assert captured.value.code == "ERR-COLLECT-122"


def test_duplicate_check_run_id_is_incomplete() -> None:
    suites = deepcopy(cast(JsonObject, _fixture("check-suites-page-1.json")))
    suites["total_count"] = 1
    runs = deepcopy(cast(JsonObject, _fixture("check-runs-501.json")))
    check_runs = cast(list[JsonObject], runs["check_runs"])
    check_runs[1] = deepcopy(check_runs[0])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-suites"):
            return httpx.Response(200, json=suites)
        return httpx.Response(200, json=runs)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        GitHubForgeAdapter(client).fetch_checks("acme/widgets", HEAD_SHA)

    assert captured.value.code == "ERR-COLLECT-122"


def test_unknown_terminal_conclusion_is_response_failure() -> None:
    suites = deepcopy(cast(JsonObject, _fixture("check-suites-page-1.json")))
    suites["total_count"] = 1
    runs = deepcopy(cast(JsonObject, _fixture("check-runs-501.json")))
    runs["total_count"] = 1
    check_runs = cast(list[JsonObject], runs["check_runs"])
    check_runs[:] = [check_runs[0]]
    check_runs[0]["conclusion"] = "new-unmapped-state"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-suites"):
            return httpx.Response(200, json=suites)
        return httpx.Response(200, json=runs)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        GitHubForgeAdapter(client).fetch_checks("acme/widgets", HEAD_SHA)

    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.parametrize(
    "parameters",
    [
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": True,
            "require_last_push_approval": False,
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": False,
            "require_last_push_approval": True,
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_reviewers": [{"minimum_approvals": 1}],
        },
    ],
)
def test_each_ruleset_review_requirement_is_honoured(parameters: JsonObject) -> None:
    rules: list[JsonObject] = [{"ruleset_id": 1, "type": "pull_request", "parameters": parameters}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/branches/main"):
            return httpx.Response(200, json=rules)
        return httpx.Response(404, json={"message": "Not Found"})

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_review_requirement("acme/widgets", "main")

    assert result.required is True
    assert result.warnings == ()


@pytest.mark.parametrize(
    "parameters",
    [
        None,
        {
            "required_approving_review_count": True,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": "false",
            "require_last_push_approval": False,
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_reviewers": "team",
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_reviewers": ["team"],
        },
        {
            "required_approving_review_count": 0,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_reviewers": [{"minimum_approvals": True}],
        },
    ],
)
def test_malformed_ruleset_review_configuration_degrades(parameters: object) -> None:
    rules = [{"ruleset_id": 1, "type": "pull_request", "parameters": parameters}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/branches/main"):
            return httpx.Response(200, json=rules)
        return httpx.Response(404, json={"message": "Not Found"})

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_review_requirement("acme/widgets", "main")

    assert result.required == "unknown"
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-125"]


def test_non_pull_request_rule_and_missing_classic_reviews_do_not_require_review() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/branches/main"):
            return httpx.Response(
                200,
                json=[{"ruleset_id": 1, "type": "required_status_checks"}],
            )
        return httpx.Response(200, json={"enforce_admins": {"enabled": True}})

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_review_requirement("acme/widgets", "main")

    assert result.required is False
    assert result.warnings == ()


def test_malformed_rule_type_degrades_rules_source_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rules/branches/main"):
            return httpx.Response(200, json=[{"ruleset_id": 1}])
        return httpx.Response(200, json=_protection(count=1))

    with _client(handler) as client:
        result = GitHubForgeAdapter(client).fetch_review_requirement("acme/widgets", "main")

    assert result.required is True
    assert [warning.reference for warning in result.warnings] == ["github:branch-rules"]


def test_unknown_check_status_is_response_failure() -> None:
    suites = deepcopy(cast(JsonObject, _fixture("check-suites-page-1.json")))
    suites["total_count"] = 1
    runs = deepcopy(cast(JsonObject, _fixture("check-runs-501.json")))
    runs["total_count"] = 1
    check_runs = cast(list[JsonObject], runs["check_runs"])
    check_runs[:] = [check_runs[0]]
    check_runs[0]["status"] = "new-status"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-suites"):
            return httpx.Response(200, json=suites)
        return httpx.Response(200, json=runs)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        GitHubForgeAdapter(client).fetch_checks("acme/widgets", HEAD_SHA)

    assert captured.value.code == "ERR-COLLECT-125"


def test_duplicate_check_run_id_across_suites_is_incomplete() -> None:
    suites = deepcopy(cast(JsonObject, _fixture("check-suites-page-1.json")))
    suites["total_count"] = 2
    runs = deepcopy(cast(JsonObject, _fixture("check-runs-501.json")))
    runs["total_count"] = 1
    check_runs = cast(list[JsonObject], runs["check_runs"])
    check_runs[:] = [check_runs[0]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-suites"):
            return httpx.Response(200, json=suites)
        return httpx.Response(200, json=runs)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_check_runs("acme/widgets", HEAD_SHA)

    assert captured.value.code == "ERR-COLLECT-122"


class ExplodingProtectionClient:
    def fetch_branch_rules(self, repo: str, base_branch: str) -> tuple[JsonObject, ...]:
        raise RuntimeError(PRIVATE_RULES_FAILURE)

    def fetch_classic_protection(self, repo: str, base_branch: str) -> JsonObject | None:
        raise RuntimeError(PRIVATE_CLASSIC_FAILURE)


def test_unexpected_protection_failures_are_redacted_and_independent() -> None:
    adapter = GitHubForgeAdapter(cast(GitHubHttpClient, ExplodingProtectionClient()))

    result = adapter.fetch_review_requirement("acme/widgets", "main")

    assert result.required == "unknown"
    assert [warning.reference for warning in result.warnings] == [
        "github:branch-rules",
        "github:classic-protection",
    ]
    assert "private" not in repr(result)
