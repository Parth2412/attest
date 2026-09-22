"""GitHub review and check collection governed by BRD-F04 and ADR-041."""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Final, Literal, Protocol, cast, runtime_checkable

from attest_collect._github_http import GitHubHttpClient
from attest_collect._github_http import JsonObject as JsonObject
from attest_collect._strict_json import decode_json
from attest_collect.errors import (
    CollectDiagnosticCode,
    CollectError,
    collect_diagnostic_details,
    collect_error,
)
from attest_core import (
    AutomatedReview,
    Check,
    CheckConclusion,
    JsonValue,
    Review,
    Reviewer,
    ReviewEvidence,
    ReviewState,
    ReviewVerdict,
    canonicalize,
)

type ReviewRequired = bool | Literal["unknown"]
type GitHubDiagnosticCode = Literal[
    "ERR-COLLECT-121",
    "ERR-COLLECT-122",
    "ERR-COLLECT-123",
    "ERR-COLLECT-124",
    "ERR-COLLECT-125",
    "WARN-COLLECT-005",
    "WARN-COLLECT-006",
]
type GitHubWarningCode = Literal["WARN-COLLECT-005", "WARN-COLLECT-006"]

_WARNING_DETAILS: Final[dict[GitHubWarningCode, tuple[str, str]]] = {
    "WARN-COLLECT-005": (
        "A GitHub check run has no terminal predicate conclusion",
        "Retry collection after the check completes",
    ),
    "WARN-COLLECT-006": (
        "A pending GitHub draft review has no submitted verdict",
        "Submit the review before collecting final evidence",
    ),
}
_REVIEW_VERDICTS: Final[dict[str, ReviewVerdict]] = {
    "APPROVED": ReviewVerdict.APPROVED,
    "CHANGES_REQUESTED": ReviewVerdict.CHANGES_REQUESTED,
    "COMMENTED": ReviewVerdict.COMMENTED,
    "DISMISSED": ReviewVerdict.DISMISSED,
}
_NONTERMINAL_CHECK_STATUSES: Final[frozenset[str]] = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)
_CHECK_CONCLUSIONS: Final[dict[str, CheckConclusion]] = {
    "success": CheckConclusion.SUCCESS,
    "failure": CheckConclusion.FAILURE,
    "neutral": CheckConclusion.NEUTRAL,
    "cancelled": CheckConclusion.CANCELLED,
    "skipped": CheckConclusion.SKIPPED,
    "timed_out": CheckConclusion.TIMED_OUT,
    "action_required": CheckConclusion.FAILURE,
    "stale": CheckConclusion.FAILURE,
}


class ReviewContextKind(StrEnum):
    """Distinguish review-bearing, direct-push, and unresolved contexts."""

    PULL_REQUEST = "pull-request"
    DIRECT_PUSH = "direct-push"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class GitHubWarning:
    """Represent one stable, non-secret F-04 degradation."""

    code: GitHubDiagnosticCode
    message: str
    remediation: str
    reference: str


@dataclass(frozen=True, slots=True)
class GitHubReviewContext:
    """Carry explicit, validated GitHub collection inputs (REQ-F04-110/130)."""

    kind: ReviewContextKind
    repository: str
    head_sha: str
    base_branch: str
    change_author_ids: frozenset[str]
    pr_number: int | None = None
    last_commit_pushed_at: datetime | None = None

    def __post_init__(self) -> None:
        try:
            _validate_context(self)
        except CollectError:
            raise
        except Exception as error:
            raise collect_error("ERR-COLLECT-124") from error


@dataclass(frozen=True, slots=True)
class GitHubPullRequestInput:
    """Carry an exact requested GitHub pull-request ChangeSet (REQ-F04-150)."""

    repository: str
    pr_number: int
    base_revision: str
    head_revision: str
    target_branch: str

    def __post_init__(self) -> None:
        if not _valid_context_fields(
            repository=self.repository,
            pr_number=self.pr_number,
            base_revision=self.base_revision,
            head_revision=self.head_revision,
            target_branch=self.target_branch,
        ):
            raise collect_error("ERR-COLLECT-126")


