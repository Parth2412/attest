"""Closed CLI output models and generated machine-output schema."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Final, Literal, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    TypeAdapter,
    model_validator,
)
from pydantic.alias_generators import to_camel

from attest_core import Statement

NonEmpty = Annotated[str, Field(strict=True, min_length=1)]
Sha256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
GitOid = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{40}$")]
_INVALID_TIMESTAMP: Final[str] = "timestamp must be canonical second-precision RFC 3339 UTC"


def _canonical_utc_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(_INVALID_TIMESTAMP) from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(_INVALID_TIMESTAMP)
    return value


UtcTime = Annotated[
    str,
    Field(strict=True, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"),
    AfterValidator(_canonical_utc_time),
]
type JsonScalar = StrictBool | StrictInt | str | None
type Outcome = Literal["success", "warning", "denied", "failed", "unverified-identity"]

_EXIT_DISAGREEMENT: Final[str] = "CLI outcome and exit code disagree"
_MISSING_ERROR: Final[str] = "failed reports require one diagnostic"
_UNEXPECTED_ERROR: Final[str] = "non-failed reports require data and no error"
_INVALID_INSPECTION: Final[str] = "only inspect can report unverified identity"
_DECISION_DISAGREEMENT: Final[str] = "policy Decision and report disagree"


class OutputModel(BaseModel):
    """Provide immutable, closed camel-case output behavior."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class CliDiagnostic(OutputModel):
    code: NonEmpty
    message: NonEmpty
    remediation: NonEmpty


class CheckData(OutputModel):
    name: NonEmpty
    result: Literal["passed", "failed", "skipped"]
    code: str | None


class VerificationData(OutputModel):
    status: Literal["verified", "verified-untrusted-environment", "failed"]
    checks: tuple[CheckData, ...]
    statement: Statement | None
    failure_code: str | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: StrictBool


class PolicySourceData(OutputModel):
    path: str | None
    sha256: Sha256 | None


class PredicateResultData(OutputModel):
    name: NonEmpty
    status: Literal["passed", "failed", "not-applicable", "unknown"]
    reason: NonEmpty
    detail: str | None


class PolicyResultData(OutputModel):
    policy_id: NonEmpty
    matched: StrictBool | None
    on_violation: Literal["block", "warn"]
    predicates: tuple[PredicateResultData, ...]


class DecisionData(OutputModel):
    outcome: Literal["allow", "warn", "deny"]
    exit_code: Literal[0, 3, 4, 5]
    source: PolicySourceData
    notice: str | None
    policies: tuple[PolicyResultData, ...]


class StoreRefData(OutputModel):
    backend: Literal["git-ref", "filesystem", "oci"]
    digest: Sha256
    bundle_digest: Sha256
    location: NonEmpty
    stored_at: UtcTime


class InitData(OutputModel):
    created_paths: tuple[NonEmpty, ...]
    workflow_identity: NonEmpty


class CollectData(OutputModel):
    output_path: NonEmpty
    change_set_digest: Sha256
    base_commit: GitOid
    head_commit: GitOid
    merge_base: GitOid | None
    target_branch: NonEmpty
    backend: Literal["pygit2", "subprocess"]


class BuildData(OutputModel):
    output_path: NonEmpty
    change_set_digest: Sha256


class SignData(OutputModel):
    output_path: NonEmpty
    environment: Literal["production", "staging"]
    certificate_identity: NonEmpty
    certificate_issuer: NonEmpty
    rekor_index: Annotated[int, Field(strict=True, ge=0)]


class PushData(OutputModel):
    store_ref: StoreRefData | None
    fallback_path: str | None


class VerifyData(OutputModel):
    verification: VerificationData


class GateData(OutputModel):
    verification: VerificationData
    decision: DecisionData


class RunStageData(OutputModel):
    name: Literal["collect", "build", "sign", "push", "verify", "gate"]
    status: Literal["success", "warning", "denied", "failed"]
    output_path: str | None


class RunData(OutputModel):
    stages: tuple[RunStageData, ...]
    store_ref: StoreRefData | None
    verification: VerificationData
    decision: DecisionData


class InspectData(OutputModel):
    status: Literal["unverified-identity", "failed"]
    checks: tuple[CheckData, ...]
    statement: Statement | None
    failure_code: str | None


class ConfigValueEntryData(OutputModel):
    key: NonEmpty
    value: JsonScalar
    source: NonEmpty


class ConfigSecretEntryData(OutputModel):
    key: NonEmpty
    configured: StrictBool
    source: NonEmpty


type ConfigEntryData = ConfigValueEntryData | ConfigSecretEntryData


class ConfigShowData(OutputModel):
    entries: tuple[ConfigEntryData, ...]
    organisation_policy: Literal["unsupported"]


class DoctorCheckData(OutputModel):
    name: NonEmpty
    status: Literal["passed", "warning", "failed"]
    code: str | None
    message: NonEmpty
    remediation: str | None


