"""Acceptance tests for deterministic F-05 Statement assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from attest_core import (
    Authorship,
    ChangeSetInfo,
    Check,
    ClaimScope,
    Collection,
    EnvironmentKind,
    JsonValue,
    Review,
    ReviewState,
    Statement,
    build_statement,
    canonicalize,
)
from attest_core.constants import PREDICATE_TYPE_V0_1
from attest_core.errors import BuildError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = Path(__file__).parent / "golden" / "statement-v0.1.jcs"
BUILDER_PATH = REPOSITORY_ROOT / "packages" / "attest-core" / "src" / "attest_core" / "builder.py"


def _inputs(
    data: dict[str, Any],
) -> tuple[ChangeSetInfo, Authorship, Review, tuple[Check, ...], Collection]:
    predicate = data["predicate"]
    return (
        ChangeSetInfo.model_validate(predicate["changeSet"]),
        Authorship.model_validate(predicate["authorship"]),
        Review.model_validate(predicate["review"]),
        tuple(Check.model_validate(item) for item in predicate["checks"]),
        Collection.model_validate(predicate["collection"]),
    )


def _canonical(statement: Statement) -> bytes:
    return canonicalize(cast(JsonValue, statement.model_dump()))


@pytest.mark.ac("AC-F05-010")
def test_builder_is_deterministic_and_matches_committed_golden_statement(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-010: fixed inputs produce identical committed canonical bytes."""
    inputs = _inputs(valid_statement_data)

    first = build_statement(*inputs)
    second = build_statement(*inputs)

    assert first == second
    assert _canonical(first) + b"\n" == GOLDEN_PATH.read_bytes()


