"""Pure deterministic policy evaluation governed by BRD-F09 §5.2-5.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from attest_core import Statement, identity_pattern_matches
from attest_core.models import Predicate, ReviewVerdict
from attest_policy.errors import policy_error
from attest_policy.glob import branch_pattern_matches, path_pattern_matches
from attest_policy.models import (
    Decision,
    DecisionExitCode,
    DecisionOutcome,
    LoadedPolicy,
    Policy,
    PolicyContext,
    PolicyResult,
    PredicateName,
    PredicateResult,
    PredicateStatus,
    ReasonCode,
    VerificationStatus,
    VerificationView,
)


@dataclass(frozen=True, slots=True)
class _View:
    status: VerificationStatus
    statement: Statement | None
    failure_code: str | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: bool


def _valid_optional_string(value: object) -> bool:
    return value is None or (isinstance(value, str) and bool(value))


def _verification_view(verification: VerificationView | None) -> _View | None:
    if verification is None:
        return None
    try:
        view = _View(
            status=verification.status,
            statement=verification.statement,
            failure_code=verification.failure_code,
            verified_identity=verification.verified_identity,
            verified_issuer=verification.verified_issuer,
            transparency_log_verified=verification.transparency_log_verified,
        )
    except (AttributeError, TypeError):
        raise policy_error("ERR-POLICY-604") from None
    if (
        view.status not in {"verified", "verified-untrusted-environment", "failed"}
        or not _valid_optional_string(view.verified_identity)
        or not _valid_optional_string(view.verified_issuer)
        or not isinstance(view.transparency_log_verified, bool)
    ):
        raise policy_error("ERR-POLICY-604")
    if view.status == "failed":
        if (
            view.statement is not None
            or not isinstance(view.failure_code, str)
            or not view.failure_code
            or view.verified_identity is not None
            or view.verified_issuer is not None
            or view.transparency_log_verified
        ):
            raise policy_error("ERR-POLICY-604")
        return view
    if not isinstance(view.statement, Statement) or view.failure_code is not None:
        raise policy_error("ERR-POLICY-604")
    trusted = view.statement.predicate.collection.environment.trusted
    if (view.status == "verified") is not trusted:
        raise policy_error("ERR-POLICY-604")
    return view


def _result(
    name: PredicateName,
    status: str,
    reason: ReasonCode,
    detail: str | None = None,
) -> PredicateResult:
    return PredicateResult(
        name=name,
        status=cast(PredicateStatus, status),
        reason=reason,
        detail=detail,
    )


def _configured_results(policy: Policy, reason: ReasonCode) -> list[PredicateResult]:
    require = policy.require
    results: list[PredicateResult] = []
    if require.attestation is not None:
        results.append(_result("require.attestation", "not-applicable", reason))
    if require.environment is not None:
        results.append(_result("require.environment.trusted", "not-applicable", reason))
    if require.signer is not None:
        results.extend(
            (
                _result("require.signer.issuer", "not-applicable", reason),
                _result("require.signer.identity", "not-applicable", reason),
            )
        )
    if require.transparency_log is not None:
        results.append(_result("require.transparencyLog", "not-applicable", reason))
    if require.review is not None:
        if require.review.when is not None:
            results.append(_result("require.review.when.authorshipMode", "not-applicable", reason))
        if require.review.min_human_approvals is not None:
            results.append(_result("require.review.minHumanApprovals", "not-applicable", reason))
        if require.review.approver_must_not_be_author is not None:
            results.append(
                _result(
                    "require.review.approverMustNotBeAuthor",
                    "not-applicable",
                    reason,
                )
            )
    if require.authorship is not None:
        results.append(_result("require.authorship.claimsRequired", "not-applicable", reason))
    if require.checks is not None:
        results.extend(
            _result("require.checks.mustPass", "not-applicable", reason, name)
            for name in require.checks.must_pass
        )
    return results


def _global_policy_result(policy: Policy, reason: ReasonCode) -> PolicyResult:
    return PolicyResult(
        policy_id=policy.id,
        matched=None,
        on_violation=policy.on_violation,
        predicates=(
            _result("match.branches", "not-applicable", reason),
            _result("match.paths", "not-applicable", reason),
            *_configured_results(policy, reason),
        ),
    )


def _matches(policy: Policy, context: PolicyContext) -> tuple[bool, bool]:
    branches = any(
        branch_pattern_matches(pattern, context.target_branch) for pattern in policy.match.branches
    )
    paths = any(
        path_pattern_matches(pattern, path)
        for pattern in policy.match.paths
        for path in context.changed_paths
    )
    return branches, paths


def _boolean_requirement(
    name: PredicateName,
    enabled: bool,
    condition: bool,
    passed: ReasonCode,
    failed: ReasonCode,
) -> PredicateResult:
    if not enabled:
        return _result(name, "not-applicable", "requirement-disabled")
    return _result(name, "passed" if condition else "failed", passed if condition else failed)


def _review_results(policy: Policy, predicate: Predicate) -> list[PredicateResult]:
    configuration = policy.require.review
    if configuration is None:
        return []
    results: list[PredicateResult] = []
    condition_met = True
    if configuration.when is not None:
        condition_met = predicate.authorship.mode.value in configuration.when.authorship_mode
        results.append(
            _result(
                "require.review.when.authorshipMode",
                "passed" if condition_met else "not-applicable",
                "review-condition-met" if condition_met else "review-condition-not-met",
            )
        )
    if not condition_met:
        if configuration.min_human_approvals is not None:
            results.append(
                _result(
                    "require.review.minHumanApprovals",
                    "not-applicable",
                    "review-condition-not-met",
                )
            )
        if configuration.approver_must_not_be_author is not None:
            results.append(
                _result(
                    "require.review.approverMustNotBeAuthor",
                    "not-applicable",
                    "review-condition-not-met",
                )
            )
        return results

    if configuration.min_human_approvals is not None:
        enough = predicate.review.human_approvals >= configuration.min_human_approvals
        results.append(
            _result(
                "require.review.minHumanApprovals",
                "passed" if enough else "failed",
                "approvals-satisfied" if enough else "approvals-insufficient",
            )
        )
    if configuration.approver_must_not_be_author is not None:
        if not configuration.approver_must_not_be_author:
            results.append(
                _result(
                    "require.review.approverMustNotBeAuthor",
                    "not-applicable",
                    "requirement-disabled",
                )
            )
        elif predicate.review.reviewers and all(
            reviewer.effective is None for reviewer in predicate.review.reviewers
        ):
            results.append(
                _result(
                    "require.review.approverMustNotBeAuthor",
                    "failed",
                    "effective-review-state-missing",
                )
            )
        else:
            identities = {
                reviewer.identity.split(":", maxsplit=2)[1]
                for reviewer in predicate.review.reviewers
                if reviewer.effective is True
                and reviewer.verdict is ReviewVerdict.APPROVED
                and not reviewer.is_change_author
            }
            minimum = configuration.min_human_approvals
            enough = minimum is not None and len(identities) >= minimum
            results.append(
                _result(
                    "require.review.approverMustNotBeAuthor",
                    "passed" if enough else "failed",
                    (
                        "non-author-approvals-satisfied"
                        if enough
                        else "non-author-approvals-insufficient"
                    ),
                )
            )
    return results


def _check_results(policy: Policy, predicate: Predicate) -> list[PredicateResult]:
    configuration = policy.require.checks
    if configuration is None:
        return []
    checks = predicate.checks or ()
    results: list[PredicateResult] = []
    for name in configuration.must_pass:
        matched = tuple(check for check in checks if check.name == name)
        if not matched:
            results.append(_result("require.checks.mustPass", "failed", "check-missing", name))
        elif any(check.conclusion != "success" for check in matched):
            results.append(
                _result("require.checks.mustPass", "failed", "check-not-successful", name)
            )
        else:
            results.append(_result("require.checks.mustPass", "passed", "checks-passed", name))
    return results


def _evaluate_requirements(policy: Policy, view: _View | None) -> list[PredicateResult]:
    require = policy.require
    if view is None:
        results: list[PredicateResult] = []
        if require.attestation is not None:
            results.append(
                _result(
                    "require.attestation",
                    "failed" if require.attestation else "not-applicable",
                    "attestation-missing" if require.attestation else "requirement-disabled",
                )
            )
        results.extend(_configured_results_without_attestation(policy, "attestation-missing"))
        return results

    statement = view.statement
    if statement is None:
        raise policy_error("ERR-POLICY-604")
    predicate = statement.predicate
    results = []
    if require.attestation is not None:
        results.append(
            _boolean_requirement(
                "require.attestation",
                require.attestation,
                True,
                "attestation-present",
                "attestation-missing",
            )
        )
    if require.environment is not None:
        results.append(
            _boolean_requirement(
                "require.environment.trusted",
                require.environment.trusted,
                predicate.collection.environment.trusted,
                "environment-trusted",
                "environment-untrusted-or-unknown",
            )
        )
    if require.signer is not None:
        issuer_matches = view.verified_issuer == require.signer.issuer
        identity_matches = view.verified_identity is not None and identity_pattern_matches(
            require.signer.identity, view.verified_identity
        )
        results.extend(
            (
                _result(
                    "require.signer.issuer",
                    "passed" if issuer_matches else "failed",
                    "signer-issuer-matched" if issuer_matches else "signer-issuer-mismatched",
                ),
                _result(
                    "require.signer.identity",
                    "passed" if identity_matches else "failed",
                    (
                        "signer-identity-matched"
                        if identity_matches
                        else "signer-identity-mismatched"
                    ),
                ),
            )
        )
    if require.transparency_log is not None:
        results.append(
            _boolean_requirement(
                "require.transparencyLog",
                require.transparency_log,
                view.transparency_log_verified,
                "transparency-log-verified",
                "transparency-log-unverified",
            )
        )
    results.extend(_review_results(policy, predicate))
    if require.authorship is not None:
        results.append(
            _boolean_requirement(
                "require.authorship.claimsRequired",
                require.authorship.claims_required,
                predicate.authorship.claims_present,
                "claims-present",
                "claims-missing",
            )
        )
    results.extend(_check_results(policy, predicate))
    return results


def _configured_results_without_attestation(
    policy: Policy,
    reason: ReasonCode,
) -> list[PredicateResult]:
    configured = _configured_results(policy, reason)
    if policy.require.attestation is not None:
        return configured[1:]
    return configured


def _evaluate_policy(policy: Policy, view: _View | None, context: PolicyContext) -> PolicyResult:
    branch_match, path_match = _matches(policy, context)
    matched = branch_match and path_match
    predicates: list[PredicateResult] = [
        _result(
            "match.branches",
            "passed" if branch_match else "failed",
            "matched" if branch_match else "not-matched",
        ),
        _result(
            "match.paths",
            "passed" if path_match else "failed",
            "matched" if path_match else "not-matched",
        ),
    ]
    if matched:
        predicates.extend(_evaluate_requirements(policy, view))
    else:
        predicates.extend(_configured_results(policy, "policy-not-matched"))
    return PolicyResult(
        policy_id=policy.id,
        matched=matched,
        on_violation=policy.on_violation,
        predicates=tuple(predicates),
    )


def _decision_outcome(
    results: tuple[PolicyResult, ...],
    *,
    attestation_missing: bool,
) -> tuple[DecisionOutcome, DecisionExitCode]:
    violated = tuple(
        result
        for result in results
        if result.matched is True
        and any(predicate.status == "failed" for predicate in result.predicates[2:])
    )
    if any(result.on_violation == "block" for result in violated):
        return "deny", 5 if attestation_missing else 3
    if violated:
        return "warn", 0
    return "allow", 0


def evaluate(
    verification: VerificationView | None,
    policy: LoadedPolicy,
    context: PolicyContext,
) -> Decision:
    """Evaluate every policy without I/O or a substituted Predicate input (REQ-F09-010-180)."""
    if not _valid_evaluation_inputs(policy, context):
        raise policy_error("ERR-POLICY-604")
    view = _verification_view(verification)
    document = policy.document
    policies = () if document is None else document.policies
    if view is not None and view.status == "failed":
        results = tuple(_global_policy_result(item, "verification-failed") for item in policies)
        return Decision(
            outcome="deny",
            exit_code=4,
            source=policy.source,
            notice=policy.reporting_only_notice,
            policies=results,
        )
    results = tuple(_evaluate_policy(item, view, context) for item in policies)
    outcome, exit_code = _decision_outcome(results, attestation_missing=view is None)
    return Decision(
        outcome=outcome,
        exit_code=exit_code,
        source=policy.source,
        notice=policy.reporting_only_notice,
        policies=results,
    )


def _valid_evaluation_inputs(policy: object, context: object) -> bool:
    return isinstance(policy, LoadedPolicy) and isinstance(context, PolicyContext)
