"""Acceptance tests for deterministic F-09 policy evaluation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]  # AC-F09-060: PyYAML lacks typing metadata

from attest_core import Check, Statement, canonicalize
from attest_policy import (
    PREDICATE_NAMES,
    REASON_CODES,
    Decision,
    LoadedPolicy,
    PolicyContext,
    PolicyError,
    PredicateResult,
    evaluate,
    load_policy,
)


def _loaded(value: dict[str, Any]) -> LoadedPolicy:
    return load_policy(cast(str, yaml.safe_dump(value, sort_keys=False)).encode())


def _single_result(decision: Decision, name: str) -> PredicateResult:
    return next(item for item in decision.policies[0].predicates if item.name == name)


@pytest.mark.ac("AC-F09-060")
def test_success_snapshot_has_every_predicate_in_normative_order(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    decision = evaluate(verified_view, _loaded(policy_data), policy_context)
    results = decision.policies[0].predicates

    assert decision.outcome == "allow"
    assert decision.exit_code == 0
    assert [(item.name, item.status, item.reason, item.detail) for item in results] == [
        ("match.branches", "passed", "matched", None),
        ("match.paths", "passed", "matched", None),
        ("require.attestation", "passed", "attestation-present", None),
        ("require.environment.trusted", "passed", "environment-trusted", None),
        ("require.signer.issuer", "passed", "signer-issuer-matched", None),
        ("require.signer.identity", "passed", "signer-identity-matched", None),
        ("require.transparencyLog", "passed", "transparency-log-verified", None),
        ("require.review.when.authorshipMode", "passed", "review-condition-met", None),
        ("require.review.minHumanApprovals", "passed", "approvals-satisfied", None),
        (
            "require.review.approverMustNotBeAuthor",
            "passed",
            "non-author-approvals-satisfied",
            None,
        ),
        ("require.authorship.claimsRequired", "passed", "claims-present", None),
        ("require.checks.mustPass", "passed", "checks-passed", "unit-tests"),
    ]


@pytest.mark.ac("AC-F09-060")
def test_closed_predicate_and_reason_vocabularies_are_exact() -> None:
    assert PREDICATE_NAMES == (
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
    assert REASON_CODES == (
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


@pytest.mark.ac("AC-F09-060")
@pytest.mark.parametrize(
    ("target", "paths", "branch_status", "path_status"),
    [
        ("other", ("src/a.py",), "failed", "passed"),
        ("main", (), "passed", "failed"),
    ],
)
def test_nonmatching_policy_reports_match_failures_and_skips_requirements(
    target: str,
    paths: tuple[str, ...],
    branch_status: str,
    path_status: str,
    policy_data: dict[str, Any],
    verified_view: Any,
) -> None:
    decision = evaluate(
        verified_view,
        _loaded(policy_data),
        PolicyContext(target_branch=target, changed_paths=paths),
    )

    assert (decision.outcome, decision.exit_code, decision.policies[0].matched) == (
        "allow",
        0,
        False,
    )
    assert decision.policies[0].predicates[0].status == branch_status
    assert decision.policies[0].predicates[1].status == path_status
    assert any(item.reason == "not-matched" for item in decision.policies[0].predicates[:2])
    assert all(
        item.status == "not-applicable" and item.reason == "policy-not-matched"
        for item in decision.policies[0].predicates[2:]
    )


@pytest.mark.ac("AC-F09-060")
def test_false_boolean_requirements_are_explicit_no_ops(
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    policy = policy_data["policies"][0]
    policy["require"] = {"attestation": False}
    attestation = _single_result(
        evaluate(verified_view, _loaded(policy_data), policy_context),
        "require.attestation",
    )
    assert (attestation.status, attestation.reason) == (
        "not-applicable",
        "requirement-disabled",
    )

    policy["require"] = {
        "attestation": True,
        "environment": {"trusted": False},
        "transparencyLog": False,
        "review": {"minHumanApprovals": 1, "approverMustNotBeAuthor": False},
        "authorship": {"claimsRequired": False},
    }
    results = evaluate(verified_view, _loaded(policy_data), policy_context).policies[0].predicates
    disabled = {
        "require.environment.trusted",
        "require.transparencyLog",
        "require.review.approverMustNotBeAuthor",
        "require.authorship.claimsRequired",
    }
    assert {
        item.name
        for item in results
        if item.status == "not-applicable" and item.reason == "requirement-disabled"
    } == disabled


@pytest.mark.ac("AC-F09-060")
def test_unmet_review_condition_skips_every_dependent_review_predicate(
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    policy_data["policies"][0]["require"] = {
        "attestation": True,
        "review": {
            "when": {"authorshipMode": ["ai-authored"]},
            "minHumanApprovals": 1,
            "approverMustNotBeAuthor": True,
        },
    }
    results = evaluate(verified_view, _loaded(policy_data), policy_context).policies[0].predicates
    review_results = results[3:]

    assert [item.name for item in review_results] == [
        "require.review.when.authorshipMode",
        "require.review.minHumanApprovals",
        "require.review.approverMustNotBeAuthor",
    ]
    assert all(
        item.status == "not-applicable" and item.reason == "review-condition-not-met"
        for item in review_results
    )


@pytest.mark.ac("AC-F09-030")
@pytest.mark.parametrize(
    ("violation", "outcome", "exit_code"),
    [("block", "deny", 5), ("warn", "warn", 0)],
)
def test_missing_attestation_exit_depends_on_matching_violation_mode(
    violation: str,
    outcome: str,
    exit_code: int,
    policy_data: dict[str, Any],
    policy_context: PolicyContext,
) -> None:
    policy_data["policies"][0]["require"] = {"attestation": True}
    policy_data["policies"][0]["onViolation"] = violation
    decision = evaluate(None, _loaded(policy_data), policy_context)

    assert decision.outcome == outcome
    assert decision.exit_code == exit_code
    assert _single_result(decision, "require.attestation").reason == "attestation-missing"


@pytest.mark.ac("AC-F09-040")
def test_verification_failure_precedes_matching_and_predicate_evaluation(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    failed = replace(
        verified_view,
        status="failed",
        statement=None,
        failure_code="ERR-VERIFY-013",
        verified_identity=None,
        verified_issuer=None,
        transparency_log_verified=False,
    )
    decision = evaluate(failed, _loaded(policy_data), policy_context)

    assert decision.outcome == "deny"
    assert decision.exit_code == 4
    assert decision.policies[0].matched is None
    assert all(item.status == "not-applicable" for item in decision.policies[0].predicates)
    assert all(item.reason == "verification-failed" for item in decision.policies[0].predicates)


@pytest.mark.ac("AC-F09-050")
def test_every_matching_policy_is_reported_and_block_has_precedence(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    first = policy_data["policies"][0]
    first["require"] = {
        "attestation": True,
        "signer": {"issuer": "near-miss", "identity": "near-miss"},
    }
    first["onViolation"] = "warn"
    second = deepcopy(first)
    second["id"] = "POL-BLOCK-002"
    second["onViolation"] = "block"
    policy_data["policies"].append(second)

    decision = evaluate(verified_view, _loaded(policy_data), policy_context)
    assert decision.outcome == "deny"
    assert decision.exit_code == 3
    assert [item.policy_id for item in decision.policies] == ["POL-MAIN-001", "POL-BLOCK-002"]
    assert all(item.matched is True for item in decision.policies)


@pytest.mark.ac("AC-F09-070")
def test_warning_only_failure_is_visible_but_nonblocking(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    policy = policy_data["policies"][0]
    policy["require"] = {"attestation": True, "checks": {"mustPass": ["missing"]}}
    policy["onViolation"] = "warn"
    decision = evaluate(verified_view, _loaded(policy_data), policy_context)

    assert decision.outcome == "warn"
    assert decision.exit_code == 0
    result = _single_result(decision, "require.checks.mustPass")
    assert (result.status, result.reason, result.detail) == ("failed", "check-missing", "missing")


@pytest.mark.ac("AC-F09-060")
@pytest.mark.parametrize(
    ("case", "name", "reason"),
    [
        (
            "environment",
            "require.environment.trusted",
            "environment-untrusted-or-unknown",
        ),
        ("approvals", "require.review.minHumanApprovals", "approvals-insufficient"),
        (
            "non-author",
            "require.review.approverMustNotBeAuthor",
            "non-author-approvals-insufficient",
        ),
        ("claims", "require.authorship.claimsRequired", "claims-missing"),
    ],
)
def test_signed_predicate_failures_use_the_closed_reason_codes(
    case: str,
    name: str,
    reason: str,
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    statement = verified_view.statement
    assert statement is not None
    predicate = statement.predicate
    status = verified_view.status
    if case == "environment":
        environment = predicate.collection.environment.model_copy(update={"trusted": False})
        collection = predicate.collection.model_copy(update={"environment": environment})
        predicate = predicate.model_copy(update={"collection": collection})
        status = "verified-untrusted-environment"
    elif case == "approvals":
        review = predicate.review.model_copy(update={"human_approvals": 0})
        predicate = predicate.model_copy(update={"review": review})
    elif case == "non-author":
        reviewers = tuple(
            reviewer.model_copy(update={"is_change_author": True})
            for reviewer in predicate.review.reviewers
        )
        review = predicate.review.model_copy(update={"reviewers": reviewers})
        predicate = predicate.model_copy(update={"review": review})
    else:
        authorship = predicate.authorship.model_copy(update={"claims_present": False, "claims": ()})
        predicate = predicate.model_copy(update={"authorship": authorship})
    changed = statement.model_copy(update={"predicate": predicate})
    view = replace(verified_view, status=status, statement=changed)

    result = _single_result(evaluate(view, _loaded(policy_data), policy_context), name)
    assert (result.status, result.reason) == ("failed", reason)


@pytest.mark.ac("AC-F09-110")
def test_separation_uses_effective_distinct_ids_and_legacy_fails_closed(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    statement = verified_view.statement
    assert statement is not None
    source = statement.model_dump()
    base_reviewer = source["predicate"]["review"]["reviewers"][0]
    superseded_self = deepcopy(base_reviewer)
    superseded_self.update(
        {
            "identity": "github:12345:old-login",
            "effective": False,
            "isChangeAuthor": True,
            "submittedAt": "2026-09-11T06:03:00Z",
            "evidence": {"kind": "forge-api", "digest": "6" * 64},
        }
    )
    effective_self = deepcopy(base_reviewer)
    effective_self.update(
        {
            "identity": "github:12345:new-login",
            "verdict": "dismissed",
            "effective": True,
            "isChangeAuthor": True,
            "evidence": {"kind": "forge-api", "digest": "7" * 64},
        }
    )
    non_author = deepcopy(base_reviewer)
    non_author.update(
        {
            "identity": "github:67890:alice",
            "effective": True,
            "isChangeAuthor": False,
            "evidence": {"kind": "forge-api", "digest": "8" * 64},
        }
    )
    source["predicate"]["review"]["reviewers"] = [
        superseded_self,
        effective_self,
        non_author,
    ]
    source["predicate"]["review"]["humanApprovals"] = 1
    marked_statement = Statement.model_validate(source)
    marked = replace(verified_view, statement=marked_statement)

    decision = evaluate(marked, _loaded(policy_data), policy_context)
    assert _single_result(decision, "require.review.approverMustNotBeAuthor").status == "passed"

    legacy_wire = marked_statement.model_dump()
    for reviewer in legacy_wire["predicate"]["review"]["reviewers"]:
        reviewer.pop("effective")
    legacy = replace(verified_view, statement=Statement.model_validate(legacy_wire))
    legacy_result = _single_result(
        evaluate(legacy, _loaded(policy_data), policy_context),
        "require.review.approverMustNotBeAuthor",
    )
    assert (legacy_result.status, legacy_result.reason) == (
        "failed",
        "effective-review-state-missing",
    )


@pytest.mark.ac("AC-F09-140")
def test_policy_evaluation_cannot_mutate_statement_or_changeset_digest(
    policy_data: dict[str, Any], verified_view: Any, policy_context: PolicyContext
) -> None:
    statement = verified_view.statement
    assert statement is not None
    before = canonicalize(statement.model_dump())
    digest = statement.predicate.change_set.digest

    evaluate(verified_view, _loaded(policy_data), policy_context)
    policy_data["policies"][0]["match"]["paths"] = ["docs/**"]
    evaluate(verified_view, _loaded(policy_data), policy_context)

    assert canonicalize(statement.model_dump()) == before
    assert statement.predicate.change_set.digest == digest


@pytest.mark.ac("AC-F09-150")
def test_complete_context_controls_matching_and_invalid_context_or_view_is_rejected(
    policy_data: dict[str, Any], verified_view: Any
) -> None:
    statement = verified_view.statement
    assert statement is not None
    changed = statement.predicate.change_set.model_copy(
        update={"paths": ("src/a.py",), "paths_truncated": True}
    )
    truncated = statement.model_copy(
        update={"predicate": statement.predicate.model_copy(update={"change_set": changed})}
    )
    view = replace(verified_view, statement=truncated)
    policy_data["policies"][0]["match"]["paths"] = ["infra/**"]
    context = PolicyContext(target_branch="main", changed_paths=("infra/prod.yml",))
    assert evaluate(view, _loaded(policy_data), context).policies[0].matched is True

    invalid_contexts = [
        ("", ("a",)),
        ("main", ("a", "a")),
        ("main", ("%61",)),
        ("main", ("b", "a")),
    ]
    for target, paths in invalid_contexts:
        with pytest.raises(PolicyError) as captured:
            PolicyContext(target_branch=target, changed_paths=paths)
        assert captured.value.code == "ERR-POLICY-604"

    inconsistent = replace(verified_view, statement=None)
    with pytest.raises(PolicyError) as captured:
        evaluate(inconsistent, _loaded(policy_data), context)
    assert captured.value.code == "ERR-POLICY-604"


@pytest.mark.ac("AC-F09-150")
def test_every_inconsistent_verification_view_is_rejected(
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    inconsistent_views = (
        replace(verified_view, statement=None),
        replace(verified_view, failure_code="ERR-VERIFY-013"),
        replace(verified_view, status="verified-untrusted-environment"),
        replace(verified_view, status="failed", failure_code="ERR-VERIFY-013"),
        replace(
            verified_view,
            status="failed",
            statement=None,
            failure_code=None,
            verified_identity=None,
            verified_issuer=None,
            transparency_log_verified=False,
        ),
        replace(verified_view, transparency_log_verified=cast(Any, "true")),
        replace(verified_view, verified_identity=""),
    )

    for view in inconsistent_views:
        with pytest.raises(PolicyError) as captured:
            evaluate(view, _loaded(policy_data), policy_context)
        assert captured.value.code == "ERR-POLICY-604"

    loaded = _loaded(policy_data)
    for invalid_policy, invalid_context in (
        (cast(Any, None), policy_context),
        (loaded, cast(Any, None)),
    ):
        with pytest.raises(PolicyError) as captured:
            evaluate(verified_view, invalid_policy, invalid_context)
        assert captured.value.code == "ERR-POLICY-604"


@pytest.mark.ac("AC-F09-160")
@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("issuer", "signer-issuer-mismatched"),
        ("identity", "signer-identity-mismatched"),
        ("log", "transparency-log-unverified"),
    ],
)
def test_verified_signer_and_log_evidence_fail_closed_on_near_miss(
    case: str,
    reason: str,
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    if case == "issuer":
        view = replace(verified_view, verified_issuer="https://token.actions.example.com")
        name = "require.signer.issuer"
    elif case == "identity":
        view = replace(
            verified_view,
            verified_identity=(
                "https://github.com/Org/Other/.github/workflows/attest.yml@refs/heads/main"
            ),
        )
        name = "require.signer.identity"
    else:
        view = replace(verified_view, transparency_log_verified=False)
        name = "require.transparencyLog"
    result = _single_result(evaluate(view, _loaded(policy_data), policy_context), name)
    assert (result.status, result.reason) == ("failed", reason)


@pytest.mark.ac("AC-F09-180")
def test_required_checks_produce_one_result_in_declaration_order(
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    statement = verified_view.statement
    assert statement is not None
    assert statement.predicate.checks is not None
    unit = statement.predicate.checks[0]
    lint = unit.model_copy(update={"name": "lint"})
    checks = (lint, unit)
    changed = statement.model_copy(
        update={
            "predicate": statement.predicate.model_copy(update={"checks": checks}),
        }
    )
    view = replace(verified_view, statement=changed)
    policy_data["policies"][0]["require"] = {
        "attestation": True,
        "checks": {"mustPass": ["lint", "unit-tests"]},
    }

    results = evaluate(view, _loaded(policy_data), policy_context).policies[0].predicates[3:]
    assert [(item.detail, item.status, item.reason) for item in results] == [
        ("lint", "passed", "checks-passed"),
        ("unit-tests", "passed", "checks-passed"),
    ]


@pytest.mark.ac("AC-F09-180")
@pytest.mark.parametrize(
    ("mode", "expected", "reason"),
    [
        ("missing", "failed", "check-missing"),
        ("case", "failed", "check-missing"),
        ("failed", "failed", "check-not-successful"),
        ("neutral", "failed", "check-not-successful"),
        ("mixed", "failed", "check-not-successful"),
        ("one-success", "passed", "checks-passed"),
        ("many-success", "passed", "checks-passed"),
    ],
)
def test_required_checks_use_exact_names_and_all_retained_records(
    mode: str,
    expected: str,
    reason: str,
    policy_data: dict[str, Any],
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    statement = verified_view.statement
    assert statement is not None
    assert statement.predicate.checks is not None
    base = statement.predicate.checks[0]
    required_name = "Unit-Tests" if mode == "case" else "unit-tests"
    policy_data["policies"][0]["require"] = {
        "attestation": True,
        "checks": {"mustPass": ["missing" if mode == "missing" else required_name]},
    }
    if mode in {"failed", "neutral"}:
        checks: tuple[Check, ...] = (base.model_copy(update={"conclusion": mode}),)
    elif mode == "mixed":
        checks = (base, base.model_copy(update={"conclusion": "failure", "run_id": "2"}))
    elif mode == "many-success":
        checks = (base, Check.model_validate({**base.model_dump(), "runId": "2"}))
    else:
        checks = (base,)
    changed_statement = statement.model_copy(
        update={"predicate": statement.predicate.model_copy(update={"checks": checks})}
    )
    view = replace(verified_view, statement=changed_statement)

    result = _single_result(
        evaluate(view, _loaded(policy_data), policy_context),
        "require.checks.mustPass",
    )
    assert (result.status, result.reason) == (expected, reason)