class DoctorData(OutputModel):
    git_backend: Literal["auto", "pygit2", "subprocess", "unavailable"]
    signing_environment: Literal["production", "staging"]
    verification_environment: Literal["production", "staging", "supplied"]
    store_backend: Literal["git-ref", "filesystem", "oci"]
    checks: tuple[DoctorCheckData, ...]


class VersionData(OutputModel):
    cli_version: NonEmpty
    python_version: NonEmpty
    build_revision: str | None


class _Report(OutputModel):
    schema_version: Literal["0.1.0"]
    command: str
    outcome: Outcome
    exit_code: StrictInt
    data: object
    warnings: tuple[CliDiagnostic, ...]
    error: CliDiagnostic | None = None

    @model_validator(mode="after")
    def _outcome_agrees(self) -> _Report:
        if self.outcome in {"success", "warning", "unverified-identity"}:
            valid_exit = self.exit_code == 0
        elif self.outcome == "denied":
            valid_exit = self.command in {"gate", "run"} and self.exit_code in {3, 4, 5}
        else:
            valid_exit = self.exit_code in {1, 2, 4, 5, 6}
        if not valid_exit:
            raise ValueError(_EXIT_DISAGREEMENT)
        if self.outcome == "failed":
            if self.error is None:
                raise ValueError(_MISSING_ERROR)
        elif self.error is not None or self.data is None:
            raise ValueError(_UNEXPECTED_ERROR)
        if self.outcome == "unverified-identity" and self.command != "inspect":
            raise ValueError(_INVALID_INSPECTION)
        decision: DecisionData | None = None
        if isinstance(self.data, GateData | RunData):
            decision = self.data.decision
        if decision is not None:
            expected = {"allow": "success", "warn": "warning", "deny": "denied"}[decision.outcome]
            if self.outcome != expected or self.exit_code != decision.exit_code:
                raise ValueError(_DECISION_DISAGREEMENT)
        return self


class AttestReport(_Report):
    command: Literal["attest"]
    data: None


class InitReport(_Report):
    command: Literal["init"]
    data: InitData | None


class CollectReport(_Report):
    command: Literal["collect"]
    data: CollectData | None


class BuildReport(_Report):
    command: Literal["build"]
    data: BuildData | None


class SignReport(_Report):
    command: Literal["sign"]
    data: SignData | None


class PushReport(_Report):
    command: Literal["push"]
    data: PushData | None


class VerifyReport(_Report):
    command: Literal["verify"]
    data: VerifyData | None


class GateReport(_Report):
    command: Literal["gate"]
    data: GateData | None


class RunReport(_Report):
    command: Literal["run"]
    data: RunData | None


class InspectReport(_Report):
    command: Literal["inspect"]
    data: InspectData | None


class ConfigShowReport(_Report):
    command: Literal["config-show"]
    data: ConfigShowData | None


class DoctorReport(_Report):
    command: Literal["doctor"]
    data: DoctorData | None


class VersionReport(_Report):
    command: Literal["version"]
    data: VersionData | None


type CliReport = Annotated[
    AttestReport
    | InitReport
    | CollectReport
    | BuildReport
    | SignReport
    | PushReport
    | VerifyReport
    | GateReport
    | RunReport
    | InspectReport
    | ConfigShowReport
    | DoctorReport
    | VersionReport,
    Field(discriminator="command"),
]
_REPORT_ADAPTER: TypeAdapter[CliReport] = TypeAdapter(CliReport)


class CliOutputDocument(RootModel[CliReport]):
    """Expose the discriminated report union to schema generation."""


def make_report(
    command: str,
    outcome: str,
    exit_code: int,
    data: object,
    *,
    warnings: tuple[CliDiagnostic, ...] = (),
    error: CliDiagnostic | None = None,
) -> CliReport:
    """Validate and construct one command report."""
    return _REPORT_ADAPTER.validate_python(
        {
            "schemaVersion": "0.1.0",
            "command": command,
            "outcome": outcome,
            "exitCode": exit_code,
            "data": data,
            "warnings": warnings,
            "error": error,
        }
    )


def validate_cli_output(value: object) -> CliReport:
    """Validate an arbitrary machine report against the runtime union."""
    return _REPORT_ADAPTER.validate_python(value)


def report_wire(report: CliReport) -> dict[str, object]:
    """Serialize a complete report while omitting only the optional top-level error."""
    wire = cast(dict[str, object], report.model_dump(mode="json", by_alias=True))
    if wire["error"] is None:
        del wire["error"]
    return wire


def generate_cli_output_schema() -> dict[str, object]:
    """Generate the CLI output Draft 2020-12 schema."""
    schema = CliOutputDocument.model_json_schema(by_alias=True, mode="validation")
    return cast(
        dict[str, object],
        {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema},
    )


def render_cli_output_schema() -> str:
    """Render deterministic CLI output schema text."""
    return json.dumps(generate_cli_output_schema(), indent=2, sort_keys=True) + "\n"
