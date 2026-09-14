"""Strict policy configuration and decision contracts governed by BRD-F09."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Final, Literal, Protocol, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic.json_schema import SkipJsonSchema

from attest_core import Statement, decode_git_path, validate_identity_pattern
from attest_core.models.base import CanonicalGitPath
from attest_policy.errors import policy_error
from attest_policy.glob import validate_branch_pattern, validate_path_pattern

OnViolation = Literal["block", "warn"]
PredicateStatus = Literal["passed", "failed", "not-applicable"]
DecisionOutcome = Literal["allow", "warn", "deny"]
DecisionExitCode = Literal[0, 3, 4, 5]
VerificationStatus = Literal["verified", "verified-untrusted-environment", "failed"]
AuthorshipModeName = Literal["human-authored", "ai-assisted", "ai-authored", "unknown"]
PredicateName = Literal[
    "match.branches",
    "match.paths",
    "require.attestation",
    "require.environment.trusted",
    "require.signer.issuer",
    "require.signer.identity",
    "require.transparencyLog",
    "require.review.when.authorshipMode",
    "require.review.minHumanApprovals",
    "require.review.approverMustNotBeAuthor",
    "require.authorship.claimsRequired",
    "require.checks.mustPass",
]
ReasonCode = Literal[
    "matched",
    "not-matched",
    "verification-failed",
    "policy-not-matched",
    "requirement-disabled",
    "review-condition-met",
    "review-condition-not-met",
    "attestation-present",
    "attestation-missing",
    "environment-trusted",
    "environment-untrusted-or-unknown",
    "signer-issuer-matched",
    "signer-issuer-mismatched",
    "signer-identity-matched",
    "signer-identity-mismatched",
    "transparency-log-verified",
    "transparency-log-unverified",
    "approvals-satisfied",
    "approvals-insufficient",
    "non-author-approvals-satisfied",
    "non-author-approvals-insufficient",
    "effective-review-state-missing",
    "claims-present",
    "claims-missing",
    "checks-passed",
    "check-missing",
    "check-not-successful",
]

PREDICATE_NAMES: Final[tuple[PredicateName, ...]] = (
    "match.branches",
    "match.paths",
    "require.attestation",
    "require.environment.trusted",
    "require.signer.issuer",
    "require.signer.identity",
    "require.transparencyLog",
    "require.review.when.authorshipMode",
    "require.review.minHumanApprovals",
    "require.review.approverMustNotBeAuthor",
    "require.authorship.claimsRequired",
    "require.checks.mustPass",
)
REASON_CODES: Final[tuple[ReasonCode, ...]] = (
    "matched",
    "not-matched",
    "verification-failed",
    "policy-not-matched",
    "requirement-disabled",
    "review-condition-met",
    "review-condition-not-met",
    "attestation-present",
    "attestation-missing",
    "environment-trusted",
    "environment-untrusted-or-unknown",
    "signer-issuer-matched",
    "signer-issuer-mismatched",
    "signer-identity-matched",
    "signer-identity-mismatched",
    "transparency-log-verified",
    "transparency-log-unverified",
    "approvals-satisfied",
    "approvals-insufficient",
    "non-author-approvals-satisfied",
    "non-author-approvals-insufficient",
    "effective-review-state-missing",
    "claims-present",
    "claims-missing",
    "checks-passed",
    "check-missing",
    "check-not-successful",
)

NonEmptyString = Annotated[str, StringConstraints(strict=True, min_length=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
_EMPTY_OBJECT = "policy configuration object must not be empty"
_DUPLICATE_VALUES = "policy list values must be unique"
_NESTED_REQUIRES_ATTESTATION = "nested requirements require attestation true"
_INVALID_SEPARATION_MINIMUM = "review separation requires at least one human approval"
_DUPLICATE_POLICY_ID = "policy IDs must be unique"
_NULL_FIELD = "policy fields cannot be null"
_INVALID_VERSION = "policy version must be strict integer 1"


class PolicyModel(BaseModel):
    """Provide immutable closed policy configuration behavior (REQ-F09-020)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_nulls(cls, value: object) -> object:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError(_NULL_FIELD)
        return value


