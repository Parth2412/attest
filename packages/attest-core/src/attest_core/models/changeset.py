"""ChangeSet wire models governed by SPEC-001 §5.3 and §6.2."""

from __future__ import annotations

import re

from pydantic import Field, StrictBool, field_validator, model_validator

from attest_core.constants import DIGEST_ALGORITHM
from attest_core.models.base import (
    REPOSITORY_PATTERN,
    CanonicalGitPath,
    CanonicalRepository,
    GitMode,
    GitOid,
    NonNegativeInt,
    Sha256Digest,
    WireModel,
)
from attest_core.models.enums import ChangeType, ChangeTypeValue

_INVALID_ADDED_ENTRY = "added entries require null old values and non-null new values"
_INVALID_DELETED_ENTRY = "deleted entries require non-null old values and null new values"
_INVALID_CHANGED_ENTRY = "modified and typechange entries require all transition values"
_INVALID_ALGORITHM = "ChangeSet algorithm must be CSD-1"
_INVALID_REPOSITORY = "repository must be a canonical HTTPS clone URL"
_INVALID_TRUNCATION = "paths must be present when pathsTruncated is true"


class ChangeSetEntry(WireModel):
    """Represent one canonical CSD-1 path transition (REQ-F01-050)."""

    path: CanonicalGitPath
    change_type: ChangeTypeValue
    old_mode: GitMode | None
    new_mode: GitMode | None
    old_blob: GitOid | None
    new_blob: GitOid | None

    @model_validator(mode="after")
    def _validate_transition(self) -> ChangeSetEntry:
        old_values = (self.old_mode, self.old_blob)
        new_values = (self.new_mode, self.new_blob)
        if self.change_type is ChangeType.ADDED and (
            old_values != (None, None) or None in new_values
        ):
            raise ValueError(_INVALID_ADDED_ENTRY)
        if self.change_type is ChangeType.DELETED and (
            new_values != (None, None) or None in old_values
        ):
            raise ValueError(_INVALID_DELETED_ENTRY)
        if self.change_type in (ChangeType.MODIFIED, ChangeType.TYPECHANGE) and (
            None in old_values or None in new_values
        ):
            raise ValueError(_INVALID_CHANGED_ENTRY)
        return self


class ChangeSetRecord(WireModel):
    """Represent the exact context-free CSD-1 digest record (REQ-F01-050)."""

    algorithm: str = Field(strict=True, json_schema_extra={"const": DIGEST_ALGORITHM})
    entries: tuple[ChangeSetEntry, ...]

    @field_validator("algorithm")
    @classmethod
    def _validate_algorithm(cls, value: str) -> str:
        if value != DIGEST_ALGORITHM:
            raise ValueError(_INVALID_ALGORITHM)
        return value


class ChangeSetStats(WireModel):
    """Count ChangeSet entry classes without line statistics (REQ-F01-010)."""

    files_changed: NonNegativeInt
    files_added: NonNegativeInt
    files_modified: NonNegativeInt
    files_deleted: NonNegativeInt


class ChangeSetInfo(WireModel):
    """Represent ChangeSet identity and signed context (REQ-F01-010/080/090)."""

    repository: CanonicalRepository = Field(json_schema_extra={"pattern": REPOSITORY_PATTERN})
    algorithm: str = Field(strict=True, json_schema_extra={"const": DIGEST_ALGORITHM})
    base_commit: GitOid
    head_commit: GitOid
    merge_base: GitOid | None = None
    digest: Sha256Digest
    stats: ChangeSetStats
    paths: tuple[CanonicalGitPath, ...] | None = None
    paths_truncated: StrictBool | None = None

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str) -> str:
        if re.fullmatch(REPOSITORY_PATTERN, value) is None:
            raise ValueError(_INVALID_REPOSITORY)
        return value

    @field_validator("algorithm")
    @classmethod
    def _validate_algorithm(cls, value: str) -> str:
        if value != DIGEST_ALGORITHM:
            raise ValueError(_INVALID_ALGORITHM)
        return value

    @model_validator(mode="after")
    def _validate_truncation(self) -> ChangeSetInfo:
        if self.paths_truncated is True and self.paths is None:
            raise ValueError(_INVALID_TRUNCATION)
        return self
