"""Acceptance tests for strict F-01 wire models."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from attest_core.errors import BuildError
from attest_core.models import (
    AgentRef,
    Authorship,
    AuthorshipClaim,
    AuthorshipMode,
    AutomatedReview,
    ChangeSetEntry,
    ChangeSetInfo,
    ChangeSetRecord,
    ChangeSetStats,
    Check,
    ClaimScope,
    ClaimSource,
    Collection,
    CollectorRef,
    DigestSet,
    EnvironmentRef,
    ModelRef,
    Predicate,
    Review,
    Reviewer,
    ReviewEvidence,
    Statement,
    Subject,
)

MODEL_PATHS: tuple[tuple[type[BaseModel], tuple[str | int, ...]], ...] = (
    (Statement, ()),
    (Subject, ("subject", 0)),
    (DigestSet, ("subject", 0, "digest")),
    (Predicate, ("predicate",)),
    (ChangeSetInfo, ("predicate", "changeSet")),
    (ChangeSetStats, ("predicate", "changeSet", "stats")),
    (Authorship, ("predicate", "authorship")),
    (AuthorshipClaim, ("predicate", "authorship", "claims", 0)),
    (AgentRef, ("predicate", "authorship", "claims", 0, "agent")),
    (ModelRef, ("predicate", "authorship", "claims", 0, "model")),
    (ClaimScope, ("predicate", "authorship", "claims", 0, "scope")),
    (ClaimSource, ("predicate", "authorship", "claims", 0, "source")),
    (Review, ("predicate", "review")),
    (Reviewer, ("predicate", "review", "reviewers", 0)),
    (ReviewEvidence, ("predicate", "review", "reviewers", 0, "evidence")),
    (AutomatedReview, ("predicate", "review", "automatedReviews", 0)),
    (Check, ("predicate", "checks", 0)),
    (Collection, ("predicate", "collection")),
    (CollectorRef, ("predicate", "collection", "collector")),
    (EnvironmentRef, ("predicate", "collection", "environment")),
)
_MISSING_CODED_CONTEXT = "validation error did not retain a coded BuildError"


def _nested(value: dict[str, Any], path: tuple[str | int, ...]) -> dict[str, Any]:
    current: Any = value
    for part in path:
        current = current[part]
    assert isinstance(current, dict)
    return deepcopy(current)


def _coded_context(error: ValidationError) -> BuildError:
    for item in error.errors(include_url=False):
        context_error = item.get("ctx", {}).get("error")
        if isinstance(context_error, BuildError):
            return context_error
    raise AssertionError(_MISSING_CODED_CONTEXT)


def _replace(value: dict[str, Any], path: tuple[str | int, ...], replacement: Any) -> None:
    current: Any = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


@pytest.mark.ac("AC-F01-010")
@pytest.mark.parametrize(("model_type", "path"), MODEL_PATHS)
def test_every_wire_model_forbids_unknown_fields_and_is_frozen(
    model_type: type[BaseModel],
    path: tuple[str | int, ...],
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F01-010: strictness applies to every nested wire object."""
    payload = _nested(valid_statement_data, path)
    payload["unexpectedField"] = True
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)

    valid_model = model_type.model_validate(_nested(valid_statement_data, path))
    field_name = next(iter(model_type.model_fields))
    with pytest.raises(ValidationError):
        setattr(valid_model, field_name, getattr(valid_model, field_name))


@pytest.mark.ac("AC-F01-010")
def test_changeset_record_and_entry_are_strict_and_unknown_enums_are_coded() -> None:
    """REQ-F01-010: digest-record models are strict and enum failures carry ERR-BUILD-204."""
    entry = {
        "path": "src/a.py",
        "changeType": "added",
        "oldMode": None,
        "newMode": "100644",
        "oldBlob": None,
        "newBlob": "1" * 40,
    }
    with pytest.raises(ValidationError):
        ChangeSetEntry.model_validate({**entry, "unknown": True})
    with pytest.raises(ValidationError):
        ChangeSetRecord.model_validate(
            {"algorithm": "CSD-1", "entries": [entry], "baseCommit": "a" * 40}
        )
    with pytest.raises(ValidationError) as captured:
        ChangeSetEntry.model_validate({**entry, "changeType": "renamed"})
    assert _coded_context(captured.value).code == "ERR-BUILD-204"


@pytest.mark.ac("AC-F01-010")
@pytest.mark.parametrize(
    "path",
    [
        ("predicate", "authorship", "mode"),
        ("predicate", "authorship", "claims", 0, "source", "kind"),
        ("predicate", "review", "state"),
        ("predicate", "review", "reviewers", 0, "verdict"),
        ("predicate", "review", "automatedReviews", 0, "verdict"),
        ("predicate", "checks", 0, "conclusion"),
        ("predicate", "collection", "environment", "kind"),
    ],
)
def test_every_closed_statement_enum_retains_err_build_204(
    path: tuple[str | int, ...], valid_statement_data: dict[str, Any]
) -> None:
    """REQ-F01-010: every unknown closed-enum value retains ERR-BUILD-204."""
    value = deepcopy(valid_statement_data)
    _replace(value, path, "future-value")
    with pytest.raises(ValidationError) as captured:
        Statement.model_validate(value)
    assert _coded_context(captured.value).code == "ERR-BUILD-204"