class PolicyMatch(PolicyModel):
    """Select a policy by target branch and complete changed paths."""

    branches: tuple[NonEmptyString, ...] = Field(min_length=1)
    paths: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("branches")
    @classmethod
    def _validate_branches(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError(_DUPLICATE_VALUES)
        for value in values:
            validate_branch_pattern(value)
        return values

    @field_validator("paths")
    @classmethod
    def _validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError(_DUPLICATE_VALUES)
        for value in values:
            validate_path_pattern(value)
        return values


class EnvironmentRequirement(PolicyModel):
    """Require the signed producer environment to be trusted."""

    trusted: StrictBool


class SignerRequirement(PolicyModel):
    """Require F-08 verified exact issuer and bounded identity evidence."""

    issuer: NonEmptyString
    identity: NonEmptyString

    @field_validator("identity")
    @classmethod
    def _validate_identity(cls, value: str) -> str:
        validate_identity_pattern(value)
        return value


class ReviewWhen(PolicyModel):
    """Condition review requirements on signed authorship mode."""

    authorship_mode: tuple[AuthorshipModeName, ...] = Field(min_length=1)

    @field_validator("authorship_mode")
    @classmethod
    def _validate_unique_modes(
        cls, values: tuple[AuthorshipModeName, ...]
    ) -> tuple[AuthorshipModeName, ...]:
        if len(values) != len(set(values)):
            raise ValueError(_DUPLICATE_VALUES)
        return values


class ReviewRequirement(PolicyModel):
    """Configure conditional approval and separation predicates."""

    when: ReviewWhen | SkipJsonSchema[None] = None
    min_human_approvals: NonNegativeInt | SkipJsonSchema[None] = None
    approver_must_not_be_author: StrictBool | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def _validate_review(self) -> ReviewRequirement:
        if not self.model_fields_set:
            raise ValueError(_EMPTY_OBJECT)
        if self.approver_must_not_be_author is True and (
            self.min_human_approvals is None or self.min_human_approvals < 1
        ):
            raise ValueError(_INVALID_SEPARATION_MINIMUM)
        return self


class AuthorshipRequirement(PolicyModel):
    """Require the signed authorship claims-presence flag."""

    claims_required: StrictBool


class ChecksRequirement(PolicyModel):
    """Require exact named retained check records to all pass."""

    must_pass: tuple[NonEmptyString, ...] = Field(min_length=1)

    @field_validator("must_pass")
    @classmethod
    def _validate_unique_checks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError(_DUPLICATE_VALUES)
        return values


class PolicyRequirements(PolicyModel):
    """Hold the closed set of configurable policy predicates."""

    attestation: StrictBool | SkipJsonSchema[None] = None
    environment: EnvironmentRequirement | SkipJsonSchema[None] = None
    signer: SignerRequirement | SkipJsonSchema[None] = None
    transparency_log: StrictBool | SkipJsonSchema[None] = None
    review: ReviewRequirement | SkipJsonSchema[None] = None
    authorship: AuthorshipRequirement | SkipJsonSchema[None] = None
    checks: ChecksRequirement | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def _validate_requirements(self) -> PolicyRequirements:
        if not self.model_fields_set:
            raise ValueError(_EMPTY_OBJECT)
        nested = (self.environment, self.signer, self.review, self.authorship, self.checks)
        if (
            any(value is not None for value in nested) or self.transparency_log is not None
        ) and self.attestation is not True:
            raise ValueError(_NESTED_REQUIRES_ATTESTATION)
        return self


class Policy(PolicyModel):
    """Represent one ordered version 1 policy rule (REQ-F09-020/170)."""

    id: NonEmptyString
    description: NonEmptyString | SkipJsonSchema[None] = None
    match: PolicyMatch
    require: PolicyRequirements
    on_violation: OnViolation


class PolicyDocument(PolicyModel):
    """Represent the strict public policy version 1 document (REQ-F09-020/170)."""

    version: Literal[1]
    policies: tuple[Policy, ...]

    @field_validator("version", mode="before")
    @classmethod
    def _validate_strict_version(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int) or value != 1:
            raise ValueError(_INVALID_VERSION)
        return value

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> PolicyDocument:
        identifiers = tuple(policy.id for policy in self.policies)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(_DUPLICATE_POLICY_ID)
        return self


class VerificationView(Protocol):
    """Describe only successful verified evidence consumed by F-09 (REQ-F09-150/160)."""

    status: VerificationStatus
    statement: Statement | None
    failure_code: str | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: bool


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Carry caller-selected matching context from the recomputed ChangeSet (REQ-F09-150)."""

    target_branch: str
    changed_paths: tuple[CanonicalGitPath, ...]

    def __post_init__(self) -> None:
        _validate_context(self.target_branch, self.changed_paths)


def _validate_context(target_branch: object, changed_paths: object) -> None:
    if (
        not isinstance(target_branch, str)
        or not target_branch
        or not isinstance(changed_paths, tuple)
    ):
        raise policy_error("ERR-POLICY-604")
    try:
        decoded = tuple(
            decode_git_path(path) for path in changed_paths if isinstance(path, str) and bool(path)
        )
    except (TypeError, ValueError):
        raise policy_error("ERR-POLICY-604") from None
    if (
        len(decoded) != len(changed_paths)
        or len(decoded) != len(set(decoded))
        or decoded != tuple(sorted(decoded))
    ):
        raise policy_error("ERR-POLICY-604")


@dataclass(frozen=True, slots=True)
class PolicySource:
    """Identify exact policy input bytes without retaining their content (REQ-F09-100)."""

    path: str | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class LoadedPolicy:
    """Pair a parsed document with source evidence and notice (REQ-F09-100/120)."""

    document: PolicyDocument | None
    source: PolicySource
    reporting_only_notice: str | None


@dataclass(frozen=True, slots=True)
class PredicateResult:
    """Report one stable policy predicate result (REQ-F09-060)."""

    name: PredicateName
    status: PredicateStatus
    reason: ReasonCode
    detail: str | None


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Report one policy and all of its ordered predicates (REQ-F09-050/060)."""

    policy_id: str
    matched: bool | None
    on_violation: OnViolation
    predicates: tuple[PredicateResult, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    """Return the deterministic aggregate enforcement decision (REQ-F09-030)."""

    outcome: DecisionOutcome
    exit_code: DecisionExitCode
    source: PolicySource
    notice: str | None
    policies: tuple[PolicyResult, ...]


def generate_policy_json_schema() -> dict[str, object]:
    """Generate the Draft 2020-12 policy schema from strict models (REQ-F09-020)."""
    generated = PolicyDocument.model_json_schema(by_alias=True, mode="validation")
    return cast(
        dict[str, object],
        {"$schema": "https://json-schema.org/draft/2020-12/schema", **generated},
    )


def render_policy_json_schema() -> str:
    """Render deterministic committed policy schema text (REQ-F09-020)."""
    return json.dumps(generate_policy_json_schema(), indent=2, sort_keys=True) + "\n"
