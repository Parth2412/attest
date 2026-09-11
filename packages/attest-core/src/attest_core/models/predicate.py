"""AI-authorship predicate wire model governed by SPEC-001 §6."""

from __future__ import annotations

from typing import Literal

from pydantic import StrictBool, model_validator

from attest_core.models.base import (
    CanonicalGitPath,
    ClaimId,
    NonEmptyString,
    NonNegativeInt,
    PositiveInt,
    ReviewerIdentity,
    SemVer,
    Sha256Digest,
    UtcTimestamp,
    WireModel,
)
from attest_core.models.changeset import ChangeSetInfo
from attest_core.models.enums import (
    AuthorshipModeValue,
    CheckConclusionValue,
    ClaimSourceKindValue,
    EnvironmentKind,
    EnvironmentKindValue,
    ReviewStateValue,
    ReviewVerdictValue,
)

_DUPLICATE_CLAIM_ID = "claimId values must be unique within a Statement"
_TRUSTED_LOCAL_ENVIRONMENT = "local collection environments must set trusted to false"


class AgentRef(WireModel):
    """Identify an authoring harness without restricting its name (REQ-F01-010)."""

    name: NonEmptyString
    version: NonEmptyString | None = None


class ModelRef(WireModel):
    """Identify a disclosed model without guessed values (REQ-F01-010)."""

    provider: NonEmptyString
    name: NonEmptyString
    version: NonEmptyString | None = None


class ClaimScope(WireModel):
    """Bind an Authorship Claim to canonical Git paths (REQ-F01-180)."""

    paths: tuple[CanonicalGitPath, ...]


class ClaimSource(WireModel):
    """Record the provenance of an Authorship Claim (REQ-F01-010/090)."""

    kind: ClaimSourceKindValue
    reference: NonEmptyString
    digest: Sha256Digest


class AuthorshipClaim(WireModel):
    """Represent one self-reported Authorship Claim (REQ-F01-010)."""

    claim_id: ClaimId
    agent: AgentRef
    model: ModelRef | None = None
    session_id: NonEmptyString | None = None
    prompt_digest: Sha256Digest | None = None
    scope: ClaimScope | None = None
    source: ClaimSource
    claimed_at: UtcTimestamp | None = None


class Authorship(WireModel):
    """Record explicit authorship evidence state without a mode default (REQ-F01-170)."""

    mode: AuthorshipModeValue
    claims_present: StrictBool
    claims: tuple[AuthorshipClaim, ...]

    @model_validator(mode="after")
    def _validate_unique_claim_ids(self) -> Authorship:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError(_DUPLICATE_CLAIM_ID)
        return self


class ReviewEvidence(WireModel):
    """Bind a reviewer record to forge response evidence (REQ-F01-090)."""

    kind: Literal["forge-api"]
    digest: Sha256Digest


class Reviewer(WireModel):
    """Record one namespaced human reviewer and evidence (REQ-F01-010/070)."""

    identity: ReviewerIdentity
    identity_provider: NonEmptyString
    verdict: ReviewVerdictValue
    submitted_at: UtcTimestamp
    is_change_author: StrictBool
    evidence: ReviewEvidence


class AutomatedReview(WireModel):
    """Record an automated review separately from human approvals (REQ-F01-010/070)."""

    tool: NonEmptyString
    verdict: ReviewVerdictValue
    findings_digest: Sha256Digest
    submitted_at: UtcTimestamp


class Review(WireModel):
    """Represent the complete Review Record structure (REQ-F01-010)."""

    required: StrictBool | Literal["unknown"]
    state: ReviewStateValue
    human_approvals: NonNegativeInt
    reviewers: tuple[Reviewer, ...]
    automated_reviews: tuple[AutomatedReview, ...] | None = None
    review_latency_seconds: NonNegativeInt | None = None


class Check(WireModel):
    """Record one forge check conclusion (REQ-F01-010/090)."""

    name: NonEmptyString
    conclusion: CheckConclusionValue
    run_id: NonEmptyString
    details_digest: Sha256Digest


class CollectorRef(WireModel):
    """Identify the collecting implementation and version (REQ-F01-010)."""

    name: NonEmptyString
    version: NonEmptyString


class EnvironmentRef(WireModel):
    """Describe collection environment trust and forge context (REQ-F01-010)."""

    kind: EnvironmentKindValue
    trusted: StrictBool
    run_id: NonEmptyString | None = None
    run_attempt: PositiveInt | None = None
    workflow_ref: NonEmptyString | None = None
    oidc_issuer: NonEmptyString | None = None
    event_name: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_local_trust(self) -> EnvironmentRef:
        if self.kind is EnvironmentKind.LOCAL and self.trusted:
            raise ValueError(_TRUSTED_LOCAL_ENVIRONMENT)
        return self


class Collection(WireModel):
    """Record where and when predicate data was collected (REQ-F01-070)."""

    collector: CollectorRef
    collected_at: UtcTimestamp
    environment: EnvironmentRef


class Predicate(WireModel):
    """Represent the complete v0.1 AI-authorship predicate (REQ-F01-010)."""

    schema_version: SemVer
    change_set: ChangeSetInfo
    authorship: Authorship
    review: Review
    checks: tuple[Check, ...] | None = None
    collection: Collection
