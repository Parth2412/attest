"""Sanitised CLI command execution boundary governed by BRD-F10."""

from __future__ import annotations

import os
import platform
import re
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from attest_cli.errors import CliError, cli_error
from attest_cli.models import (
    BuildData,
    CheckData,
    CliDiagnostic,
    CollectData,
    ConfigSecretEntryData,
    ConfigShowData,
    ConfigValueEntryData,
    DecisionData,
    DoctorCheckData,
    DoctorData,
    GateData,
    InitData,
    InspectData,
    PolicyResultData,
    PolicySourceData,
    PredicateResultData,
    PushData,
    RunData,
    RunStageData,
    SignData,
    StoreRefData,
    VerificationData,
    VerifyData,
    VersionData,
    make_report,
)
from attest_cli.output import emit_report

if TYPE_CHECKING:
    from attest_cli.config import ResolvedConfig
    from attest_collect import BackendOverride
    from attest_policy import Decision, LoadedPolicy, VerificationView
    from attest_sign import (
        IdentityConstraint,
        RepositoryConstraint,
        TrustRootSource,
        VerificationResult,
    )
    from attest_store import AttestationStore, StoreRef

Outcome = Literal["success", "warning", "denied", "failed", "unverified-identity"]
RunStageName = Literal["collect", "build", "sign", "push", "verify", "gate"]


class _Endpoint(Protocol):
    url: str