@dataclass(frozen=True, slots=True)
class GitHubChangeSetContext:
    """Return a forge-bound GitHub ChangeSet context (REQ-F04-150)."""

    repository: str
    pr_number: int
    base_revision: str
    head_revision: str
    merge_base_revision: str
    target_branch: str
    change_author_ids: frozenset[str]

    def __post_init__(self) -> None:
        if (
            not _valid_context_fields(
                repository=self.repository,
                pr_number=self.pr_number,
                base_revision=self.base_revision,
                head_revision=self.head_revision,
                target_branch=self.target_branch,
            )
            or not _valid_head_sha(self.merge_base_revision)
            or not _valid_author_ids(self.change_author_ids)
        ):
            raise collect_error("ERR-COLLECT-127")


@dataclass(frozen=True, slots=True)
class ForgeReviewData:
    """Supply complete raw review evidence to the normalizer (REQ-F04-020/060)."""

    responses: tuple[JsonObject, ...]
    required: ReviewRequired
    last_commit_pushed_at: datetime | None

    def __post_init__(self) -> None:
        _validate_required(self.required)
        responses = cast(object, self.responses)
        if not isinstance(responses, tuple) or any(
            not isinstance(response, dict) for response in responses
        ):
            raise collect_error("ERR-COLLECT-125")
        if self.last_commit_pushed_at is not None:
            object.__setattr__(
                self,
                "last_commit_pushed_at",
                _utc_timestamp(self.last_commit_pushed_at),
            )


@dataclass(frozen=True, slots=True)
class ReviewRequirementData:
    """Return branch-rule resolution and degradations (REQ-F04-100/130)."""

    required: ReviewRequired
    warnings: tuple[GitHubWarning, ...]

    def __post_init__(self) -> None:
        _validate_required(self.required)
        warnings = cast(object, self.warnings)
        if not isinstance(warnings, tuple) or any(
            not isinstance(warning, GitHubWarning) for warning in warnings
        ):
            raise collect_error("ERR-COLLECT-125")


@dataclass(frozen=True, slots=True)
class ForgeCheckData:
    """Return normalized terminal checks and omissions (REQ-F04-130/140)."""

    checks: tuple[Check, ...]
    warnings: tuple[GitHubWarning, ...]

    def __post_init__(self) -> None:
        checks = cast(object, self.checks)
        warnings = cast(object, self.warnings)
        if (
            not isinstance(checks, tuple)
            or any(not isinstance(check, Check) for check in checks)
            or not isinstance(warnings, tuple)
            or any(not isinstance(warning, GitHubWarning) for warning in warnings)
        ):
            raise collect_error("ERR-COLLECT-125")


@dataclass(frozen=True, slots=True)
class GitHubCollection:
    """Return review evidence, checks, and forge degradations (REQ-F04-130)."""

    review: Review
    checks: tuple[Check, ...] | None
    warnings: tuple[GitHubWarning, ...]


@runtime_checkable
class ForgeAdapter(Protocol):
    """Define the injectable forge boundary (REQ-F04-070/100/140)."""

    def fetch_reviews(self, repo: str, pr_number: int) -> tuple[JsonObject, ...]:
        """Fetch complete raw submitted and pending review objects."""

    def fetch_review_requirement(
        self,
        repo: str,
        base_branch: str,
    ) -> ReviewRequirementData:
        """Resolve effective classic and ruleset review requirements."""

    def fetch_checks(self, repo: str, head_sha: str) -> ForgeCheckData:
        """Fetch every representable terminal check run."""


@runtime_checkable
class GitHubContextAdapter(Protocol):
    """Define the exact injectable PR/Compare context boundary (REQ-F04-150)."""

    def fetch_pull_request(self, repo: str, pr_number: int) -> JsonObject:
        """Fetch the current pull-request response object."""

    def fetch_comparison_pages(
        self,
        repo: str,
        base_revision: str,
        head_revision: str,
    ) -> tuple[JsonObject, ...]:
        """Fetch all Compare response pages for the requested revisions."""


@dataclass(frozen=True, slots=True)
class _ParsedReview:
    raw: JsonObject
    review_id: int
    user_id: str
    login: str
    account_type: Literal["User", "Bot"]
    verdict: ReviewVerdict
    submitted_at: datetime


