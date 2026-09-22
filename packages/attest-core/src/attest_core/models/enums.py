"""Closed wire-format enumerations governed by BRD-F01 §4.2."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator

from attest_core.errors import build_error


class AuthorshipMode(StrEnum):
    """Describe the declared authorship mode (REQ-F01-010/170)."""

    HUMAN_AUTHORED = "human-authored"
    AI_ASSISTED = "ai-assisted"
    AI_AUTHORED = "ai-authored"
    UNKNOWN = "unknown"


class ChangeType(StrEnum):
    """Describe one CSD-1 path transition (REQ-F01-050)."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    TYPECHANGE = "typechange"


class ClaimSourceKind(StrEnum):
    """Identify how an Authorship Claim was collected (REQ-F01-010)."""

    TRAILER = "trailer"
    SIDECAR = "sidecar"
    GIT_NOTE = "git-note"
    FORGE_API = "forge-api"
    MANUAL = "manual"


class ReviewState(StrEnum):
    """Describe the aggregate human-review state (REQ-F01-010)."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    COMMENTED = "commented"
    NONE = "none"
    UNKNOWN = "unknown"


class ReviewVerdict(StrEnum):
    """Describe one human or automated review verdict (REQ-F01-010)."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


class CheckConclusion(StrEnum):
    """Describe a recorded check conclusion (REQ-F01-010)."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class EnvironmentKind(StrEnum):
    """Identify the environment where collection occurred (REQ-F01-010)."""

    GITHUB_ACTIONS = "github-actions"
    GITLAB_CI = "gitlab-ci"
    LOCAL = "local"
    OTHER = "other"


def _closed_enum[EnumType: StrEnum](enum_type: type[EnumType], value: object) -> EnumType:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            pass
    raise build_error("ERR-BUILD-204")


def _authorship_mode(value: object) -> AuthorshipMode:
    return _closed_enum(AuthorshipMode, value)


def _change_type(value: object) -> ChangeType:
    return _closed_enum(ChangeType, value)


def _claim_source_kind(value: object) -> ClaimSourceKind:
    return _closed_enum(ClaimSourceKind, value)


def _review_state(value: object) -> ReviewState:
    return _closed_enum(ReviewState, value)


def _review_verdict(value: object) -> ReviewVerdict:
    return _closed_enum(ReviewVerdict, value)


def _check_conclusion(value: object) -> CheckConclusion:
    return _closed_enum(CheckConclusion, value)


def _environment_kind(value: object) -> EnvironmentKind:
    return _closed_enum(EnvironmentKind, value)


AuthorshipModeValue = Annotated[AuthorshipMode, BeforeValidator(_authorship_mode)]
ChangeTypeValue = Annotated[ChangeType, BeforeValidator(_change_type)]
ClaimSourceKindValue = Annotated[ClaimSourceKind, BeforeValidator(_claim_source_kind)]
ReviewStateValue = Annotated[ReviewState, BeforeValidator(_review_state)]
ReviewVerdictValue = Annotated[ReviewVerdict, BeforeValidator(_review_verdict)]
CheckConclusionValue = Annotated[CheckConclusion, BeforeValidator(_check_conclusion)]
EnvironmentKindValue = Annotated[EnvironmentKind, BeforeValidator(_environment_kind)]