def _endpoint_url(value: object) -> str:
    endpoint = cast(_Endpoint, value).url
    if not endpoint.startswith("https://"):
        raise ValueError
    return endpoint


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Carry one fully mapped command result to the renderer."""

    outcome: Outcome
    exit_code: int
    data: object
    warnings: tuple[CliDiagnostic, ...] = ()
    error: CliDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class _VerificationSnapshot:
    resolved: ResolvedConfig
    constraint: IdentityConstraint
    trust: TrustRootSource


_FLAG_KEYS: Final[dict[str, str]] = {
    "repository": "repository.path",
    "git_backend": "repository.backend",
    "github_event": "github.eventPath",
    "signing_environment": "signing.environment",
    "signing_timeout_seconds": "signing.timeoutSeconds",
    "identity": "verification.identity",
    "issuer": "verification.issuer",
    "verify_environment": "verification.environment",
    "offline": "verification.offline",
    "trust_config_file": "verification.trustConfigFile",
    "policy": "policy.path",
    "store_backend": "storage.backend",
    "store_directory": "storage.directory",
    "fallback_directory": "storage.fallbackDirectory",
    "git_remote": "storage.git.remote",
    "git_timeout_seconds": "storage.git.timeoutSeconds",
    "oci_repository": "storage.oci.repository",
    "oci_subject_media_type": "storage.oci.subject.mediaType",
    "oci_subject_digest": "storage.oci.subject.digest",
    "oci_subject_size": "storage.oci.subject.size",
    "oci_staging_directory": "storage.oci.stagingDirectory",
    "oci_insecure": "storage.oci.insecure",
    "oci_tls_verify": "storage.oci.tlsVerify",
    "oci_timeout_seconds": "storage.oci.timeoutSeconds",
}
_COLLECT_USAGE_CODES: Final[frozenset[str]] = frozenset(
    {
        "ERR-COLLECT-101",
        "ERR-COLLECT-102",
        "ERR-COLLECT-103",
        "ERR-COLLECT-104",
        "ERR-COLLECT-105",
        "ERR-COLLECT-115",
        "ERR-COLLECT-121",
        "ERR-COLLECT-124",
        "ERR-COLLECT-126",
        "ERR-COLLECT-127",
    }
)
_COLLECT_TRANSIENT_CODES: Final[frozenset[str]] = frozenset({"ERR-COLLECT-123", "ERR-COLLECT-125"})
_SIGN_USAGE_CODES: Final[frozenset[str]] = frozenset({"ERR-SIGN-301", "ERR-SIGN-306"})
_SIGN_TRANSIENT_CODES: Final[frozenset[str]] = frozenset(
    {"ERR-SIGN-302", "ERR-SIGN-303", "ERR-SIGN-304"}
)
_VERIFY_DETAILS: Final[dict[str, tuple[str, str]]] = {
    "ERR-VERIFY-001": (
        "The Sigstore bundle is malformed or incomplete",
        "Supply a complete parseable Sigstore bundle",
    ),
    "ERR-VERIFY-007": (
        "The verified DSSE payload is not a supported attest Statement",
        "Use a supported attest predicate version and in-toto payload type",
    ),
    "ERR-VERIFY-008": (
        "The verified Statement failed its versioned structural schema",
        "Reject the attestation and obtain a structurally valid bundle",
    ),
    "ERR-VERIFY-009": (
        "The verified Statement failed semantic validation",
        "Reject the attestation and obtain a semantically valid bundle",
    ),
    "ERR-VERIFY-010": (
        "Repository ChangeSet recomputation failed or did not match",
        "Check the repository and caller-selected base and head revisions",
    ),
    "ERR-VERIFY-011": (
        "The identity constraint is invalid",
        "Supply a non-empty exact issuer and an exact identity or bounded workflow glob",
    ),
    "ERR-VERIFY-012": (
        "The selected Sigstore trust material is unavailable or invalid",
        "Refresh the selected environment explicitly or supply valid trust configuration JSON",
    ),
    "ERR-VERIFY-013": (
        "Sigstore cryptographic verification failed",
        "Reject the bundle and inspect the signer and trust configuration",
    ),
}
_BUILD_REVISION: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")


def _public_path(value: object) -> object:
    return os.fspath(value) if isinstance(value, Path) else value


def _flags(values: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _public_path(values[name])
        for name, key in _FLAG_KEYS.items()
        if name in values and values[name] is not None
    }


def _repository(values: Mapping[str, object]) -> Path:
    supplied = values.get("repository")
    return supplied if isinstance(supplied, Path) else Path()


def _resolved_config(
    values: Mapping[str, object], *, trusted_github: bool = False
) -> ResolvedConfig:
    from attest_cli.config import ResolvedConfig, load_config

    snapshot = values.get("_resolved_config")
    if snapshot is not None:
        if not isinstance(snapshot, ResolvedConfig):
            raise cli_error("ERR-INTERNAL-001")
        return snapshot

    config = values.get("config")
    explicit = config if isinstance(config, Path) else None
    return load_config(
        repository=_repository(values),
        explicit_path=explicit,
        flags=_flags(values),
        environ=os.environ,
        trusted_github=trusted_github,
    )


def _diagnostic(error: object) -> CliDiagnostic | None:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    remediation = getattr(error, "remediation", None)
    if (
        isinstance(code, str)
        and bool(code)
        and isinstance(message, str)
        and bool(message)
        and isinstance(remediation, str)
        and bool(remediation)
    ):
        return CliDiagnostic(code=code, message=message, remediation=remediation)
    return None


def _mapped_exit(code: str) -> int | None:
    if code.startswith("ERR-CONFIG-"):
        return 2
    if code in _COLLECT_USAGE_CODES or code == "ERR-BUILD-211":
        return 2
    if code in _COLLECT_TRANSIENT_CODES or code in _SIGN_TRANSIENT_CODES:
        return 6
    if code in {"ERR-COLLECT-106", "ERR-COLLECT-122", "ERR-BUILD-210", "ERR-SIGN-305"}:
        return 1
    if code in _SIGN_USAGE_CODES or code == "ERR-VERIFY-011":
        return 2
    if code.startswith("ERR-VERIFY-"):
        return 4
    if code in {"ERR-STORE-401", "ERR-STORE-402"}:
        return 6
    if code == "ERR-STORE-403":
        return 5
    if code == "ERR-STORE-405" or code.startswith("ERR-POLICY-60"):
        return 2
    if code in {"ERR-STORE-404", "ERR-STORE-406"}:
        return 1
    return None


def _failure_from_exception(command: str, error: object) -> CommandResult:
    if isinstance(error, CliError):
        diagnostic = _diagnostic(error)
        if diagnostic is None:  # pragma: no cover - CliError guarantees these fields
            raise TypeError
        return CommandResult("failed", int(error.exit_code), None, error=diagnostic)
    diagnostic = _diagnostic(error)
    if diagnostic is not None:
        exit_code = _mapped_exit(diagnostic.code)
        if exit_code is not None:
            data: object = None
            fallback = getattr(error, "fallback_path", None)
            if command == "push" and isinstance(fallback, str) and fallback:
                from attest_cli.models import PushData

                data = PushData(store_ref=None, fallback_path=fallback)
            return CommandResult("failed", exit_code, data, error=diagnostic)
    internal = cli_error("ERR-INTERNAL-001")
    diagnostic = cast(CliDiagnostic, _diagnostic(internal))
    return CommandResult("failed", 1, None, error=diagnostic)


def _handle_version(_values: Mapping[str, object]) -> CommandResult:
    revision = os.environ.get("ATTEST_BUILD_REVISION")
    build_revision = (
        revision if revision is not None and _BUILD_REVISION.fullmatch(revision) else None
    )
    return CommandResult(
        "success",
        0,
        VersionData(
            cli_version=metadata.version("attest-cli"),
            python_version=platform.python_version(),
            build_revision=build_revision,
        ),
    )


def _handle_init(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.initialize import initialize

    repository = values["repository"]
    checkout_ref = values["checkout_ref"]
    action_ref = values["action_ref"]
    if (
        not isinstance(repository, Path)
        or not isinstance(checkout_ref, str)
        or not isinstance(action_ref, str)
    ):
        raise cli_error("ERR-CONFIG-001")
    if values.get("config") is not None:
        _resolved_config(values)
    initialized = initialize(
        repository=repository,
        github_repository=cast(str | None, values.get("github_repository")),
        default_branch=cast(str | None, values.get("default_branch")),
        checkout_ref=checkout_ref,
        action_ref=action_ref,
    )
    return CommandResult(
        "success",
        0,
        InitData(
            created_paths=initialized.created_paths,
            workflow_identity=initialized.workflow_identity,
        ),
    )


def _handle_build(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.artifacts import read_collection_artifact, serialize_statement
    from attest_cli.safe_io import write_atomic
    from attest_core import build_statement

    _resolved_config(values)
    input_path = values["input_path"]
    output = values["output"]
    overwrite = values["overwrite"]
    if (
        not isinstance(input_path, Path)
        or not isinstance(output, Path)
        or not isinstance(overwrite, bool)
    ):
        raise cli_error("ERR-CONFIG-001")
    artifact = read_collection_artifact(input_path)
    statement = build_statement(
        artifact.change_set,
        artifact.authorship,
        artifact.review,
        artifact.checks or (),
        artifact.collection,
    )
    write_atomic(output, serialize_statement(statement), overwrite=overwrite)
    return CommandResult(
        "success",
        0,
        BuildData(output_path=os.fspath(output), change_set_digest=artifact.change_set.digest),
    )


def _collect_warning_rows(*groups: tuple[object, ...]) -> tuple[CliDiagnostic, ...]:
    ordered: list[tuple[int, str, str, CliDiagnostic]] = []
    for stage, group in enumerate(groups):
        for item in group:
            diagnostic = _diagnostic(item)
            if diagnostic is None:
                raise cli_error("ERR-INTERNAL-001")
            ordered.append((stage, diagnostic.code, diagnostic.message, diagnostic))
    return tuple(row[3] for row in sorted(ordered, key=lambda row: row[:3]))


def _handle_collect(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.artifacts import (
        CollectionArtifact,
        CollectionContext,
        serialize_collection_artifact,
    )
    from attest_cli.safe_io import read_regular_file, write_atomic
    from attest_collect import (
        CollectContext,
        GitHubForgeAdapter,
        GitHubHttpClient,
        GitHubPullRequestInput,
        GitHubReviewContext,
        ReviewContextKind,
        collect_authorship,
        collect_changeset,
        collect_environment,
        collect_github,
        load_github_token,
        parse_github_pull_request_event,
        resolve_github_changeset_context,
        standard_collectors,
    )
    from attest_core import Review, ReviewState

    collection = collect_environment(os.environ)
    trusted_github = (
        collection.environment.kind.value == "github-actions" and collection.environment.trusted
    )
    resolved = _resolved_config(values, trusted_github=trusted_github)
    event_value = resolved.value("github.eventPath")
    event_path = Path(cast(str, event_value)) if event_value is not None else None
    base = values.get("base")
    head = values.get("head")
    target_branch = values.get("target_branch")
    github_repository = values.get("github_repository")
    pr = values.get("pr")
    explicit_context = (base, head, target_branch, github_repository, pr)

    if event_path is not None:
        if any(item is not None for item in explicit_context):
            raise cli_error("ERR-CONFIG-001")
        event = read_regular_file(
            event_path,
            maximum_size=1024 * 1024,
            error_code="ERR-CONFIG-003",
        )
        request = parse_github_pull_request_event(event)
        github_mode = True
    elif github_repository is not None or pr is not None:
        if (
            not isinstance(github_repository, str)
            or isinstance(pr, bool)
            or not isinstance(pr, int)
            or not isinstance(base, str)
            or not isinstance(head, str)
            or not isinstance(target_branch, str)
        ):
            raise cli_error("ERR-CONFIG-001")
        request = GitHubPullRequestInput(
            repository=github_repository,
            pr_number=pr,
            base_revision=base,
            head_revision=head,
            target_branch=target_branch,
        )
        github_mode = True
    else:
        if not all(isinstance(item, str) and bool(item) for item in (base, head, target_branch)):
            raise cli_error("ERR-CONFIG-001")
        request = None
        github_mode = False

    repository = Path(cast(str, resolved.value("repository.path")))
    backend = cast(str, resolved.value("repository.backend"))
    github_warnings: tuple[object, ...] = ()
    if github_mode:
        token = load_github_token(os.environ)
        with GitHubHttpClient(token) as client:
            if request is None:  # pragma: no cover - github_mode establishes a request
                raise cli_error("ERR-INTERNAL-001")
            context = resolve_github_changeset_context(client, request)
            change_set = collect_changeset(
                repository,
                context.base_revision,
                context.head_revision,
                cast("BackendOverride", backend),
                merge_base_rev=context.merge_base_revision,
                repository_url=f"https://github.com/{context.repository}",
            )
            github = collect_github(
                GitHubForgeAdapter(client),
                GitHubReviewContext(
                    kind=ReviewContextKind.PULL_REQUEST,
                    repository=context.repository,
                    head_sha=context.head_revision,
                    base_branch=context.target_branch,
                    change_author_ids=context.change_author_ids,
                    pr_number=context.pr_number,
                ),
            )
        review = github.review
        checks = github.checks
        github_warnings = cast(tuple[object, ...], github.warnings)
        effective_target = context.target_branch
    else:
        change_set = collect_changeset(
            repository,
            cast(str, base),
            cast(str, head),
            cast("BackendOverride", backend),
        )
        review = Review(
            required="unknown",
            state=ReviewState.UNKNOWN,
            human_approvals=0,
            reviewers=(),
        )
        checks = None
        effective_target = cast(str, target_branch)

    manual_claims = values.get("claim")
    if manual_claims is None:
        claims: tuple[str, ...] = ()
    elif isinstance(manual_claims, list) and all(isinstance(item, str) for item in manual_claims):
        claims = tuple(manual_claims)
    else:
        raise cli_error("ERR-CONFIG-001")
    record_paths = tuple(entry.path for entry in change_set.record.entries)
    authorship = collect_authorship(
        CollectContext(
            repo_path=repository,
            base_commit=change_set.info.base_commit,
            head_commit=change_set.info.head_commit,
        ),
        standard_collectors(claims),
        record_paths,
    )
    artifact = CollectionArtifact(
        schema_version="0.1.0",
        change_set_record=change_set.record,
        change_set=change_set.info,
        authorship=authorship.authorship,
        review=review,
        checks=checks,
        collection=collection,
        context=CollectionContext(
            base_commit=change_set.info.base_commit,
            head_commit=change_set.info.head_commit,
            merge_base=change_set.info.merge_base,
            target_branch=effective_target,
        ),
    )
    output = values.get("output")
    overwrite = values.get("overwrite")
    if not isinstance(output, Path) or not isinstance(overwrite, bool):
        raise cli_error("ERR-CONFIG-001")
    write_atomic(output, serialize_collection_artifact(artifact), overwrite=overwrite)
    warnings = _collect_warning_rows(
        cast(tuple[object, ...], change_set.warnings),
        cast(tuple[object, ...], authorship.warnings),
        github_warnings,
    )
    return CommandResult(
        "warning" if warnings else "success",
        0,
        CollectData(
            output_path=os.fspath(output),
            change_set_digest=change_set.info.digest,
            base_commit=change_set.info.base_commit,
            head_commit=change_set.info.head_commit,
            merge_base=change_set.info.merge_base,
            target_branch=effective_target,
            backend=change_set.diagnostics.backend,
        ),
        warnings=warnings,
    )


def _read_bundle(path: Path) -> bytes:
    from attest_cli.safe_io import MissingInputError, read_regular_file

    try:
        return read_regular_file(
            path,
            maximum_size=64 * 1024 * 1024,
            error_code="ERR-CONFIG-003",
            distinguish_missing=True,
        )
    except MissingInputError:
        from attest_store import StoreError

        raise StoreError("ERR-STORE-403") from None


def _handle_sign(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.artifacts import read_statement
    from attest_cli.safe_io import write_atomic
    from attest_sign import SigningEnvironment, SigstoreSigner

    resolved = _resolved_config(values)
    input_path = values.get("input_path")
    output = values.get("output")
    overwrite = values.get("overwrite")
    if (
        not isinstance(input_path, Path)
        or not isinstance(output, Path)
        or not isinstance(overwrite, bool)
    ):
        raise cli_error("ERR-CONFIG-001")
    environment = SigningEnvironment(cast(str, resolved.value("signing.environment")))
    timeout_seconds = cast(int, resolved.value("signing.timeoutSeconds"))
    statement = read_statement(input_path)
    signer = SigstoreSigner(
        environment=environment,
        attempt_timeout=timedelta(seconds=timeout_seconds),
    )
    bundle = signer.sign(statement)
    write_atomic(output, bundle.raw, overwrite=overwrite)
    return CommandResult(
        "success",
        0,
        SignData(
            output_path=os.fspath(output),
            environment=bundle.environment.value,
            certificate_identity=bundle.certificate_identity,
            certificate_issuer=bundle.certificate_issuer,
            rekor_index=bundle.log_index,
        ),
    )


def _repository_relative(repository: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise cli_error("ERR-CONFIG-001")
    configured = Path(value)
    return configured if configured.is_absolute() else repository / configured


def _store_ref_data(reference: StoreRef) -> StoreRefData:
    from attest_store import StoreRef

    if not isinstance(reference, StoreRef):
        raise cli_error("ERR-INTERNAL-001")
    stored_at = reference.stored_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    return StoreRefData(
        backend=reference.backend,
        digest=reference.digest,
        bundle_digest=reference.bundle_digest,
        location=reference.location,
        stored_at=stored_at,
    )


def _verification_data(result: VerificationResult) -> VerificationData:
    return VerificationData(
        status=result.status,
        checks=tuple(
            CheckData(name=item.name, result=item.result, code=item.code) for item in result.checks
        ),
        statement=result.statement,
        failure_code=result.failure_code,
        verified_identity=result.verified_identity,
        verified_issuer=result.verified_issuer,
        transparency_log_verified=result.transparency_log_verified,
    )


def _verification_failure(data: VerificationData) -> CliDiagnostic:
    code = data.failure_code
    if code is None or code not in _VERIFY_DETAILS:
        raise cli_error("ERR-INTERNAL-001")
    message, remediation = _VERIFY_DETAILS[code]
    return CliDiagnostic(code=code, message=message, remediation=remediation)


def _verification_inputs(
    values: Mapping[str, object],
) -> tuple[ResolvedConfig, IdentityConstraint, TrustRootSource]:
    from attest_cli.safe_io import decode_json_object, read_regular_file
    from attest_sign import (
        IdentityConstraint,
        ServiceTrustRoot,
        SuppliedTrustRoot,
        VerificationEnvironment,
    )

    snapshot = values.get("_verification_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, _VerificationSnapshot):
            raise cli_error("ERR-INTERNAL-001")
        return snapshot.resolved, snapshot.constraint, snapshot.trust

    resolved = _resolved_config(values)
    identity = resolved.value("verification.identity")
    issuer = resolved.value("verification.issuer")
    if not isinstance(identity, str) or not identity or not isinstance(issuer, str) or not issuer:
        raise cli_error("ERR-CONFIG-005")
    constraint = IdentityConstraint(identity_pattern=identity, issuer=issuer)
    trust_path_value = resolved.value("verification.trustConfigFile")
    if trust_path_value is None:
        trust: TrustRootSource = ServiceTrustRoot(
            environment=VerificationEnvironment(
                cast(str, resolved.value("verification.environment"))
            ),
            offline=cast(bool, resolved.value("verification.offline")),
        )
    else:
        repository = Path(cast(str, resolved.value("repository.path")))
        trust_path = _repository_relative(repository, trust_path_value)
        raw = read_regular_file(
            trust_path,
            maximum_size=64 * 1024 * 1024,
            error_code="ERR-CONFIG-003",
        )
        decode_json_object(raw)
        trust = SuppliedTrustRoot(raw.decode("utf-8", errors="strict"))
    return resolved, constraint, trust


def _optional_repository_constraint(
    values: Mapping[str, object],
) -> RepositoryConstraint | None:
    from attest_sign import RepositoryConstraint

    supplied = (values.get("repository"), values.get("base"), values.get("head"))
    present = tuple(item is not None for item in supplied)
    if any(present) and not all(present):
        raise cli_error("ERR-CONFIG-001")
    if not all(present):
        return None
    repository, base, head = supplied
    if not isinstance(repository, Path) or not isinstance(base, str) or not isinstance(head, str):
        raise cli_error("ERR-CONFIG-001")
    return RepositoryConstraint(path=repository, base_revision=base, head_revision=head)


def _handle_verify(values: Mapping[str, object]) -> CommandResult:
    from attest_sign import verify

    _, constraint, trust = _verification_inputs(values)
    repository = _optional_repository_constraint(values)
    input_path = values.get("input_path")
    if not isinstance(input_path, Path):
        raise cli_error("ERR-CONFIG-001")
    result = verify(_read_bundle(input_path), constraint, trust, repository)
    verification = _verification_data(result)
    data = VerifyData(verification=verification)
    if verification.status == "failed":
        return CommandResult(
            "failed",
            4,
            data,
            error=_verification_failure(verification),
        )
    return CommandResult("success", 0, data)


def _load_resolved_policy(resolved: ResolvedConfig, repository: Path) -> LoadedPolicy:
    from attest_cli.safe_io import MissingInputError, read_regular_file
    from attest_policy import load_policy

    path_value = resolved.value("policy.path")
    source = resolved.source("policy.path")
    if not isinstance(path_value, str) or not path_value:
        raise cli_error("ERR-CONFIG-001")
    policy_path = _repository_relative(repository, path_value)
    try:
        raw = read_regular_file(
            policy_path,
            maximum_size=1024 * 1024,
            error_code="ERR-CONFIG-003",
            distinguish_missing=True,
        )
    except MissingInputError:
        if source == "builtin":
            return load_policy(None, None)
        return load_policy(None, os.fspath(policy_path))
    except CliError:
        return load_policy(None, os.fspath(policy_path))
    return load_policy(raw, os.fspath(policy_path))


def _decision_data(decision: Decision) -> DecisionData:
    return DecisionData(
        outcome=decision.outcome,
        exit_code=decision.exit_code,
        source=PolicySourceData(path=decision.source.path, sha256=decision.source.sha256),
        notice=decision.notice,
        policies=tuple(
            PolicyResultData(
                policy_id=policy.policy_id,
                matched=policy.matched,
                on_violation=policy.on_violation,
                predicates=tuple(
                    PredicateResultData(
                        name=predicate.name,
                        status=predicate.status,
                        reason=predicate.reason,
                        detail=predicate.detail,
                    )
                    for predicate in policy.predicates
                ),
            )
            for policy in decision.policies
        ),
    )


def _handle_gate(values: Mapping[str, object]) -> CommandResult:
    from attest_collect import collect_changeset
    from attest_policy import PolicyContext, evaluate
    from attest_sign import RepositoryConstraint, verify

    resolved, constraint, trust = _verification_inputs(values)
    input_path = values.get("input_path")
    repository = values.get("repository")
    base = values.get("base")
    head = values.get("head")
    target_branch = values.get("target_branch")
    if (
        not isinstance(input_path, Path)
        or not isinstance(repository, Path)
        or not isinstance(base, str)
        or not isinstance(head, str)
        or not isinstance(target_branch, str)
    ):
        raise cli_error("ERR-CONFIG-001")
    change_set = collect_changeset(
        repository,
        base,
        head,
        cast("BackendOverride", resolved.value("repository.backend")),
    )
    result = verify(
        _read_bundle(input_path),
        constraint,
        trust,
        RepositoryConstraint(
            path=repository,
            base_revision=change_set.info.base_commit,
            head_revision=change_set.info.head_commit,
        ),
    )
    loaded_policy = _load_resolved_policy(resolved, repository)
    decision = evaluate(
        cast("VerificationView", result),
        loaded_policy,
        PolicyContext(
            target_branch=target_branch,
            changed_paths=tuple(entry.path for entry in change_set.record.entries),
        ),
    )
    verification = _verification_data(result)
    decision_output = _decision_data(decision)
    data = GateData(verification=verification, decision=decision_output)
    outcome = cast(
        Outcome,
        {"allow": "success", "warn": "warning", "deny": "denied"}[decision.outcome],
    )
    warnings = _collect_warning_rows(cast(tuple[object, ...], change_set.warnings))
    return CommandResult(outcome, decision.exit_code, data, warnings=warnings)


def _run_stage(name: RunStageName, result: CommandResult, output_path: str | None) -> RunStageData:
    status = result.outcome
    if status == "unverified-identity":
        raise cli_error("ERR-INTERNAL-001")
    return RunStageData(name=name, status=status, output_path=output_path)


def _run_in_directory(values: Mapping[str, object], directory: Path) -> CommandResult:
    from attest_cli.artifacts import read_collection_artifact
    from attest_cli.safe_io import write_atomic
    from attest_policy import PolicyContext, evaluate

    output = values.get("output")
    overwrite = values.get("overwrite")
    if not isinstance(output, Path) or not isinstance(overwrite, bool):
        raise cli_error("ERR-CONFIG-001")
    collection_path = directory / "collection.json"
    statement_path = directory / "statement.json"
    work_bundle_path = directory / "bundle.sigstore.json"
    persistent = values.get("work_directory") is not None
    stages: list[RunStageData] = []

    collect_values = dict(values)
    collect_values.update(output=collection_path)
    collected = _handle_collect(collect_values)
    stages.append(
        _run_stage(
            "collect",
            collected,
            os.fspath(collection_path) if persistent else None,
        )
    )
    if not isinstance(collected.data, CollectData):
        raise cli_error("ERR-INTERNAL-001")

    build_values: dict[str, object] = {
        "input_path": collection_path,
        "output": statement_path,
        "overwrite": overwrite,
        "repository": values.get("repository"),
        "config": values.get("config"),
        "_resolved_config": values.get("_resolved_config"),
    }
    built = _handle_build(build_values)
    stages.append(_run_stage("build", built, os.fspath(statement_path) if persistent else None))

    sign_values: dict[str, object] = {
        "input_path": statement_path,
        "output": output,
        "overwrite": overwrite,
        "signing_environment": values.get("signing_environment"),
        "signing_timeout_seconds": values.get("signing_timeout_seconds"),
        "repository": values.get("repository"),
        "config": values.get("config"),
        "_resolved_config": values.get("_resolved_config"),
    }
    signed = _handle_sign(sign_values)
    stages.append(_run_stage("sign", signed, os.fspath(output)))
    if persistent and output.absolute() != work_bundle_path.absolute():
        write_atomic(work_bundle_path, _read_bundle(output), overwrite=overwrite)

    push_values = dict(values)
    push_values.update(
        input_path=output,
        change_set_digest=collected.data.change_set_digest,
    )
    pushed = _handle_push(push_values)
    stages.append(_run_stage("push", pushed, None))
    if not isinstance(pushed.data, PushData) or pushed.data.store_ref is None:
        raise cli_error("ERR-INTERNAL-001")

    artifact = read_collection_artifact(collection_path)
    verify_values = dict(values)
    verify_values.update(
        input_path=output,
        repository=Path(cast(str, _resolved_config(values).value("repository.path"))),
        base=artifact.context.base_commit,
        head=artifact.context.head_commit,
    )
    verified = _handle_verify(verify_values)
    if not isinstance(verified.data, VerifyData):
        raise cli_error("ERR-INTERNAL-001")
    stages.append(_run_stage("verify", verified, None))

    repository = Path(cast(str, _resolved_config(values).value("repository.path")))
    loaded_policy = _load_resolved_policy(_resolved_config(values), repository)
    decision = evaluate(
        cast("VerificationView", verified.data.verification),
        loaded_policy,
        PolicyContext(
            target_branch=artifact.context.target_branch,
            changed_paths=tuple(entry.path for entry in artifact.change_set_record.entries),
        ),
    )
    decision_output = _decision_data(decision)
    decision_outcome = cast(
        Outcome,
        {"allow": "success", "warn": "warning", "deny": "denied"}[decision.outcome],
    )
    gate_result = CommandResult(decision_outcome, decision.exit_code, decision_output)
    stages.append(_run_stage("gate", gate_result, None))
    return CommandResult(
        decision_outcome,
        decision.exit_code,
        RunData(
            stages=tuple(stages),
            store_ref=pushed.data.store_ref,
            verification=verified.data.verification,
            decision=decision_output,
        ),
        warnings=collected.warnings,
    )


def _handle_run(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.safe_io import ensure_directory

    # Fail closed on mandatory verification inputs before signing or storage side effects.
    resolved, constraint, trust = _verification_inputs(values)
    run_values = dict(values)
    run_values["_resolved_config"] = resolved
    run_values["_verification_snapshot"] = _VerificationSnapshot(
        resolved=resolved,
        constraint=constraint,
        trust=trust,
    )
    work_directory = values.get("work_directory")
    if work_directory is None:
        with tempfile.TemporaryDirectory(prefix="attest-run-") as temporary:
            return _run_in_directory(run_values, Path(temporary))
    if not isinstance(work_directory, Path):
        raise cli_error("ERR-CONFIG-001")
    return _run_in_directory(run_values, ensure_directory(work_directory))


def _handle_push(values: Mapping[str, object]) -> CommandResult:
    from attest_cli.safe_io import ensure_directory, read_regular_file
    from attest_store import (
        FilesystemStore,
        GitRefStore,
        OciStore,
        OciSubject,
        StoreError,
        put_with_fallback,
    )

    resolved = _resolved_config(values)
    input_path = values.get("input_path")
    digest = values.get("change_set_digest")
    if not isinstance(input_path, Path) or not isinstance(digest, str):
        raise cli_error("ERR-CONFIG-001")
    bundle = _read_bundle(input_path)
    repository = Path(cast(str, resolved.value("repository.path")))
    fallback_path = ensure_directory(
        _repository_relative(repository, resolved.value("storage.fallbackDirectory"))
    )
    fallback = FilesystemStore(fallback_path)
    backend = resolved.value("storage.backend")
    if backend == "git-ref":
        primary: AttestationStore = GitRefStore(
            repository,
            backend=cast("BackendOverride", resolved.value("repository.backend")),
            subprocess_timeout=timedelta(
                seconds=cast(int, resolved.value("storage.git.timeoutSeconds"))
            ),
        )
        remote = cast(str, resolved.value("storage.git.remote"))
        try:
            cast(GitRefStore, primary).import_remote(digest, remote)
        except StoreError as primary_error:
            try:
                fallback_reference = fallback.put(digest, bundle)
            except StoreError:
                raise StoreError("ERR-STORE-406") from primary_error
            raise StoreError(
                primary_error.code,
                fallback_path=fallback_reference.location,
            ) from primary_error
        local_reference = put_with_fallback(primary, fallback, digest, bundle)
        reference = cast(GitRefStore, primary).push(
            local_reference,
            remote,
            fallback,
        )
    elif backend == "filesystem":
        directory = ensure_directory(
            _repository_relative(repository, resolved.value("storage.directory"))
        )
        reference = put_with_fallback(FilesystemStore(directory), fallback, digest, bundle)
    elif backend == "oci":
        staging = ensure_directory(
            _repository_relative(repository, resolved.value("storage.oci.stagingDirectory"))
        )
        auth_value = resolved.value("storage.oci.authConfigFile")
        auth_path = _repository_relative(repository, auth_value) if auth_value is not None else None
        if auth_path is not None:
            read_regular_file(
                auth_path,
                maximum_size=64 * 1024 * 1024,
                error_code="ERR-CONFIG-003",
            )
        subject = OciSubject(
            media_type=cast(str, resolved.value("storage.oci.subject.mediaType")),
            digest=cast(str, resolved.value("storage.oci.subject.digest")),
            size=cast(int, resolved.value("storage.oci.subject.size")),
        )
        primary = OciStore(
            cast(str, resolved.value("storage.oci.repository")),
            subject=subject,
            staging_directory=staging,
            auth_config=auth_path,
            insecure=cast(bool, resolved.value("storage.oci.insecure")),
            tls_verify=cast(bool, resolved.value("storage.oci.tlsVerify")),
            operation_timeout=timedelta(
                seconds=cast(int, resolved.value("storage.oci.timeoutSeconds"))
            ),
        )
        reference = put_with_fallback(primary, fallback, digest, bundle)
    else:
        raise cli_error("ERR-CONFIG-001")
    return CommandResult(
        "success",
        0,
        PushData(store_ref=_store_ref_data(reference), fallback_path=None),
    )


def _handle_inspect(values: Mapping[str, object]) -> CommandResult:
    from attest_sign import inspect_bundle

    _resolved_config(values)
    input_path = values["input_path"]
    if not isinstance(input_path, Path):
        raise cli_error("ERR-CONFIG-001")
    raw = _read_bundle(input_path)
    inspected = inspect_bundle(raw)
    data = InspectData(
        status=inspected.status,
        checks=tuple(
            CheckData(name=item.name, result=item.result, code=item.code)
            for item in inspected.checks
        ),
        statement=inspected.statement,
        failure_code=inspected.failure_code,
    )
    if inspected.status == "failed":
        code = inspected.failure_code
        if code is None or code not in _VERIFY_DETAILS:
            raise cli_error("ERR-INTERNAL-001")
        message, remediation = _VERIFY_DETAILS[code]
        return CommandResult(
            "failed",
            2,
            data,
            error=CliDiagnostic(code=code, message=message, remediation=remediation),
        )
    return CommandResult("unverified-identity", 0, data)


def _handle_config_show(values: Mapping[str, object]) -> CommandResult:
    if values.get("resolved") is not True:
        raise cli_error("ERR-CONFIG-001")
    resolved = _resolved_config(values, trusted_github=_trusted_github())
    entries = tuple(
        ConfigSecretEntryData(key=item.key, configured=bool(item.configured), source=item.source)
        if item.configured is not None
        else ConfigValueEntryData(
            key=item.key,
            value=cast(bool | int | str | None, item.value),
            source=item.source,
        )
        for item in resolved.entries
    )
    return CommandResult(
        "success",
        0,
        ConfigShowData(entries=entries, organisation_policy="unsupported"),
    )


def _trusted_github() -> bool:
    from attest_collect import collect_environment

    collection = collect_environment(os.environ)
    return collection.environment.kind.value == "github-actions" and collection.environment.trusted


def _selected_git_backend(requested: object) -> str:
    from attest_collect import Pygit2Backend, SubprocessBackend

    if requested == "pygit2":
        selected = "pygit2" if Pygit2Backend.is_available() else "unavailable"
    elif requested == "subprocess":
        selected = "subprocess" if SubprocessBackend.is_available() else "unavailable"
    elif requested == "auto":
        if Pygit2Backend.is_available():
            selected = "pygit2"
        elif SubprocessBackend.is_available():
            selected = "subprocess"
        else:
            selected = "unavailable"
    else:
        raise cli_error("ERR-CONFIG-001")
    if selected == "unavailable":
        raise cli_error("ERR-CONFIG-006")
    return selected


def _signing_endpoints(environment: str) -> tuple[str, ...]:
    from sigstore.models import ClientTrustConfig

    if environment not in {"production", "staging"}:
        raise cli_error("ERR-CONFIG-001")
    try:
        if environment == "production":
            config = ClientTrustConfig.production(offline=True)
        else:
            config = ClientTrustConfig.staging(offline=True)
        signing = config.signing_config
        urls = (
            _endpoint_url(signing.get_fulcio()),
            *(_endpoint_url(client) for client in signing.get_tlogs()),
            *(_endpoint_url(client) for client in signing.get_tsas()),
        )
    except Exception:
        raise cli_error("ERR-CONFIG-006") from None
    return tuple(urls)


def _probe_signing_endpoints(endpoints: tuple[str, ...]) -> tuple[DoctorCheckData, ...]:
    import httpx

    checks: list[DoctorCheckData] = []
    with httpx.Client(
        follow_redirects=False,
        verify=True,
        timeout=httpx.Timeout(5.0),
        trust_env=False,
        headers={"User-Agent": "attest-cli/0.1"},
    ) as client:
        for endpoint in endpoints:
            try:
                response = client.head(endpoint)
                reachable = response.status_code < 500
            except httpx.RequestError:
                reachable = False
            checks.append(
                DoctorCheckData(
                    name=f"signing-endpoint:{endpoint}",
                    status="passed" if reachable else "warning",
                    code=None if reachable else "WARN-DOCTOR-003",
                    message=(
                        "Signing endpoint is reachable"
                        if reachable
                        else "Signing endpoint could not be reached"
                    ),
                    remediation=None
                    if reachable
                    else "Check explicit egress and TLS configuration",
                )
            )
    return tuple(checks)


def _handle_doctor(values: Mapping[str, object]) -> CommandResult:
    from attest_collect import collect_environment

    collection = collect_environment(os.environ)
    trusted_github = (
        collection.environment.kind.value == "github-actions" and collection.environment.trusted
    )
    resolved = _resolved_config(values, trusted_github=trusted_github)
    repository = Path(cast(str, resolved.value("repository.path")))
    selected_git = _selected_git_backend(resolved.value("repository.backend"))
    checks: list[DoctorCheckData] = [
        DoctorCheckData(
            name="git-backend",
            status="passed",
            code=None,
            message=f"Git backend selected: {selected_git}",
            remediation=None,
        ),
        DoctorCheckData(
            name="ambient-identity",
            status="passed" if trusted_github else "warning",
            code=None if trusted_github else "WARN-DOCTOR-001",
            message=(
                "Trusted ambient signing identity is available"
                if trusted_github
                else "Trusted ambient signing identity is unavailable"
            ),
            remediation=(
                None if trusted_github else "Run signing in a trusted workflow with id-token: write"
            ),
        ),
        DoctorCheckData(
            name="ci-environment",
            status="passed",
            code=None,
            message=f"CI environment detected: {collection.environment.kind.value}",
            remediation=None,
        ),
    ]
    policy = _load_resolved_policy(resolved, repository)
    policy_present = policy.source.path is not None
    checks.append(
        DoctorCheckData(
            name="policy",
            status="passed" if policy_present else "warning",
            code=None if policy_present else "WARN-DOCTOR-002",
            message=(
                f"Resolved policy is valid: {policy.source.path}"
                if policy_present
                else "No policy is configured; gating is reporting only"
            ),
            remediation=None
            if policy_present
            else "Configure a version 1 policy before enforcement",
        )
    )
    signing_environment = cast(str, resolved.value("signing.environment"))
    endpoints = _signing_endpoints(signing_environment)
    if values.get("probe_network") is True:
        endpoint_checks = _probe_signing_endpoints(endpoints)
    else:
        endpoint_checks = (
            DoctorCheckData(
                name="signing-endpoints",
                status="passed",
                code=None,
                message="Network reachability probe was not requested",
                remediation=None,
            ),
        )
    checks.extend(endpoint_checks)
    has_warning = any(item.status == "warning" for item in checks)
    verification_environment = (
        "supplied"
        if resolved.value("verification.trustConfigFile") is not None
        else cast(str, resolved.value("verification.environment"))
    )
    return CommandResult(
        "warning" if has_warning else "success",
        0,
        DoctorData(
            git_backend=cast(Literal["auto", "pygit2", "subprocess", "unavailable"], selected_git),
            signing_environment=cast(Literal["production", "staging"], signing_environment),
            verification_environment=cast(
                Literal["production", "staging", "supplied"], verification_environment
            ),
            store_backend=cast(
                Literal["git-ref", "filesystem", "oci"], resolved.value("storage.backend")
            ),
            checks=tuple(checks),
        ),
    )


_HANDLERS: Final[dict[str, Callable[[Mapping[str, object]], CommandResult]]] = {
    "init": _handle_init,
    "collect": _handle_collect,
    "build": _handle_build,
    "sign": _handle_sign,
    "push": _handle_push,
    "verify": _handle_verify,
    "gate": _handle_gate,
    "run": _handle_run,
    "inspect": _handle_inspect,
    "config-show": _handle_config_show,
    "doctor": _handle_doctor,
    "version": _handle_version,
}


def execute(command: str, values: Mapping[str, object]) -> int:
    """Execute one dispatched leaf and emit exactly one sanitised report."""
    handler = _HANDLERS.get(command)
    if handler is None:
        result = _failure_from_exception(command, cli_error("ERR-INTERNAL-001"))
    else:
        try:
            result = handler(values)
        except Exception as error:
            result = _failure_from_exception(command, error)
    report = make_report(
        command,
        result.outcome,
        result.exit_code,
        result.data,
        warnings=result.warnings,
        error=result.error,
    )
    json_output = values.get("json_output") is True
    no_color = values.get("no_color") is True
    emit_report(
        report,
        json_output=json_output,
        no_color=no_color,
        stdout=sys.stdout,
        stderr=sys.stderr,
        is_tty=sys.stderr.isatty(),
        no_color_environment="NO_COLOR" in os.environ,
    )
    return result.exit_code