def _warning(code: GitHubDiagnosticCode, reference: str) -> GitHubWarning:
    if code in _WARNING_DETAILS:
        message, remediation = _WARNING_DETAILS[code]
    else:
        message, remediation = collect_diagnostic_details(cast(CollectDiagnosticCode, code))
    return GitHubWarning(
        code=code,
        message=message,
        remediation=remediation,
        reference=reference,
    )


def _warning_from_error(error: CollectError, reference: str) -> GitHubWarning:
    return _warning(cast(GitHubDiagnosticCode, error.code), reference)


def _validate_required(value: object) -> None:
    if not isinstance(value, bool) and value != "unknown":
        raise collect_error("ERR-COLLECT-125")


def _valid_repository(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    parts = value.split("/")
    if len(parts) != 2:
        return False
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")
    return all(
        part not in {"", ".", ".."} and all(character in allowed for character in part)
        for part in parts
    )


def _valid_numeric_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and int(value) > 0
        and str(int(value)) == value
    )


def _valid_head_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_branch(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and "*" not in value
        and all(character.isprintable() for character in value)
    )


def _valid_author_ids(value: object) -> bool:
    return isinstance(value, frozenset) and all(_valid_numeric_identity(item) for item in value)


def _valid_context_fields(
    *,
    repository: object,
    pr_number: object,
    base_revision: object,
    head_revision: object,
    target_branch: object,
) -> bool:
    return (
        _valid_repository(repository)
        and isinstance(pr_number, int)
        and not isinstance(pr_number, bool)
        and pr_number > 0
        and _valid_head_sha(base_revision)
        and _valid_head_sha(head_revision)
        and _valid_branch(target_branch)
    )


def _context_object(value: object) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError
    return cast(JsonObject, value)


def _context_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _context_oid(value: object) -> str:
    rendered = _context_string(value)
    if not _valid_head_sha(rendered):
        raise ValueError
    return rendered


