"""In-toto Statement wire model governed by SPEC-001 §3."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from attest_core.constants import IN_TOTO_STATEMENT_TYPE, PREDICATE_TYPE_V0_1, SUBJECT_NAME
from attest_core.errors import build_error
from attest_core.models.base import Sha256Digest, WireModel
from attest_core.models.predicate import Predicate

_INVALID_SUBJECT_NAME = "Statement subject name must be changeset"
_INVALID_STATEMENT_TYPE = "Statement _type is unsupported"
_INVALID_PREDICATE_TYPE = "Statement predicateType is unsupported"


class DigestSet(WireModel):
    """Contain the sole v0.1 Statement subject digest (REQ-F01-090)."""

    sha256: Sha256Digest


class Subject(WireModel):
    """Identify the literal ChangeSet subject and digest (REQ-F01-110)."""

    name: str = Field(strict=True, json_schema_extra={"const": SUBJECT_NAME})
    digest: DigestSet

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if value != SUBJECT_NAME:
            raise ValueError(_INVALID_SUBJECT_NAME)
        return value


class Statement(WireModel):
    """Bind a complete Predicate to one ChangeSet digest (REQ-F01-100/110)."""

    type_: str = Field(
        alias="_type", strict=True, json_schema_extra={"const": IN_TOTO_STATEMENT_TYPE}
    )
    subject: tuple[Subject, ...] = Field(min_length=1, max_length=1)
    predicate_type: str = Field(strict=True, json_schema_extra={"const": PREDICATE_TYPE_V0_1})
    predicate: Predicate

    @field_validator("type_")
    @classmethod
    def _validate_statement_type(cls, value: str) -> str:
        if value != IN_TOTO_STATEMENT_TYPE:
            raise ValueError(_INVALID_STATEMENT_TYPE)
        return value

    @field_validator("predicate_type")
    @classmethod
    def _validate_predicate_type(cls, value: str) -> str:
        if value != PREDICATE_TYPE_V0_1:
            raise ValueError(_INVALID_PREDICATE_TYPE)
        return value

    @model_validator(mode="after")
    def _validate_digest_binding(self) -> Statement:
        if self.subject[0].digest.sha256 != self.predicate.change_set.digest:
            raise build_error("ERR-BUILD-203")
        return self