@pytest.mark.ac("AC-F05-020")
def test_builder_copies_the_supplied_changeset_digest(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-020: subject digest is copied without ChangeSet recomputation."""
    change_set, authorship, review, checks, collection = _inputs(valid_statement_data)
    supplied_digest = "f" * 64
    changed = change_set.model_copy(update={"digest": supplied_digest})

    statement = build_statement(changed, authorship, review, checks, collection)

    assert statement.subject[0].digest.sha256 == supplied_digest
    assert statement.predicate.change_set.digest == supplied_digest


@pytest.mark.ac("AC-F05-030")
def test_builder_maps_structural_and_semantic_failures_to_safe_error(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-030: both validation layers fail as safe ERR-BUILD-210 errors."""
    change_set, authorship, review, checks, collection = _inputs(valid_statement_data)
    invalid_digest = "not-a-sha256"
    structurally_invalid = change_set.model_copy(update={"digest": invalid_digest})

    with pytest.raises(BuildError) as structural_capture:
        build_statement(structurally_invalid, authorship, review, checks, collection)
    assert structural_capture.value.code == "ERR-BUILD-210"
    assert invalid_digest not in str(structural_capture.value)
    assert structural_capture.value.__cause__ is not None

    invalid_environment = collection.environment.model_copy(
        update={"kind": EnvironmentKind.LOCAL, "trusted": True}
    )
    semantically_invalid = collection.model_copy(update={"environment": invalid_environment})
    with pytest.raises(BuildError) as semantic_capture:
        build_statement(change_set, authorship, review, checks, semantically_invalid)
    assert semantic_capture.value.code == "ERR-BUILD-210"
    assert "local collection environments" not in str(semantic_capture.value)
    assert semantic_capture.value.__cause__ is not None


@pytest.mark.ac("AC-F05-040")
def test_builder_uses_the_single_predicate_type_constant(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-040: the builder imports rather than repeats the predicate URI."""
    statement = build_statement(*_inputs(valid_statement_data))

    assert statement.predicate_type == PREDICATE_TYPE_V0_1
    assert PREDICATE_TYPE_V0_1 not in BUILDER_PATH.read_text(encoding="utf-8")


def _assert_no_null_or_empty_string(value: Any) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_null_or_empty_string(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_null_or_empty_string(nested)
    else:
        assert value is not None
        if isinstance(value, str):
            assert value


@pytest.mark.ac("AC-F05-080")
def test_builder_omits_empty_optional_arrays_but_preserves_empty_paths(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-080: no-data optionals are omitted without changing path semantics."""
    change_set, authorship, review, _, collection = _inputs(valid_statement_data)
    change_set = change_set.model_copy(update={"paths": ()})
    claim = authorship.claims[0].model_copy(update={"scope": ClaimScope(paths=())})
    authorship = authorship.model_copy(update={"claims": (claim,)})
    review = review.model_copy(update={"automated_reviews": ()})

    dumped = build_statement(change_set, authorship, review, (), collection).model_dump()

    _assert_no_null_or_empty_string(dumped)
    predicate = dumped["predicate"]
    assert "checks" not in predicate
    assert "automatedReviews" not in predicate["review"]
    assert predicate["changeSet"]["paths"] == []
    assert predicate["authorship"]["claims"][0]["scope"]["paths"] == []


@pytest.mark.ac("AC-F05-090")
def test_builder_preserves_explicit_unknown_review_and_rejects_missing_inputs(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-090: caller-owned unknown state is preserved and nothing is invented."""
    change_set, authorship, _, checks, collection = _inputs(valid_statement_data)
    unknown = Review(
        required="unknown",
        state=ReviewState.UNKNOWN,
        human_approvals=0,
        reviewers=(),
    )
    statement = build_statement(change_set, authorship, unknown, checks, collection)
    assert statement.predicate.review == unknown

    complete: list[Any] = [change_set, authorship, unknown, checks, collection]
    for missing_index in range(len(complete)):
        arguments = complete.copy()
        arguments[missing_index] = None
        with pytest.raises(BuildError) as captured:
            build_statement(*arguments)
        assert captured.value.code == "ERR-BUILD-211"

    for invalid_checks in ("not-a-check-sequence", [object()]):
        with pytest.raises(BuildError) as captured:
            build_statement(change_set, authorship, unknown, cast(Any, invalid_checks), collection)
        assert captured.value.code == "ERR-BUILD-211"


@pytest.mark.ac("AC-F05-100")
def test_builder_totally_orders_every_input_array_including_ties(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-100: primary-key ties cannot retain caller input order."""
    change_set, authorship, review, checks, collection = _inputs(valid_statement_data)

    first_claim = authorship.claims[0]
    second_claim = first_claim.model_copy(
        update={"claim_id": "01890f5e-7b8a-7cc3-98c4-dc0c0c07398f"}
    )
    claims_forward = (second_claim, first_claim)

    first_reviewer = review.reviewers[0]
    second_reviewer = first_reviewer.model_copy(
        update={
            "effective": False,
            "evidence": first_reviewer.evidence.model_copy(update={"digest": "6" * 64}),
        }
    )
    reviewers_forward = (first_reviewer, second_reviewer)

    assert review.automated_reviews is not None
    first_automated = review.automated_reviews[0]
    second_automated = first_automated.model_copy(update={"findings_digest": "7" * 64})
    automated_forward = (first_automated, second_automated)

    first_check = checks[0]
    second_check = first_check.model_copy(update={"details_digest": "8" * 64})
    checks_forward = (first_check, second_check)

    forward = build_statement(
        change_set,
        authorship.model_copy(update={"claims": claims_forward}),
        review.model_copy(
            update={
                "reviewers": reviewers_forward,
                "automated_reviews": automated_forward,
            }
        ),
        checks_forward,
        collection,
    )
    reversed_input = build_statement(
        change_set,
        authorship.model_copy(update={"claims": tuple(reversed(claims_forward))}),
        review.model_copy(
            update={
                "reviewers": tuple(reversed(reviewers_forward)),
                "automated_reviews": tuple(reversed(automated_forward)),
            }
        ),
        tuple(reversed(checks_forward)),
        collection,
    )

    assert _canonical(forward) == _canonical(reversed_input)
    predicate = forward.model_dump()["predicate"]
    assert [item["claimId"] for item in predicate["authorship"]["claims"]] == [
        second_claim.claim_id,
        first_claim.claim_id,
    ]
    assert [item["evidence"]["digest"] for item in predicate["review"]["reviewers"]] == [
        "6" * 64,
        "3" * 64,
    ]
    assert [item["findingsDigest"] for item in predicate["review"]["automatedReviews"]] == [
        "4" * 64,
        "7" * 64,
    ]
    assert [item["detailsDigest"] for item in predicate["checks"]] == [
        "5" * 64,
        "8" * 64,
    ]


@pytest.mark.ac("AC-F05-110")
def test_builder_requires_effective_markers_on_every_new_reviewer(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F05-110: new Statements cannot emit legacy-unmarked or mixed reviews."""
    change_set, authorship, review, checks, collection = _inputs(valid_statement_data)
    unmarked_reviewer = review.reviewers[0].model_copy(update={"effective": None})
    unmarked = review.model_copy(update={"reviewers": (unmarked_reviewer,)})

    with pytest.raises(BuildError) as unmarked_capture:
        build_statement(change_set, authorship, unmarked, checks, collection)
    assert unmarked_capture.value.code == "ERR-BUILD-210"

    marked_reviewer = review.reviewers[0]
    mixed = Review.model_construct(
        required=review.required,
        state=review.state,
        human_approvals=review.human_approvals,
        reviewers=(marked_reviewer, unmarked_reviewer),
        automated_reviews=review.automated_reviews,
        review_latency_seconds=review.review_latency_seconds,
    )
    with pytest.raises(BuildError) as mixed_capture:
        build_statement(change_set, authorship, mixed, checks, collection)
    assert mixed_capture.value.code == "ERR-BUILD-210"

    built = build_statement(change_set, authorship, review, checks, collection)
    assert all(item.effective is not None for item in built.predicate.review.reviewers)