def _context_integer(value: object, *, positive: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < int(positive):
        raise ValueError
    return value


def _context_list(value: object) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError
    return value


def _require_context(condition: bool) -> None:
    if not condition:
        raise ValueError


def parse_github_pull_request_event(payload: bytes) -> GitHubPullRequestInput:
    """Parse exact GitHub pull-request event bytes without ambient access (REQ-F04-150)."""
    if not isinstance(payload, bytes):
        raise collect_error("ERR-COLLECT-126")
    try:
        event = _context_object(decode_json(payload.decode("utf-8")))
        repository = _context_string(_context_object(event.get("repository")).get("full_name"))
        pr_number = _context_integer(event.get("number"), positive=True)
        pull_request = _context_object(event.get("pull_request"))
        base = _context_object(pull_request.get("base"))
        head = _context_object(pull_request.get("head"))
        base_repository = _context_string(_context_object(base.get("repo")).get("full_name"))
        _require_context(base_repository == repository)
        return GitHubPullRequestInput(
            repository=repository,
            pr_number=pr_number,
            base_revision=_context_oid(base.get("sha")),
            head_revision=_context_oid(head.get("sha")),
            target_branch=_context_string(base.get("ref")),
        )
    except Exception:
        raise collect_error("ERR-COLLECT-126") from None


def _pull_request_matches(response: object, request: GitHubPullRequestInput) -> bool:
    try:
        pull_request = _context_object(response)
        base = _context_object(pull_request.get("base"))
        head = _context_object(pull_request.get("head"))
        repository = _context_object(base.get("repo"))
        return (
            _context_integer(pull_request.get("number"), positive=True) == request.pr_number
            and _context_string(repository.get("full_name")) == request.repository
            and _context_oid(base.get("sha")) == request.base_revision
            and _context_oid(head.get("sha")) == request.head_revision
            and _context_string(base.get("ref")) == request.target_branch
        )
    except (TypeError, ValueError):
        return False


def _require_pull_request_match(
    response: object,
    request: GitHubPullRequestInput,
) -> None:
    if not _pull_request_matches(response, request):
        raise collect_error("ERR-COLLECT-127")


def _comparison_context(
    value: object,
    request: GitHubPullRequestInput,
) -> tuple[str, frozenset[str]]:
    if not isinstance(value, tuple) or not value:
        raise ValueError
    expected_total: int | None = None
    expected_merge_base: str | None = None
    identities: set[str] = set()
    commit_oids: list[str] = []
    seen_commit_oids: set[str] = set()

    for raw_page in value:
        page = _context_object(raw_page)
        total = _context_integer(page.get("total_commits"), positive=False)
        ahead = _context_integer(page.get("ahead_by"), positive=False)
        if ahead != total:
            raise ValueError
        base = _context_oid(_context_object(page.get("base_commit")).get("sha"))
        merge_base = _context_oid(_context_object(page.get("merge_base_commit")).get("sha"))
        if base != request.base_revision:
            raise ValueError
        if expected_total is None:
            expected_total = total
            expected_merge_base = merge_base
        elif total != expected_total or merge_base != expected_merge_base:
            raise ValueError

        commits = _context_list(page.get("commits"))
        for raw_commit in commits:
            commit = _context_object(raw_commit)
            oid = _context_oid(commit.get("sha"))
            if oid in seen_commit_oids:
                raise ValueError
            seen_commit_oids.add(oid)
            commit_oids.append(oid)
            for role in ("author", "committer"):
                actor = _context_object(commit.get(role))
                identity = _context_integer(actor.get("id"), positive=True)
                identities.add(str(identity))

    if expected_total is None or expected_merge_base is None:
        raise ValueError
    if len(commit_oids) != expected_total:
        raise ValueError
    if expected_total == 0:
        if request.base_revision != request.head_revision:
            raise ValueError
    elif commit_oids[-1] != request.head_revision:
        raise ValueError
    return expected_merge_base, frozenset(identities)


def resolve_github_changeset_context(
    adapter: GitHubContextAdapter,
    request: GitHubPullRequestInput,
) -> GitHubChangeSetContext:
    """Resolve one PR-bound, identity-complete GitHub context (REQ-F04-150)."""
    if not isinstance(request, GitHubPullRequestInput):
        raise collect_error("ERR-COLLECT-126")
    try:
        before = adapter.fetch_pull_request(request.repository, request.pr_number)
        _require_pull_request_match(before, request)
        pages = adapter.fetch_comparison_pages(
            request.repository,
            request.base_revision,
            request.head_revision,
        )
        merge_base, identities = _comparison_context(pages, request)
        after = adapter.fetch_pull_request(request.repository, request.pr_number)
        _require_pull_request_match(after, request)
        return GitHubChangeSetContext(
            repository=request.repository,
            pr_number=request.pr_number,
            base_revision=request.base_revision,
            head_revision=request.head_revision,
            merge_base_revision=merge_base,
            target_branch=request.target_branch,
            change_author_ids=identities,
        )
    except CollectError as error:
        if error.code in {"ERR-COLLECT-121", "ERR-COLLECT-123", "ERR-COLLECT-127"}:
            raise
        raise collect_error("ERR-COLLECT-127") from None
    except Exception:
        raise collect_error("ERR-COLLECT-127") from None


def _validate_context(context: GitHubReviewContext) -> None:
    if not isinstance(cast(object, context.kind), ReviewContextKind) or not _valid_repository(
        context.repository
    ):
        raise collect_error("ERR-COLLECT-124")
    if not _valid_head_sha(context.head_sha):
        raise collect_error("ERR-COLLECT-124")
    if not _valid_branch(context.base_branch):
        raise collect_error("ERR-COLLECT-124")
    if not _valid_author_ids(context.change_author_ids):
        raise collect_error("ERR-COLLECT-124")
    if context.kind is ReviewContextKind.PULL_REQUEST:
        if (
            isinstance(context.pr_number, bool)
            or not isinstance(context.pr_number, int)
            or context.pr_number < 1
        ):
            raise collect_error("ERR-COLLECT-124")
    elif context.pr_number is not None:
        raise collect_error("ERR-COLLECT-124")
    if context.last_commit_pushed_at is not None:
        object.__setattr__(
            context,
            "last_commit_pushed_at",
            _utc_timestamp(context.last_commit_pushed_at),
        )


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise collect_error("ERR-COLLECT-124")
    return value.astimezone(UTC).replace(microsecond=0)


def _response_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise collect_error("ERR-COLLECT-125")
    rendered = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError as error:
        raise collect_error("ERR-COLLECT-125") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise collect_error("ERR-COLLECT-125")
    return parsed.astimezone(UTC).replace(microsecond=0)


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise collect_error("ERR-COLLECT-125")
    return value


def _non_empty_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise collect_error("ERR-COLLECT-125")
    return value


def _evidence_digest(response: JsonObject) -> str:
    digest: str | None = None
    try:
        digest = sha256(canonicalize(cast(JsonValue, response))).hexdigest()
    except Exception:
        digest = None
    if digest is None:
        raise collect_error("ERR-COLLECT-125")
    return digest


def _parse_review(response: JsonObject) -> _ParsedReview | None:
    state = _non_empty_string(response.get("state"))
    if state == "PENDING":
        return None
    verdict = _REVIEW_VERDICTS.get(state)
    if verdict is None:
        raise collect_error("ERR-COLLECT-125")
    user = response.get("user")
    if not isinstance(user, dict):
        raise collect_error("ERR-COLLECT-125")
    review_id = _positive_integer(response.get("id"))
    user_id = str(_positive_integer(user.get("id")))
    login = _non_empty_string(user.get("login"))
    account_type_value = _non_empty_string(user.get("type"))
    if account_type_value not in {"User", "Bot"}:
        raise collect_error("ERR-COLLECT-125")
    submitted_at = _response_timestamp(response.get("submitted_at"))
    return _ParsedReview(
        raw=response,
        review_id=review_id,
        user_id=user_id,
        login=login,
        account_type=cast(Literal["User", "Bot"], account_type_value),
        verdict=verdict,
        submitted_at=submitted_at,
    )


def _author_ids(values: Set[str]) -> frozenset[str]:
    if any(not _valid_numeric_identity(value) for value in values):
        raise collect_error("ERR-COLLECT-125")
    return frozenset(values)


def _aggregate_state(latest: tuple[_ParsedReview, ...]) -> ReviewState:
    verdicts = {review.verdict for review in latest}
    if ReviewVerdict.CHANGES_REQUESTED in verdicts:
        return ReviewState.CHANGES_REQUESTED
    if ReviewVerdict.APPROVED in verdicts:
        return ReviewState.APPROVED
    if ReviewVerdict.COMMENTED in verdicts:
        return ReviewState.COMMENTED
    return ReviewState.NONE


def collect_review(data: ForgeReviewData, change_author_ids: Set[str]) -> Review:
    """Normalize complete GitHub review responses without I/O (REQ-F04-010-060/110)."""
    try:
        author_ids = _author_ids(change_author_ids)
        parsed = tuple(
            review for response in data.responses if (review := _parse_review(response)) is not None
        )
        ordered = tuple(sorted(parsed, key=lambda item: (item.submitted_at, item.review_id)))
        human = tuple(item for item in ordered if item.account_type == "User")
        automated = tuple(item for item in ordered if item.account_type == "Bot")
        latest_by_id: dict[str, _ParsedReview] = {}
        for item in human:
            latest_by_id[item.user_id] = item
        latest = tuple(latest_by_id.values())

        reviewers = tuple(
            Reviewer(
                identity=f"github:{item.user_id}:{item.login}",
                identity_provider="github",
                verdict=item.verdict,
                submitted_at=item.submitted_at,
                effective=item is latest_by_id[item.user_id],
                is_change_author=item.user_id in author_ids,
                evidence=ReviewEvidence(
                    kind="forge-api",
                    digest=_evidence_digest(item.raw),
                ),
            )
            for item in human
        )
        automated_reviews = tuple(
            AutomatedReview(
                tool=item.login,
                verdict=item.verdict,
                findings_digest=_evidence_digest(item.raw),
                submitted_at=item.submitted_at,
            )
            for item in automated
        )
        approved = tuple(item for item in latest if item.verdict is ReviewVerdict.APPROVED)
        latency: int | None = None
        if data.last_commit_pushed_at is not None and approved:
            first_approval = min(item.submitted_at for item in approved)
            difference = int((first_approval - data.last_commit_pushed_at).total_seconds())
            if difference >= 0:
                latency = difference
        return Review(
            required=data.required,
            state=_aggregate_state(latest),
            human_approvals=len(approved),
            reviewers=reviewers,
            automated_reviews=automated_reviews or None,
            review_latency_seconds=latency,
        )
    except CollectError:
        raise
    except Exception:
        failure_code: Literal["ERR-COLLECT-125"] = "ERR-COLLECT-125"
    raise collect_error(failure_code)


def _approval_configuration_required(value: object, *, classic: bool) -> bool:
    if not isinstance(value, dict):
        raise collect_error("ERR-COLLECT-125")
    count = value.get("required_approving_review_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise collect_error("ERR-COLLECT-125")
    code_owner_key = "require_code_owner_reviews" if classic else "require_code_owner_review"
    code_owner = value.get(code_owner_key)
    last_push = value.get("require_last_push_approval")
    if not isinstance(code_owner, bool) or not isinstance(last_push, bool):
        raise collect_error("ERR-COLLECT-125")
    if count > 0 or code_owner or last_push:
        return True
    required_reviewers = value.get("required_reviewers", [])
    if not isinstance(required_reviewers, list):
        raise collect_error("ERR-COLLECT-125")
    for reviewer in required_reviewers:
        if not isinstance(reviewer, dict):
            raise collect_error("ERR-COLLECT-125")
        minimum = reviewer.get("minimum_approvals")
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            raise collect_error("ERR-COLLECT-125")
        if minimum > 0:
            return True
    return False


def _rules_require_review(rules: tuple[JsonObject, ...]) -> bool:
    for rule in rules:
        rule_type = rule.get("type")
        if not isinstance(rule_type, str):
            raise collect_error("ERR-COLLECT-125")
        if rule_type == "pull_request" and _approval_configuration_required(
            rule.get("parameters"),
            classic=False,
        ):
            return True
    return False


def _classic_requires_review(protection: JsonObject | None) -> bool:
    if protection is None:
        return False
    reviews = protection.get("required_pull_request_reviews")
    if reviews is None:
        return False
    return _approval_configuration_required(reviews, classic=True)


def _check_from_response(response: JsonObject) -> Check | None:
    status = _non_empty_string(response.get("status"))
    if status in _NONTERMINAL_CHECK_STATUSES:
        return None
    if status != "completed":
        raise collect_error("ERR-COLLECT-125")
    conclusion_value = _non_empty_string(response.get("conclusion"))
    conclusion = _CHECK_CONCLUSIONS.get(conclusion_value)
    if conclusion is None:
        raise collect_error("ERR-COLLECT-125")
    run_id = _positive_integer(response.get("id"))
    return Check(
        name=_non_empty_string(response.get("name")),
        conclusion=conclusion,
        run_id=str(run_id),
        details_digest=_evidence_digest(response),
    )


class GitHubForgeAdapter:
    """Translate bounded GitHub responses into domain data (REQ-F04-100/140)."""

    def __init__(self, client: GitHubHttpClient) -> None:
        self._client = client

    def fetch_reviews(self, repo: str, pr_number: int) -> tuple[JsonObject, ...]:
        """Fetch every review without normalizing or discarding history."""
        return self._client.fetch_reviews(repo, pr_number)

    def fetch_review_requirement(
        self,
        repo: str,
        base_branch: str,
    ) -> ReviewRequirementData:
        """Combine active rulesets and classic protection (REQ-F04-100)."""
        warnings: list[GitHubWarning] = []
        rules_required: bool | None = None
        classic_required: bool | None = None
        try:
            rules_required = _rules_require_review(
                self._client.fetch_branch_rules(repo, base_branch)
            )
        except CollectError as error:
            warnings.append(_warning_from_error(error, "github:branch-rules"))
        except Exception:
            warnings.append(_warning("ERR-COLLECT-125", "github:branch-rules"))
        try:
            classic_required = _classic_requires_review(
                self._client.fetch_classic_protection(repo, base_branch)
            )
        except CollectError as error:
            warnings.append(_warning_from_error(error, "github:classic-protection"))
        except Exception:
            warnings.append(_warning("ERR-COLLECT-125", "github:classic-protection"))

        if rules_required is True or classic_required is True:
            required: ReviewRequired = True
        elif rules_required is False and classic_required is False:
            required = False
        else:
            required = "unknown"
        return ReviewRequirementData(required=required, warnings=tuple(warnings))

    def fetch_checks(self, repo: str, head_sha: str) -> ForgeCheckData:
        """Collect all terminal runs and warn for nonterminal runs (REQ-F04-140)."""
        checks: list[Check] = []
        warnings: list[GitHubWarning] = []
        for response in self._client.fetch_check_runs(repo, head_sha):
            check = _check_from_response(response)
            if check is None:
                run_id = response.get("id")
                reference = (
                    f"github:check-run:{run_id}"
                    if isinstance(run_id, int) and not isinstance(run_id, bool) and run_id > 0
                    else "github:check-run"
                )
                warnings.append(_warning("WARN-COLLECT-005", reference))
            else:
                checks.append(check)
        return ForgeCheckData(
            checks=tuple(sorted(checks, key=lambda item: (item.name, int(item.run_id)))),
            warnings=tuple(warnings),
        )


def _unknown_review() -> Review:
    return Review(
        required="unknown",
        state=ReviewState.UNKNOWN,
        human_approvals=0,
        reviewers=(),
    )


def _direct_push_review(required: ReviewRequired) -> Review:
    return Review(
        required=required,
        state=ReviewState.NONE,
        human_approvals=0,
        reviewers=(),
    )


def _fetch_requirement(
    adapter: ForgeAdapter,
    context: GitHubReviewContext,
) -> ReviewRequirementData:
    try:
        result = _validated_requirement_data(
            adapter.fetch_review_requirement(context.repository, context.base_branch)
        )
    except CollectError as error:
        return ReviewRequirementData(
            required="unknown",
            warnings=(_warning_from_error(error, "github:review-requirement"),),
        )
    except Exception:
        return ReviewRequirementData(
            required="unknown",
            warnings=(_warning("ERR-COLLECT-125", "github:review-requirement"),),
        )
    else:
        return result


def _validated_requirement_data(value: object) -> ReviewRequirementData:
    if not isinstance(value, ReviewRequirementData):
        raise collect_error("ERR-COLLECT-125")
    return value


def _fetch_checks(
    adapter: ForgeAdapter,
    context: GitHubReviewContext,
) -> tuple[tuple[Check, ...] | None, tuple[GitHubWarning, ...]]:
    try:
        result = _validated_check_data(adapter.fetch_checks(context.repository, context.head_sha))
    except CollectError as error:
        return None, (_warning_from_error(error, "github:checks"),)
    except Exception:
        return None, (_warning("ERR-COLLECT-125", "github:checks"),)
    else:
        return result.checks, result.warnings


def _validated_check_data(value: object) -> ForgeCheckData:
    if not isinstance(value, ForgeCheckData):
        raise collect_error("ERR-COLLECT-125")
    return value


def _pull_request_number(context: GitHubReviewContext) -> int:
    if context.pr_number is None:
        raise collect_error("ERR-COLLECT-124")
    return context.pr_number


def collect_github(adapter: ForgeAdapter, context: GitHubReviewContext) -> GitHubCollection:
    """Collect GitHub evidence while degrading independent forge failures (REQ-F04-130)."""
    warnings: list[GitHubWarning] = []
    if context.kind is ReviewContextKind.UNDETERMINED:
        review = _unknown_review()
        warnings.append(_warning("ERR-COLLECT-124", "github:review-context"))
    else:
        requirement = _fetch_requirement(adapter, context)
        warnings.extend(requirement.warnings)
        if context.kind is ReviewContextKind.DIRECT_PUSH:
            review = _direct_push_review(requirement.required)
        else:
            try:
                responses = adapter.fetch_reviews(
                    context.repository,
                    _pull_request_number(context),
                )
                if any(response.get("state") == "PENDING" for response in responses):
                    warnings.append(_warning("WARN-COLLECT-006", "github:pending-review"))
                review = collect_review(
                    ForgeReviewData(
                        responses=responses,
                        required=requirement.required,
                        last_commit_pushed_at=context.last_commit_pushed_at,
                    ),
                    context.change_author_ids,
                )
            except CollectError as error:
                review = _unknown_review()
                warnings.append(_warning_from_error(error, "github:reviews"))
            except Exception:
                review = _unknown_review()
                warnings.append(_warning("ERR-COLLECT-125", "github:reviews"))

    checks, check_warnings = _fetch_checks(adapter, context)
    warnings.extend(check_warnings)
    return GitHubCollection(review=review, checks=checks, warnings=tuple(warnings))
