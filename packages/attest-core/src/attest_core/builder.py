"""Pure deterministic in-toto Statement construction governed by BRD-F05."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from jsonschema import (  # type: ignore[import-untyped]  # pinned package lacks typing metadata
    Draft202012Validator,
    FormatChecker,
)

from attest_core.canonical import JsonValue, canonicalize
from attest_core.constants import (
    IN_TOTO_STATEMENT_TYPE,
    PREDICATE_TYPE_V0_1,
    SCHEMA_VERSION,
    SUBJECT_NAME,
)
from attest_core.errors import BuildError, build_error
from attest_core.models.base import WireModel
from attest_core.models.changeset import ChangeSetInfo
from attest_core.models.predicate import Authorship, Check, Collection, Review
from attest_core.models.statement import Statement
from attest_core.schema import generate_json_schema


def _wire(model: WireModel) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], model.model_dump(mode="json", by_alias=True))


def _canonical_key(value: dict[str, JsonValue]) -> bytes:
    return canonicalize(value)


def _normalise_inputs(
    change_set: object,
    authorship: object,
    review: object,
    checks: object,
    collection: object,
) -> tuple[ChangeSetInfo, Authorship, Review, tuple[Check, ...], Collection]:
    if not isinstance(change_set, ChangeSetInfo):
        raise build_error("ERR-BUILD-211")
    if not isinstance(authorship, Authorship):
        raise build_error("ERR-BUILD-211")
    if not isinstance(review, Review):
        raise build_error("ERR-BUILD-211")
    if not isinstance(collection, Collection):
        raise build_error("ERR-BUILD-211")
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes, bytearray)):
        raise build_error("ERR-BUILD-211")
    normalised_checks = tuple(checks)
    if any(not isinstance(check, Check) for check in normalised_checks):
        raise build_error("ERR-BUILD-211")
    return change_set, authorship, review, cast(tuple[Check, ...], normalised_checks), collection


def _assemble_wire(
    change_set: ChangeSetInfo,
    authorship: Authorship,
    review: Review,
    checks: tuple[Check, ...],
    collection: Collection,
) -> dict[str, JsonValue]:
    authorship_wire = _wire(authorship)
    claim_items = cast(list[dict[str, JsonValue]], authorship_wire["claims"])
    claim_items.sort(key=lambda item: cast(str, item["claimId"]))

    review_wire = _wire(review)
    reviewer_items = cast(list[dict[str, JsonValue]], review_wire["reviewers"])
    reviewer_items.sort(
        key=lambda item: (
            cast(str, item["submittedAt"]),
            cast(str, item["identity"]),
            _canonical_key(item),
        )
    )
    automated_value = review_wire.get("automatedReviews")
    if isinstance(automated_value, list):
        automated_items = cast(list[dict[str, JsonValue]], automated_value)
        if automated_items:
            automated_items.sort(
                key=lambda item: (
                    cast(str, item["submittedAt"]),
                    cast(str, item["tool"]),
                    _canonical_key(item),
                )
            )
        else:
            review_wire.pop("automatedReviews")

    predicate: dict[str, JsonValue] = {
        "schemaVersion": SCHEMA_VERSION,
        "changeSet": _wire(change_set),
        "authorship": authorship_wire,
        "review": review_wire,
        "collection": _wire(collection),
    }
    if checks:
        check_items = [_wire(check) for check in checks]
        check_items.sort(
            key=lambda item: (
                cast(str, item["name"]),
                _canonical_key(item),
            )
        )
        predicate["checks"] = cast(JsonValue, check_items)

    return {
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": SUBJECT_NAME,
                "digest": {"sha256": change_set.digest},
            }
        ],
        "predicateType": PREDICATE_TYPE_V0_1,
        "predicate": predicate,
    }


def _validate_structural(wire: dict[str, JsonValue]) -> None:
    schema = generate_json_schema("0.1")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(wire)


def build_statement(
    change_set: ChangeSetInfo,
    authorship: Authorship,
    review: Review,
    checks: Sequence[Check],
    collection: Collection,
) -> Statement:
    """Build a schema-valid deterministic Statement (REQ-F05-010 through REQ-F05-100)."""
    try:
        change_set, authorship, review, normalised_checks, collection = _normalise_inputs(
            change_set,
            authorship,
            review,
            checks,
            collection,
        )
    except BuildError:
        raise
    except Exception as error:
        raise build_error("ERR-BUILD-211") from error
    try:
        wire = _assemble_wire(change_set, authorship, review, normalised_checks, collection)
        _validate_structural(wire)
        return Statement.model_validate(wire)
    except Exception as error:
        raise build_error("ERR-BUILD-210") from error
