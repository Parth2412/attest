"""Shared strict wire-model primitives governed by BRD-F01."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    SerializerFunctionWrapHandler,
    StringConstraints,
    WithJsonSchema,
    model_serializer,
)
from pydantic.alias_generators import to_camel

from attest_core.errors import build_error
from attest_core.path import decode_git_path

SHA256_PATTERN = r"^[0-9a-f]{64}$"
GIT_OID_PATTERN = r"^[0-9a-f]{40}$"
GIT_MODE_PATTERN = r"^[0-7]{6}$"
GIT_PATH_PATTERN = r"^(?:[A-Za-z0-9._~/-]|%[0-9A-F]{2})+$"
SEMVER_PATTERN = (
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
CLAIM_ID_PATTERN = (
    r"^(?:[0-7][0-9A-HJKMNP-TV-Z]{25}|"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-7[0-9A-Fa-f]{3}-"
    r"[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12})$"
)
REPOSITORY_PATTERN = (
    r"^(?!https://[^/]*@)(?!.*\.git$)(?!.*\/$)"
    r"https://[A-Za-z0-9.-]+(?::[0-9]+)?/[^\s/?#]+(?:/[^\s/?#]+)*$"
)
REVIEWER_IDENTITY_PATTERN = r"^[^:]+:[0-9]+:[^:]+$"
UTC_TIMESTAMP_PATTERN = r"^.+(?:Z|[+-][0-9]{2}:[0-9]{2})$"
_EMPTY_GIT_PATH = "Git path must be a non-empty string"
_INVALID_SERIALIZER_OUTPUT = "wire-model serializer must produce an object"

NonEmptyString = Annotated[str, StringConstraints(strict=True, min_length=1)]
Sha256Digest = Annotated[str, StringConstraints(strict=True, pattern=SHA256_PATTERN)]
GitMode = Annotated[str, StringConstraints(strict=True, pattern=GIT_MODE_PATTERN)]
SemVer = Annotated[str, StringConstraints(strict=True, pattern=SEMVER_PATTERN)]
ClaimId = Annotated[str, StringConstraints(strict=True, pattern=CLAIM_ID_PATTERN)]
CanonicalRepository = NonEmptyString
ReviewerIdentity = Annotated[str, StringConstraints(strict=True, pattern=REVIEWER_IDENTITY_PATTERN)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]


def _validate_git_oid(value: object) -> object:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise build_error("ERR-BUILD-202")
    return value


def _validate_git_path(value: object) -> object:
    if not isinstance(value, str) or not value:
        raise ValueError(_EMPTY_GIT_PATH)
    decode_git_path(value)
    return value


GitOid = Annotated[
    str,
    StringConstraints(strict=True, pattern=GIT_OID_PATTERN),
    BeforeValidator(_validate_git_oid),
]
CanonicalGitPath = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=GIT_PATH_PATTERN),
    BeforeValidator(_validate_git_path),
]


def _normalise_timestamp(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(microsecond=0)


def _render_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


UtcTimestamp = Annotated[
    datetime,
    AwareDatetime,
    AfterValidator(_normalise_timestamp),
    PlainSerializer(_render_timestamp, return_type=str, when_used="always"),
    WithJsonSchema(
        {"type": "string", "format": "date-time", "pattern": UTC_TIMESTAMP_PATTERN},
        mode="validation",
    ),
]


def _wire_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in value]
    return value


class WireModel(BaseModel):
    """Provide strict immutable wire behavior for every F-01 model (REQ-F01-010/020)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        rendered = _wire_value(handler(self))
        if not isinstance(rendered, dict):
            raise TypeError(_INVALID_SERIALIZER_OUTPUT)
        for field_name, field_info in type(self).model_fields.items():
            if getattr(self, field_name) is None and not field_info.is_required():
                alias = field_info.serialization_alias or field_info.alias or to_camel(field_name)
                rendered.pop(alias, None)
        return rendered
