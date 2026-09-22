"""Deterministic GitHub review normalization tests for BRD-F04."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from attest_collect.errors import CollectError, collect_error
from attest_collect.github import (
    ForgeCheckData,
    ForgeReviewData,
    GitHubCollection,
    GitHubReviewContext,
    JsonObject,
    ReviewContextKind,
    ReviewRequired,
    ReviewRequirementData,
    collect_github,
    collect_review,
)
from attest_core import JsonValue, canonicalize

FIXTURES = Path(__file__).parent / "fixtures" / "github"
HEAD_SHA = "2" * 40


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _review(
    *,
    review_id: int = 1001,
    user_id: int = 12345,
    login: str = "bob",
    account_type: str = "User",
    state: str = "APPROVED",
    submitted_at: str | None = "2026-09-13T09:20:00Z",
) -> JsonObject:
    raw = deepcopy(cast(list[JsonObject], _fixture("reviews-page-1.json"))[0])
    raw["id"] = review_id
    user = cast(dict[str, JsonValue], raw["user"])
    user["id"] = user_id
    user["login"] = login
    user["type"] = account_type
    raw["state"] = state
    raw["submitted_at"] = submitted_at
    return raw


def _data(
    *responses: JsonObject,
    required: ReviewRequired = True,
    pushed_at: datetime | None = None,
) -> ForgeReviewData:
    return ForgeReviewData(
        responses=responses,
        required=required,
        last_commit_pushed_at=pushed_at,
    )


@dataclass(frozen=True, slots=True)
class StaticForgeAdapter:
    reviews: tuple[JsonObject, ...] = ()
    requirement: ReviewRequirementData = field(
        default_factory=lambda: ReviewRequirementData(required=False, warnings=())
    )
    check_data: ForgeCheckData = field(
        default_factory=lambda: ForgeCheckData(checks=(), warnings=())
    )
    requirement_error: Exception | None = None
    review_error: Exception | None = None
    check_error: Exception | None = None

    def fetch_reviews(self, repo: str, pr_number: int) -> tuple[JsonObject, ...]:
        if self.review_error is not None:
            raise self.review_error
        return self.reviews

    def fetch_review_requirement(
        self,
        repo: str,
        base_branch: str,
    ) -> ReviewRequirementData:
        if self.requirement_error is not None:
            raise self.requirement_error
        return self.requirement

    def fetch_checks(self, repo: str, head_sha: str) -> ForgeCheckData:
        if self.check_error is not None:
            raise self.check_error
        return self.check_data


def _context(
    *,
    kind: ReviewContextKind = ReviewContextKind.PULL_REQUEST,
    pr_number: int | None = 7,
    change_author_ids: frozenset[str] = frozenset(),
    pushed_at: datetime | None = None,
) -> GitHubReviewContext:
    return GitHubReviewContext(
        kind=kind,
        repository="acme/widgets",
        head_sha=HEAD_SHA,
        base_branch="main",
        change_author_ids=change_author_ids,
        pr_number=pr_number,
        last_commit_pushed_at=pushed_at,
    )


@pytest.mark.ac("AC-F04-010")
def test_reviewer_identity_keeps_immutable_numeric_id_across_rename() -> None:
    before = collect_review(_data(_review(login="bob")), set())
    after = collect_review(_data(_review(login="bob-renamed")), set())

    assert before.reviewers[0].identity == "github:12345:bob"
    assert after.reviewers[0].identity == "github:12345:bob-renamed"
    assert before.reviewers[0].identity.split(":")[1] == after.reviewers[0].identity.split(":")[1]


@pytest.mark.ac("AC-F04-020")
def test_only_latest_human_verdict_counts_and_all_records_remain() -> None:
    requested = _review(
        review_id=1001,
        state="CHANGES_REQUESTED",
        submitted_at="2026-09-13T09:05:00Z",
    )
    approved = _review(
        review_id=1003,
        login="bob-renamed",
        state="APPROVED",
        submitted_at="2026-09-13T09:20:00Z",
    )

    result = collect_review(_data(approved, requested), set())

    assert result.state == "approved"
    assert result.human_approvals == 1
    assert [review.verdict for review in result.reviewers] == ["changes-requested", "approved"]
    assert [review.effective for review in result.reviewers] == [False, True]


@pytest.mark.ac("AC-F04-020")
def test_equal_timestamp_uses_numeric_review_id_for_effective_verdict() -> None:
    """REQ-F04-020: numeric review ID is the deterministic latest-state tiebreaker."""
    timestamp = "2026-09-13T09:20:00Z"
    approved = _review(review_id=1001, state="APPROVED", submitted_at=timestamp)
    requested = _review(
        review_id=1002,
        login="bob-renamed",
        state="CHANGES_REQUESTED",
        submitted_at=timestamp,
    )

    result = collect_review(_data(requested, approved), set())

    assert result.state == "changes-requested"
    assert result.human_approvals == 0
    assert [review.effective for review in result.reviewers] == [False, True]


@pytest.mark.ac("AC-F04-020")
def test_active_change_request_takes_aggregate_precedence() -> None:
    approved = _review(user_id=10, login="alice", review_id=1, state="APPROVED")
    requested = _review(user_id=20, login="bob", review_id=2, state="CHANGES_REQUESTED")

    result = collect_review(_data(approved, requested), set())

    assert result.state == "changes-requested"
    assert result.human_approvals == 1


@pytest.mark.ac("AC-F04-030")
def test_dismissed_approval_does_not_count() -> None:
    result = collect_review(_data(_review(state="DISMISSED")), set())

    assert result.state == "none"
    assert result.human_approvals == 0
    assert result.reviewers[0].verdict == "dismissed"


@pytest.mark.ac("AC-F04-040")
def test_bot_review_is_automated_and_never_a_human_approval() -> None:
    result = collect_review(
        _data(_review(account_type="Bot", login="review-bot[bot]")),
        set(),
    )

    assert result.state == "none"
    assert result.human_approvals == 0
    assert result.reviewers == ()
    assert result.automated_reviews is not None
    assert result.automated_reviews[0].tool == "review-bot[bot]"
    assert result.automated_reviews[0].verdict == "approved"


@pytest.mark.ac("AC-F04-040")
def test_pending_review_is_omitted_with_warning() -> None:
    adapter = StaticForgeAdapter(reviews=(_review(state="PENDING", submitted_at=None),))

    result = collect_github(adapter, _context())

    assert result.review.state == "none"
    assert result.review.reviewers == ()
    assert [warning.code for warning in result.warnings] == ["WARN-COLLECT-006"]


@pytest.mark.ac("AC-F04-050")
def test_immutable_author_id_marks_self_review() -> None:
    result = collect_review(_data(_review()), {"12345", "777"})

    assert result.reviewers[0].is_change_author is True


@pytest.mark.ac("AC-F04-060")
def test_review_evidence_digest_matches_complete_response_object() -> None:
    response = _review()
    expected = sha256(canonicalize(cast(JsonValue, response))).hexdigest()

    result = collect_review(_data(response), set())

    assert result.reviewers[0].evidence.digest == expected


@pytest.mark.ac("AC-F04-100")
@pytest.mark.parametrize("required", [True, False, "unknown"])
def test_direct_push_is_none_and_preserves_resolved_requirement(
    required: ReviewRequired,
) -> None:
    adapter = StaticForgeAdapter(requirement=ReviewRequirementData(required=required, warnings=()))

    result = collect_github(
        adapter,
        _context(kind=ReviewContextKind.DIRECT_PUSH, pr_number=None),
    )

    assert result.review.state == "none"
    assert result.review.required == required
    assert result.review.human_approvals == 0


@pytest.mark.ac("AC-F04-110")
def test_latency_requires_authentic_ordered_push_time() -> None:
    approval = _review(submitted_at="2026-09-13T09:20:00Z")
    missing = collect_review(_data(approval), set())
    reversed_time = collect_review(
        _data(approval, pushed_at=datetime(2026, 9, 13, 9, 21, tzinfo=UTC)),
        set(),
    )
    exact = collect_review(
        _data(approval, pushed_at=datetime(2026, 9, 13, 9, 5, tzinfo=UTC)),
        set(),
    )

    assert missing.review_latency_seconds is None
    assert "reviewLatencySeconds" not in missing.model_dump()
    assert reversed_time.review_latency_seconds is None
    assert exact.review_latency_seconds == 900


@pytest.mark.ac("AC-F04-130")
def test_review_server_failure_returns_unknown_and_preserves_check_result() -> None:
    adapter = StaticForgeAdapter(
        review_error=collect_error("ERR-COLLECT-125"),
        check_data=ForgeCheckData(checks=(), warnings=()),
    )

    result = collect_github(adapter, _context())

    assert isinstance(result, GitHubCollection)
    assert result.review.state == "unknown"
    assert result.review.required == "unknown"
    assert result.checks == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-125"]


@pytest.mark.ac("AC-F04-130")
def test_check_failure_omits_checks_without_discarding_review() -> None:
    adapter = StaticForgeAdapter(
        reviews=(_review(),),
        requirement=ReviewRequirementData(required=True, warnings=()),
        check_error=collect_error("ERR-COLLECT-125"),
    )

    result = collect_github(adapter, _context())

    assert result.review.state == "approved"
    assert result.checks is None
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-125"]


def test_unsupported_submitted_account_type_fails_open_without_private_content() -> None:
    private_body = "private review text"
    response = _review(account_type="Organization")
    response["body"] = private_body

    result = collect_github(StaticForgeAdapter(reviews=(response,)), _context())
    rendered = repr(result)

    assert result.review.state == "unknown"
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-125"]
    assert private_body not in rendered


def test_undetermined_context_degrades_review_but_still_collects_checks() -> None:
    result = collect_github(
        StaticForgeAdapter(),
        _context(kind=ReviewContextKind.UNDETERMINED, pr_number=None),
    )

    assert result.review.state == "unknown"
    assert result.checks == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-124"]


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "not-a-repository"},
        {"head_sha": "ABC"},
        {"base_branch": ""},
        {"change_author_ids": frozenset({"bob"})},
        {"kind": ReviewContextKind.PULL_REQUEST, "pr_number": None},
        {"kind": ReviewContextKind.DIRECT_PUSH, "pr_number": 7},
        {"last_commit_pushed_at": datetime(2026, 9, 13, 9, 5, tzinfo=UTC).replace(tzinfo=None)},
    ],
)
def test_invalid_context_is_coded(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "kind": ReviewContextKind.PULL_REQUEST,
        "repository": "acme/widgets",
        "head_sha": HEAD_SHA,
        "base_branch": "main",
        "change_author_ids": frozenset(),
        "pr_number": 7,
        "last_commit_pushed_at": None,
    }
    arguments.update(changes)

    with pytest.raises(CollectError) as captured:
        GitHubReviewContext(**cast(Any, arguments))

    assert captured.value.code == "ERR-COLLECT-124"


@pytest.mark.parametrize("required", [None, 0, "yes"])
def test_invalid_requirement_data_is_coded(required: object) -> None:
    with pytest.raises(CollectError) as captured:
        ForgeReviewData(
            responses=(),
            required=cast(Any, required),
            last_commit_pushed_at=None,
        )

    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state", "NEW_STATE"),
        ("state", ""),
        ("id", True),
        ("user", None),
        ("submitted_at", None),
        ("submitted_at", "not-a-timestamp"),
        ("submitted_at", "2026-09-13T09:20:00"),
    ],
)
def test_malformed_review_fields_are_coded(field: str, value: object) -> None:
    response = _review()
    response[field] = cast(JsonValue, value)

    with pytest.raises(CollectError) as captured:
        collect_review(_data(response), set())

    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", 0), ("login", ""), ("type", "Organization")],
)
def test_malformed_review_user_fields_are_coded(field: str, value: object) -> None:
    response = _review()
    user = cast(dict[str, JsonValue], response["user"])
    user[field] = cast(JsonValue, value)

    with pytest.raises(CollectError) as captured:
        collect_review(_data(response), set())

    assert captured.value.code == "ERR-COLLECT-125"


def test_invalid_change_author_identity_is_coded() -> None:
    with pytest.raises(CollectError) as captured:
        collect_review(_data(_review()), {"01"})

    assert captured.value.code == "ERR-COLLECT-125"


def test_latest_commented_review_produces_commented_state() -> None:
    result = collect_review(_data(_review(state="COMMENTED")), set())

    assert result.state == "commented"
    assert result.human_approvals == 0


def test_domain_model_validation_is_wrapped_as_response_failure() -> None:
    with pytest.raises(CollectError) as captured:
        collect_review(_data(_review(login="login:with:separator")), set())

    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.parametrize(
    ("adapter", "warning_reference"),
    [
        (
            StaticForgeAdapter(requirement_error=RuntimeError("private requirement failure")),
            "github:review-requirement",
        ),
        (
            StaticForgeAdapter(review_error=RuntimeError("private review failure")),
            "github:reviews",
        ),
        (
            StaticForgeAdapter(check_error=RuntimeError("private check failure")),
            "github:checks",
        ),
    ],
)
def test_unexpected_adapter_failures_are_redacted(
    adapter: StaticForgeAdapter,
    warning_reference: str,
) -> None:
    result = collect_github(adapter, _context())
    warning = next(item for item in result.warnings if item.reference == warning_reference)

    assert warning.code == "ERR-COLLECT-125"
    assert "private" not in repr(result)


class InvalidCheckAdapter(StaticForgeAdapter):
    def fetch_checks(self, repo: str, head_sha: str) -> ForgeCheckData:
        return cast(ForgeCheckData, {"checks": []})


def test_invalid_adapter_check_result_fails_open() -> None:
    result = collect_github(InvalidCheckAdapter(), _context())

    assert result.checks is None
    assert [warning.reference for warning in result.warnings] == ["github:checks"]


class InvalidRequirementAdapter(StaticForgeAdapter):
    def fetch_review_requirement(
        self,
        repo: str,
        base_branch: str,
    ) -> ReviewRequirementData:
        return cast(ReviewRequirementData, {"required": False})


def test_invalid_adapter_requirement_result_fails_open() -> None:
    result = collect_github(InvalidRequirementAdapter(), _context())

    assert result.review.required == "unknown"
    assert [warning.reference for warning in result.warnings] == ["github:review-requirement"]