@pytest.mark.ac("AC-F01-020")
def test_alias_serialization_is_default_lossless_and_omits_optional_nulls(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F01-020: default output is canonical wire-keyed data."""
    value = deepcopy(valid_statement_data)
    value["predicate"]["authorship"]["claims"][0]["sessionId"] = None
    value["predicate"]["changeSet"]["mergeBase"] = None
    statement = Statement.model_validate(value)

    dumped = statement.model_dump()
    assert "predicateType" in dumped
    assert "predicate_type" not in dumped
    assert "_type" in dumped
    assert "sha256" in dumped["subject"][0]["digest"]
    assert "sessionId" not in dumped["predicate"]["authorship"]["claims"][0]
    assert "mergeBase" not in dumped["predicate"]["changeSet"]
    assert Statement.model_validate(dumped) == statement


@pytest.mark.ac("AC-F01-020")
def test_every_optional_null_is_omitted_recursively(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F01-020: optional null omission applies throughout the complete Statement."""
    value = deepcopy(valid_statement_data)
    change_set = value["predicate"]["changeSet"]
    change_set.update({"mergeBase": None, "paths": None, "pathsTruncated": None})
    claim = value["predicate"]["authorship"]["claims"][0]
    claim.update(
        {
            "sessionId": None,
            "promptDigest": None,
            "scope": None,
            "claimedAt": None,
        }
    )
    claim["agent"]["version"] = None
    claim["model"]["version"] = None
    review = value["predicate"]["review"]
    review.update({"automatedReviews": None, "reviewLatencySeconds": None})
    value["predicate"]["checks"] = None
    environment = value["predicate"]["collection"]["environment"]
    for key in ("runId", "runAttempt", "workflowRef", "oidcIssuer", "eventName"):
        environment[key] = None

    dumped = Statement.model_validate(value).model_dump()

    def assert_no_null(item: Any) -> None:
        if isinstance(item, dict):
            assert None not in item.values()
            for nested in item.values():
                assert_no_null(nested)
        elif isinstance(item, list):
            for nested in item:
                assert_no_null(nested)

    assert_no_null(dumped)


@pytest.mark.ac("AC-F01-070")
def test_timestamps_reject_naive_values_and_serialize_as_utc_seconds(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F01-070: every timestamp uses aware UTC second precision."""
    naive = deepcopy(valid_statement_data)
    naive["predicate"]["collection"]["collectedAt"] = "2026-09-11T12:00:00"
    with pytest.raises(ValidationError):
        Statement.model_validate(naive)

    offset = deepcopy(valid_statement_data)
    offset["predicate"]["collection"]["collectedAt"] = "2026-09-11T12:34:56.987+05:30"
    dumped = Statement.model_validate(offset).model_dump()
    assert dumped["predicate"]["collection"]["collectedAt"] == "2026-09-11T07:04:56Z"


@pytest.mark.ac("AC-F01-080")
def test_abbreviated_oid_raises_coded_build_error(valid_statement_data: dict[str, Any]) -> None:
    """REQ-F01-080: abbreviated git OIDs are rejected with ERR-BUILD-202."""
    value = deepcopy(valid_statement_data)
    value["predicate"]["changeSet"]["baseCommit"] = "abcdef0"
    with pytest.raises(ValidationError) as captured:
        Statement.model_validate(value)
    assert _coded_context(captured.value).code == "ERR-BUILD-202"


@pytest.mark.ac("AC-F01-090")
def test_uppercase_digest_is_rejected(valid_statement_data: dict[str, Any]) -> None:
    """REQ-F01-090: SHA-256 values are unprefixed lowercase hexadecimal."""
    value = deepcopy(valid_statement_data)
    uppercase = ("ab" * 32).upper()
    value["subject"][0]["digest"]["sha256"] = uppercase
    value["predicate"]["changeSet"]["digest"] = uppercase
    with pytest.raises(ValidationError):
        Statement.model_validate(value)


@pytest.mark.ac("AC-F01-100")
def test_subject_predicate_digest_mismatch_is_coded(
    valid_statement_data: dict[str, Any],
) -> None:
    """REQ-F01-100: runtime validation binds subject and predicate digests."""
    value = deepcopy(valid_statement_data)
    value["predicate"]["changeSet"]["digest"] = "f" * 64
    with pytest.raises(ValidationError) as captured:
        Statement.model_validate(value)
    assert _coded_context(captured.value).code == "ERR-BUILD-203"


@pytest.mark.ac("AC-F01-110")
@pytest.mark.parametrize("subjects", [[], [{"name": "wrong", "digest": {"sha256": "0" * 64}}]])
def test_statement_rejects_invalid_subjects(
    subjects: list[dict[str, Any]], valid_statement_data: dict[str, Any]
) -> None:
    """REQ-F01-110: the Statement has one literal changeset subject."""
    value = deepcopy(valid_statement_data)
    value["subject"] = subjects
    with pytest.raises(ValidationError):
        Statement.model_validate(value)

    value["subject"] = valid_statement_data["subject"] * 2
    with pytest.raises(ValidationError):
        Statement.model_validate(value)


@pytest.mark.ac("AC-F01-150")
def test_build_errors_expose_complete_diagnostics() -> None:
    """REQ-F01-150: coded errors always carry actionable diagnostics."""
    error = BuildError(
        code="ERR-BUILD-201",
        message="Non-canonicalisable value",
        remediation="Use integers",
    )
    assert error.code
    assert error.message
    assert error.remediation
    assert error.code in str(error)


@pytest.mark.ac("AC-F01-170")
def test_authorship_mode_is_explicitly_unknown_without_evidence() -> None:
    """REQ-F01-170: missing evidence is explicit unknown, never a human default."""
    authorship = Authorship(mode=AuthorshipMode.UNKNOWN, claims=(), claims_present=False)
    assert authorship.mode.value == "unknown"
    with pytest.raises(ValidationError):
        Authorship.model_validate({"claims": [], "claimsPresent": False})
