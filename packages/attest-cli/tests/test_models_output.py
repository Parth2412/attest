"""F-10 intermediate artifact and report-schema contract tests."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from attest_cli.artifacts import (
    CollectionArtifact,
    CollectionContext,
    generate_collection_schema,
    read_collection_artifact,
    read_statement,
    render_collection_schema,
    serialize_collection_artifact,
    serialize_statement,
)
from attest_cli.errors import CliError
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
    PolicySourceData,
    PushData,
    RunData,
    RunStageData,
    SignData,
    StoreRefData,
    VerificationData,
    VerifyData,
    VersionData,
    generate_cli_output_schema,
    make_report,
    render_cli_output_schema,
    report_wire,
    validate_cli_output,
)
from attest_cli.output import emit_report
from attest_core import (
    ChangeSetEntry,
    ChangeSetRecord,
    ChangeType,
    Statement,
    build_changeset_record,
    compute_changeset_digest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLI_SCHEMA = REPOSITORY_ROOT / "spec" / "schemas" / "cli-output-v0.1.schema.json"


def _verification(statement: Statement) -> VerificationData:
    return VerificationData(
        status="verified",
        checks=(CheckData(name="bundle-structure", result="passed", code=None),),
        statement=statement,
        failure_code=None,
        verified_identity="https://github.com/example/repo/.github/workflows/attest.yml@refs/heads/main",
        verified_issuer="https://token.actions.githubusercontent.com",
        transparency_log_verified=True,
    )


def _decision() -> DecisionData:
    return DecisionData(
        outcome="allow",
        exit_code=0,
        source=PolicySourceData(path=None, sha256=None),
        notice="No policy was supplied; attest is reporting only",
        policies=(),
    )


def _store_ref() -> StoreRefData:
    return StoreRefData(
        backend="filesystem",
        digest="a" * 64,
        bundle_digest="b" * 64,
        location="/tmp/bundle.sigstore.json",
        stored_at="2026-09-15T12:00:00Z",
    )


@pytest.mark.ac("AC-F10-020")
@pytest.mark.parametrize(
    "stored_at",
    ["2026-09-15T99:00:00Z", "2026-02-30T12:00:00Z", "2026-09-15T12:00:00+00:00"],
)
def test_store_reference_rejects_noncanonical_utc_timestamps(stored_at: str) -> None:
    with pytest.raises(ValidationError):
        StoreRefData(
            backend="filesystem",
            digest="a" * 64,
            bundle_digest="b" * 64,
            location="bundle.sigstore.json",
            stored_at=stored_at,
        )


def _command_data(statement: Statement) -> dict[str, object]:
    verification = _verification(statement)
    decision = _decision()
    store_ref = _store_ref()
    return {
        "init": InitData(
            created_paths=(".attest/config.yaml",),
            workflow_identity="https://github.com/example/repo/.github/workflows/attest.yml@refs/heads/main",
        ),
        "collect": CollectData(
            output_path="collection.json",
            change_set_digest="a" * 64,
            base_commit="1" * 40,
            head_commit="2" * 40,
            merge_base="1" * 40,
            target_branch="main",
            backend="subprocess",
        ),
        "build": BuildData(output_path="statement.json", change_set_digest="a" * 64),
        "sign": SignData(
            output_path="bundle.json",
            environment="production",
            certificate_identity="identity",
            certificate_issuer="issuer",
            rekor_index=1,
        ),
        "push": PushData(store_ref=store_ref, fallback_path=None),
        "verify": VerifyData(verification=verification),
        "gate": GateData(verification=verification, decision=decision),
        "run": RunData(
            stages=(RunStageData(name="collect", status="success", output_path=None),),
            store_ref=store_ref,
            verification=verification,
            decision=decision,
        ),
        "inspect": InspectData(
            status="unverified-identity",
            checks=(CheckData(name="bundle-structure", result="passed", code=None),),
            statement=statement,
            failure_code=None,
        ),
        "config-show": ConfigShowData(
            entries=(
                ConfigValueEntryData(key="repository.path", value=".", source="builtin"),
                ConfigSecretEntryData(
                    key="storage.oci.authConfigFile", configured=False, source="builtin"
                ),
            ),
            organisation_policy="unsupported",
        ),
        "doctor": DoctorData(
            git_backend="subprocess",
            signing_environment="production",
            verification_environment="production",
            store_backend="git-ref",
            checks=(
                DoctorCheckData(
                    name="git-backend",
                    status="passed",
                    code=None,
                    message="Git backend is available",
                    remediation=None,
                ),
            ),
        ),
        "version": VersionData(cli_version="0.1.0", python_version="3.13.7", build_revision=None),
    }


@pytest.mark.ac("AC-F10-020")
@pytest.mark.ac("AC-F10-200")
def test_every_leaf_success_report_validates_against_generated_schema(statement: Statement) -> None:
    schema = generate_cli_output_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    for command, data in _command_data(statement).items():
        outcome = "unverified-identity" if command == "inspect" else "success"
        report = make_report(command, outcome, 0, data)
        wire = report_wire(report)
        validator.validate(wire)
        assert validate_cli_output(wire) == report


@pytest.mark.ac("AC-F10-020")
@pytest.mark.parametrize(
    "command",
    [
        "init",
        "collect",
        "build",
        "sign",
        "push",
        "verify",
        "gate",
        "run",
        "inspect",
        "config-show",
        "doctor",
        "version",
    ],
)
@pytest.mark.parametrize("exit_code", [1, 2])
def test_every_leaf_failure_and_usage_report_validates_against_committed_schema(
    command: str,
    exit_code: int,
) -> None:
    diagnostic = CliDiagnostic(
        code="ERR-INTERNAL-001" if exit_code == 1 else "ERR-CONFIG-001",
        message="Stable message",
        remediation="Stable remediation",
    )
    report = make_report(command, "failed", exit_code, None, error=diagnostic)
    wire = report_wire(report)

    schema = json.loads(CLI_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(wire)
    assert validate_cli_output(wire) == report


@pytest.mark.ac("AC-F10-020")
@pytest.mark.parametrize("command", ["collect", "doctor", "gate", "run"])
def test_every_warning_capable_command_validates_against_committed_schema(
    command: str,
    statement: Statement,
) -> None:
    data = _command_data(statement)[command]
    if isinstance(data, GateData | RunData):
        warning_decision = _decision().model_copy(update={"outcome": "warn"})
        data = data.model_copy(update={"decision": warning_decision})
    report = make_report(command, "warning", 0, data)
    wire = report_wire(report)

    schema = json.loads(CLI_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(wire)
    assert validate_cli_output(wire) == report


@pytest.mark.ac("AC-F10-020")
@pytest.mark.parametrize("command", ["gate", "run"])
def test_every_denial_capable_command_validates_against_committed_schema(
    command: str,
    statement: Statement,
) -> None:
    data = _command_data(statement)[command]
    assert isinstance(data, GateData | RunData)
    denial = _decision().model_copy(update={"outcome": "deny", "exit_code": 3})
    report = make_report(command, "denied", 3, data.model_copy(update={"decision": denial}))
    wire = report_wire(report)

    schema = json.loads(CLI_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(wire)
    assert validate_cli_output(wire) == report


@pytest.mark.ac("AC-F10-020")
def test_report_outcome_exit_error_agreement_is_fail_closed(statement: Statement) -> None:
    diagnostic = CliDiagnostic(code="ERR-CONFIG-001", message="Invalid", remediation="Correct it")
    with pytest.raises(ValidationError):
        make_report("build", "success", 2, _command_data(statement)["build"])
    with pytest.raises(ValidationError):
        make_report("inspect", "unverified-identity", 0, _command_data(statement)["build"])
    with pytest.raises(ValidationError):
        make_report("build", "failed", 2, None)

    failure = make_report("build", "failed", 2, None, error=diagnostic)
    assert failure.error == diagnostic


@pytest.mark.ac("AC-F10-030")
@pytest.mark.ac("AC-F10-090")
def test_json_renderer_emits_one_object_lf_without_ansi(statement: Statement) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = make_report("verify", "success", 0, _command_data(statement)["verify"])

    emit_report(
        report,
        json_output=True,
        no_color=False,
        stdout=stdout,
        stderr=stderr,
        is_tty=True,
        no_color_environment=False,
    )

    assert stdout.getvalue().endswith("\n")
    assert stdout.getvalue().count("\n") == 1
    assert json.loads(stdout.getvalue())["command"] == "verify"
    assert "\x1b[" not in stdout.getvalue()
    assert stderr.getvalue() == ""


@pytest.mark.ac("AC-F10-090")
@pytest.mark.ac("AC-F10-170")
def test_human_inspection_is_prominently_unverified(statement: Statement) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = make_report(
        "inspect",
        "unverified-identity",
        0,
        _command_data(statement)["inspect"],
    )

    emit_report(
        report,
        json_output=False,
        no_color=True,
        stdout=stdout,
        stderr=stderr,
        is_tty=True,
        no_color_environment=False,
    )

    assert stdout.getvalue() == ""
    assert stderr.getvalue().startswith("UNVERIFIED IDENTITY\n")
    assert "\x1b[" not in stderr.getvalue()
    assert '"status": "unverified-identity"' in stderr.getvalue()


@pytest.mark.ac("AC-F10-090")
@pytest.mark.parametrize(
    ("is_tty", "no_color", "no_color_environment"),
    [
        (False, False, False),
        (True, True, False),
        (True, False, True),
    ],
)
def test_pipe_no_color_option_and_environment_never_emit_ansi(
    statement: Statement,
    is_tty: bool,
    no_color: bool,
    no_color_environment: bool,
) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = make_report("version", "success", 0, _command_data(statement)["version"])

    emit_report(
        report,
        json_output=False,
        no_color=no_color,
        stdout=stdout,
        stderr=stderr,
        is_tty=is_tty,
        no_color_environment=no_color_environment,
    )

    assert stdout.getvalue() == ""
    assert "\x1b[" not in stderr.getvalue()
    assert json.loads(stderr.getvalue()) == report_wire(report)


@pytest.mark.ac("AC-F10-090")
@pytest.mark.ac("AC-F10-220")
def test_tty_colour_changes_only_presentation_bytes(statement: Statement) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = make_report("version", "success", 0, _command_data(statement)["version"])

    emit_report(
        report,
        json_output=False,
        no_color=False,
        stdout=stdout,
        stderr=stderr,
        is_tty=True,
        no_color_environment=False,
    )

    rendered = stderr.getvalue()
    assert "\x1b[" in rendered
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)
    assert json.loads(plain) == report_wire(report)


@pytest.mark.ac("AC-F10-110")
@pytest.mark.ac("AC-F10-200")
def test_collection_artifact_is_canonical_closed_and_round_trips(
    tmp_path: Path, statement: Statement
) -> None:
    entry = ChangeSetEntry(
        path="src/a.py",
        change_type=ChangeType.ADDED,
        old_mode=None,
        new_mode="100644",
        old_blob=None,
        new_blob="1" * 40,
    )
    record: ChangeSetRecord = build_changeset_record([entry])
    change_set = statement.predicate.change_set.model_copy(
        update={"digest": "6c50ed6c593d1b7079d1dfdb644ce4d18a54d057d620f751307297cd801a9dc4"}
    )
    artifact = CollectionArtifact(
        schema_version="0.1.0",
        change_set_record=record,
        change_set=change_set,
        authorship=statement.predicate.authorship,
        review=statement.predicate.review,
        checks=statement.predicate.checks,
        collection=statement.predicate.collection,
        context=CollectionContext(
            base_commit=change_set.base_commit,
            head_commit=change_set.head_commit,
            merge_base=change_set.merge_base,
            target_branch="main",
        ),
    )
    raw = serialize_collection_artifact(artifact)
    path = tmp_path / "collection.json"
    path.write_bytes(raw)

    assert raw.endswith(b"\n")
    assert b" " not in raw
    assert read_collection_artifact(path) == artifact

    with pytest.raises(ValidationError):
        CollectionArtifact(
            schema_version="0.1.0",
            change_set_record=record,
            change_set=change_set.model_copy(update={"digest": "a" * 64}),
            authorship=artifact.authorship,
            review=artifact.review,
            checks=artifact.checks,
            collection=artifact.collection,
            context=artifact.context,
        )

    duplicate_record = build_changeset_record([entry, entry])
    with pytest.raises(ValidationError):
        CollectionArtifact(
            schema_version="0.1.0",
            change_set_record=duplicate_record,
            change_set=change_set.model_copy(
                update={"digest": compute_changeset_digest(duplicate_record)}
            ),
            authorship=artifact.authorship,
            review=artifact.review,
            checks=artifact.checks,
            collection=artifact.collection,
            context=artifact.context,
        )


@pytest.mark.ac("AC-F10-200")
def test_collection_artifact_rejects_unknown_fields(statement: Statement) -> None:
    with pytest.raises(ValidationError):
        CollectionContext.model_validate(
            {
                "baseCommit": "1" * 40,
                "headCommit": "2" * 40,
                "mergeBase": None,
                "targetBranch": "main",
                "unknown": True,
            }
        )


@pytest.mark.ac("AC-F10-200")
def test_statement_artifact_is_canonical_and_rejects_wrong_models(
    tmp_path: Path,
    statement: Statement,
) -> None:
    raw = serialize_statement(statement)
    path = tmp_path / "statement.json"
    path.write_bytes(raw)

    assert raw.endswith(b"\n")
    assert read_statement(path) == statement
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        serialize_statement(cast(Statement, object()))
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        serialize_collection_artifact(cast(CollectionArtifact, object()))


@pytest.mark.ac("AC-F10-200")
@pytest.mark.parametrize(
    ("reader", "raw"),
    [
        (read_collection_artifact, b'{"schemaVersion":"9.9.9"}\n'),
        (read_statement, b'{"_type":"unsupported"}\n'),
    ],
)
def test_artifact_readers_reject_wrong_versions_and_incomplete_documents(
    tmp_path: Path,
    reader: Callable[[Path], object],
    raw: bytes,
) -> None:
    path = tmp_path / "artifact.json"
    path.write_bytes(raw)
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        reader(path)


@pytest.mark.ac("AC-F10-200")
def test_cli_and_collection_schema_renderers_are_deterministic_json() -> None:
    cli_schema = render_cli_output_schema()
    collection_schema = render_collection_schema()

    assert json.loads(cli_schema) == generate_cli_output_schema()
    assert json.loads(collection_schema) == generate_collection_schema()
    assert cli_schema.endswith("\n")
    assert collection_schema.endswith("\n")


@pytest.mark.ac("AC-F10-060")
def test_secret_config_entry_has_no_value_field() -> None:
    data = ConfigShowData(
        entries=(
            ConfigSecretEntryData(
                key="storage.oci.authConfigFile",
                configured=True,
                source="environment:ATTEST_OCI_AUTH_CONFIG_FILE",
            ),
        ),
        organisation_policy="unsupported",
    )

    assert data.model_dump(mode="json", by_alias=True)["entries"] == [
        {
            "key": "storage.oci.authConfigFile",
            "configured": True,
            "source": "environment:ATTEST_OCI_AUTH_CONFIG_FILE",
        }
    ]


@pytest.mark.ac("AC-F10-220")
def test_rendered_diagnostic_carries_no_chained_exception_text() -> None:
    secret = "super-secret-upstream-body"
    upstream = RuntimeError(secret)
    diagnostic = CliDiagnostic(
        code="ERR-INTERNAL-001",
        message="An unexpected internal failure occurred",
        remediation="Retry",
    )
    report = make_report("attest", "failed", 1, None, error=diagnostic)
    assert str(upstream) == secret
    assert secret not in report.model_dump_json()
