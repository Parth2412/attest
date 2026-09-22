"""Closed intermediate artifacts and canonical serializers for F-10."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final, Literal, Never, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from attest_cli.errors import CliError, cli_error
from attest_cli.safe_io import decode_json_object, read_regular_file
from attest_core import (
    Authorship,
    ChangeSetInfo,
    ChangeSetRecord,
    Check,
    Collection,
    JsonValue,
    Review,
    Statement,
    canonicalize,
    compute_changeset_digest,
    validate_statement_structure,
)

_COLLECTION_LIMIT = 64 * 1024 * 1024
_STATEMENT_LIMIT = 16 * 1024 * 1024
_INCONSISTENT_CHANGESET: Final[str] = "collection artifact ChangeSet context is inconsistent"
_INCOMPLETE_PATHS: Final[str] = "collection artifact paths are not complete and unique"
GitOid = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{40}$")]
NonEmpty = Annotated[str, Field(strict=True, min_length=1)]


def _invalid() -> Never:
    raise TypeError


class ArtifactModel(BaseModel):
    """Provide immutable, closed camel-case artifact behavior."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class CollectionContext(ArtifactModel):
    """Retain one exact caller-selected collection and policy context."""

    base_commit: GitOid
    head_commit: GitOid
    merge_base: GitOid | None
    target_branch: NonEmpty


class CollectionArtifact(ArtifactModel):
    """Carry all deterministic stage inputs required to build and gate."""

    schema_version: Literal["0.1.0"]
    change_set_record: ChangeSetRecord
    change_set: ChangeSetInfo
    authorship: Authorship
    review: Review
    checks: tuple[Check, ...] | None = None
    collection: Collection
    context: CollectionContext

    @model_validator(mode="after")
    def _coherent_changeset(self) -> CollectionArtifact:
        if (
            compute_changeset_digest(self.change_set_record) != self.change_set.digest
            or self.change_set.algorithm != self.change_set_record.algorithm
            or self.context.base_commit != self.change_set.base_commit
            or self.context.head_commit != self.change_set.head_commit
            or self.context.merge_base != self.change_set.merge_base
        ):
            raise ValueError(_INCONSISTENT_CHANGESET)
        record_paths = tuple(entry.path for entry in self.change_set_record.entries)
        if len(record_paths) != len(set(record_paths)):
            raise ValueError(_INCOMPLETE_PATHS)
        return self


def generate_collection_schema() -> dict[str, object]:
    """Generate the Collection Artifact Draft 2020-12 schema."""
    schema = CollectionArtifact.model_json_schema(by_alias=True, mode="validation")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}


def render_collection_schema() -> str:
    """Render deterministic Collection Artifact schema text."""
    return json.dumps(generate_collection_schema(), indent=2, sort_keys=True) + "\n"


def serialize_collection_artifact(artifact: CollectionArtifact) -> bytes:
    """Serialize one artifact as canonical JSON followed by one LF."""
    try:
        artifact_value = cast(object, artifact)
        if not isinstance(artifact_value, CollectionArtifact):
            _invalid()
        wire = cast(
            dict[str, JsonValue],
            artifact.model_dump(mode="json", by_alias=True),
        )
        return canonicalize(wire) + b"\n"
    except CliError:
        raise
    except Exception:
        raise cli_error("ERR-CONFIG-003") from None


def read_collection_artifact(path: Path | str) -> CollectionArtifact:
    """Read and validate one bounded Collection Artifact."""
    try:
        raw = read_regular_file(
            path,
            maximum_size=_COLLECTION_LIMIT,
            error_code="ERR-CONFIG-003",
        )
        return CollectionArtifact.model_validate(decode_json_object(raw))
    except CliError:
        raise
    except Exception:
        raise cli_error("ERR-CONFIG-003") from None


def serialize_statement(statement: Statement) -> bytes:
    """Serialize one validated Statement as canonical JSON followed by one LF."""
    try:
        statement_value = cast(object, statement)
        if not isinstance(statement_value, Statement):
            _invalid()
        wire = cast(dict[str, JsonValue], statement.model_dump(mode="json", by_alias=True))
        validate_statement_structure(cast(dict[str, object], wire), "0.1")
        return canonicalize(wire) + b"\n"
    except CliError:
        raise
    except Exception:
        raise cli_error("ERR-CONFIG-003") from None


def read_statement(path: Path | str) -> Statement:
    """Read one bounded structurally and semantically valid Statement."""
    try:
        raw = read_regular_file(
            path,
            maximum_size=_STATEMENT_LIMIT,
            error_code="ERR-CONFIG-003",
        )
        wire = decode_json_object(raw)
        validate_statement_structure(wire, "0.1")
        return Statement.model_validate(wire)
    except CliError:
        raise
    except Exception:
        raise cli_error("ERR-CONFIG-003") from None
