"""F-10 end-to-end run composition tests with deterministic public adapters."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from attest_cli import commands
from attest_cli.app import app
from attest_cli.artifacts import read_collection_artifact, read_statement
from attest_cli.commands import CommandResult
from attest_cli.config import load_config
from attest_cli.errors import cli_error
from attest_cli.models import CollectData
from attest_core import Statement
from attest_sign import (
    Bundle,
    CheckOutcome,
    IdentityConstraint,
    RepositoryConstraint,
    SigningEnvironment,
    TrustRootSource,
    VerificationResult,
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "remote", "add", "origin", "https://github.com/example/repo.git")
    source = repository / "example.txt"
    source.write_text("first\n", encoding="utf-8")
    _git(repository, "add", "example.txt")
    _git(repository, "commit", "-m", "first")
    base = _git(repository, "rev-parse", "HEAD")
    source.write_text("second\n", encoding="utf-8")
    _git(repository, "commit", "-am", "second")
    return repository, base, _git(repository, "rev-parse", "HEAD")


@pytest.mark.ac("AC-F10-110")
@pytest.mark.ac("AC-F10-140")
def test_run_uses_ordered_stages_exact_artifacts_and_one_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    monkeypatch.chdir(tmp_path)
    repository, base, head = _repository(tmp_path)
    exact_bundle = b"one exact signed bundle"
    signed_statements: list[Statement] = []
    repository_inputs: list[RepositoryConstraint | None] = []
    verify_calls: list[None] = []
    monkeypatch.setattr(
        "attest_collect.collect_environment", lambda _environment: statement.predicate.collection
    )

    class FakeSigner:
        def __init__(self, *, environment: SigningEnvironment, attempt_timeout: object) -> None:
            assert environment is SigningEnvironment.PRODUCTION

        def sign(self, supplied: Statement) -> Bundle:
            signed_statements.append(supplied)
            return Bundle(
                raw=exact_bundle,
                environment=SigningEnvironment.PRODUCTION,
                certificate_identity="identity",
                certificate_issuer="issuer",
                log_index=9,
                log_integrated_time=datetime(2026, 1, 1, tzinfo=UTC),
            )

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository_input: RepositoryConstraint | None,
    ) -> VerificationResult:
        verify_calls.append(None)
        repository_inputs.append(repository_input)
        assert raw == exact_bundle
        built_statement = signed_statements[0]
        return VerificationResult(
            status="verified",
            checks=[CheckOutcome("bundle-structure", "passed", None)],
            statement=built_statement,
            failure_code=None,
            verified_identity="identity",
            verified_issuer="issuer",
            transparency_log_verified=True,
        )

    monkeypatch.setattr("attest_sign.SigstoreSigner", FakeSigner)
    monkeypatch.setattr("attest_sign.verify", fake_verify)
    runner = CliRunner()
    standalone_collection = tmp_path / "standalone-collection.json"
    standalone_statement = tmp_path / "standalone-statement.json"
    standalone_bundle = tmp_path / "standalone-bundle.sigstore.json"
    common_collection_arguments = [
        "--repository",
        str(repository),
        "--base",
        base,
        "--head",
        head,
        "--target-branch",
        "main",
        "--git-backend",
        "subprocess",
        "--json",
    ]
    standalone_results = (
        runner.invoke(
            app,
            ["collect", "--output", str(standalone_collection), *common_collection_arguments],
        ),
        runner.invoke(
            app,
            [
                "build",
                "--input",
                str(standalone_collection),
                "--output",
                str(standalone_statement),
                "--json",
            ],
        ),
        runner.invoke(
            app,
            [
                "sign",
                "--input",
                str(standalone_statement),
                "--output",
                str(standalone_bundle),
                "--json",
            ],
        ),
    )
    assert [item.exit_code for item in standalone_results] == [0, 0, 0]
    config_loads: list[None] = []

    def tracked_load_config(**kwargs: object) -> object:
        config_loads.append(None)
        return load_config(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("attest_cli.config.load_config", tracked_load_config)
    output = tmp_path / "result.sigstore.json"
    work = tmp_path / "work"
    result = runner.invoke(
        app,
        [
            "run",
            "--repository",
            str(repository),
            "--output",
            str(output),
            "--work-directory",
            str(work),
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            "main",
            "--git-backend",
            "subprocess",
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--store-backend",
            "filesystem",
            "--store-directory",
            str(tmp_path / "store"),
            "--fallback-directory",
            str(tmp_path / "fallback"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert [stage["name"] for stage in report["data"]["stages"]] == [
        "collect",
        "build",
        "sign",
        "push",
        "verify",
        "gate",
    ]
    assert len(verify_calls) == 1
    assert len(config_loads) == 1
    assert output.read_bytes() == exact_bundle
    assert (work / "bundle.sigstore.json").read_bytes() == exact_bundle
    assert (work / "collection.json").read_bytes() == standalone_collection.read_bytes()
    assert (work / "statement.json").read_bytes() == standalone_statement.read_bytes()
    assert (work / "bundle.sigstore.json").read_bytes() == standalone_bundle.read_bytes()
    assert signed_statements[0] == signed_statements[1]
    assert read_statement(work / "statement.json") == signed_statements[0]
    artifact = read_collection_artifact(work / "collection.json")
    repository_input = repository_inputs[0]
    assert isinstance(repository_input, RepositoryConstraint)
    assert repository_input.base_revision == artifact.context.base_commit == base
    assert repository_input.head_revision == artifact.context.head_commit == head


@pytest.mark.ac("AC-F10-110")
def test_run_stage_failure_prevents_every_later_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[str] = []

    def collect(_values: object) -> CommandResult:
        calls.append("collect")
        return CommandResult(
            "success",
            0,
            CollectData(
                output_path="private",
                change_set_digest="a" * 64,
                base_commit="1" * 40,
                head_commit="2" * 40,
                merge_base="1" * 40,
                target_branch="main",
                backend="subprocess",
            ),
        )

    def build(_values: object) -> CommandResult:
        calls.append("build")
        raise cli_error("ERR-CONFIG-003")

    def forbidden(_values: object) -> CommandResult:
        raise AssertionError

    monkeypatch.setattr(commands, "_handle_collect", collect)
    monkeypatch.setattr(commands, "_handle_build", build)
    monkeypatch.setattr(commands, "_handle_sign", forbidden)
    monkeypatch.setattr(commands, "_handle_push", forbidden)
    monkeypatch.setattr(commands, "_handle_verify", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--output",
            str(tmp_path / "bundle.json"),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert calls == ["collect", "build"]
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-003"
    assert not (tmp_path / "bundle.json").exists()
