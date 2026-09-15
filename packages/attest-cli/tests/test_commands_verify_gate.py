"""F-10 verify and gate command orchestration tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from attest_cli.app import app
from attest_core import Statement
from attest_sign import (
    CheckOutcome,
    IdentityConstraint,
    RepositoryConstraint,
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


@pytest.mark.ac("AC-F10-100")
@pytest.mark.parametrize(
    "constraints",
    [(), ("--identity", "identity"), ("--issuer", "issuer")],
)
def test_missing_identity_stops_before_constructing_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constraints: tuple[str, ...],
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError

    monkeypatch.setattr("attest_sign.IdentityConstraint", forbidden)
    monkeypatch.setattr("attest_sign.verify", forbidden)
    result = CliRunner().invoke(
        app,
        ["verify", "--input", str(bundle), *constraints, "--json"],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-005"


@pytest.mark.ac("AC-F10-100")
def test_verify_passes_mandatory_constraints_and_selected_trust_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")
    seen: dict[str, object] = {}

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository: RepositoryConstraint | None,
    ) -> VerificationResult:
        seen.update(raw=raw, constraint=constraint, trust=trust, repository=repository)
        return VerificationResult(
            status="verified-untrusted-environment",
            checks=[CheckOutcome("bundle-structure", "passed", None)],
            statement=statement,
            failure_code=None,
            verified_identity="identity",
            verified_issuer="issuer",
            transparency_log_verified=True,
        )

    monkeypatch.setattr("attest_sign.verify", fake_verify)
    result = CliRunner().invoke(
        app,
        [
            "verify",
            "--input",
            str(bundle),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["raw"] == b"opaque"
    constraint = seen["constraint"]
    assert isinstance(constraint, IdentityConstraint)
    assert constraint.identity_pattern == "identity"
    assert constraint.issuer == "issuer"
    trust = seen["trust"]
    assert getattr(trust, "offline", None) is True
    assert seen["repository"] is None


@pytest.mark.ac("AC-F10-100")
def test_verify_passes_exact_supplied_trust_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")
    trust_config = tmp_path / "trust.json"
    trust_config.write_bytes(b'{"marker":"exact"}\n')
    seen: dict[str, object] = {}

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository: RepositoryConstraint | None,
    ) -> VerificationResult:
        seen.update(raw=raw, trust=trust)
        return VerificationResult(
            status="verified",
            checks=[CheckOutcome("bundle-structure", "passed", None)],
            statement=statement,
            failure_code=None,
            verified_identity="identity",
            verified_issuer="issuer",
            transparency_log_verified=True,
        )

    monkeypatch.setattr("attest_sign.verify", fake_verify)
    result = CliRunner().invoke(
        app,
        [
            "verify",
            "--input",
            str(bundle),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--trust-config-file",
            str(trust_config),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["raw"] == b"opaque"
    assert getattr(seen["trust"], "client_trust_config_json", None) == '{"marker":"exact"}\n'


@pytest.mark.ac("AC-F10-100")
@pytest.mark.parametrize(
    "repository_arguments",
    [
        ("--repository", "."),
        ("--base", "1" * 40),
        ("--head", "2" * 40),
        ("--repository", ".", "--base", "1" * 40),
    ],
)
def test_verify_repository_constraint_is_all_or_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repository_arguments: tuple[str, ...],
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError

    monkeypatch.setattr("attest_sign.verify", forbidden)
    result = CliRunner().invoke(
        app,
        [
            "verify",
            "--input",
            str(bundle),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            *repository_arguments,
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-001"


@pytest.mark.ac("AC-F10-020")
@pytest.mark.ac("AC-F10-070")
def test_standalone_verification_failure_retains_complete_typed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository_input: RepositoryConstraint | None,
    ) -> VerificationResult:
        return VerificationResult(
            status="failed",
            checks=[CheckOutcome("sigstore-dsse", "failed", "ERR-VERIFY-013")],
            statement=None,
            failure_code="ERR-VERIFY-013",
            verified_identity=None,
            verified_issuer=None,
            transparency_log_verified=False,
        )

    monkeypatch.setattr("attest_sign.verify", fake_verify)
    result = CliRunner().invoke(
        app,
        [
            "verify",
            "--input",
            str(bundle),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--json",
        ],
    )

    assert result.exit_code == 4, result.output
    report = json.loads(result.stdout)
    assert report["outcome"] == "failed"
    assert report["error"]["code"] == "ERR-VERIFY-013"
    assert report["data"]["verification"] == {
        "status": "failed",
        "checks": [{"name": "sigstore-dsse", "result": "failed", "code": "ERR-VERIFY-013"}],
        "statement": None,
        "failureCode": "ERR-VERIFY-013",
        "verifiedIdentity": None,
        "verifiedIssuer": None,
        "transparencyLogVerified": False,
    }


@pytest.mark.ac("AC-F10-070")
def test_missing_bundle_maps_to_required_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "verify",
            "--input",
            str(tmp_path / "missing.json"),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--json",
        ],
    )

    assert result.exit_code == 5
    assert json.loads(result.stdout)["error"]["code"] == "ERR-STORE-403"


@pytest.mark.ac("AC-F10-140")
def test_gate_uses_one_effective_changeset_and_denies_failed_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repository, base, head = _repository(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")
    seen: dict[str, object] = {}

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository_input: RepositoryConstraint | None,
    ) -> VerificationResult:
        seen.update(raw=raw, repository=repository_input)
        return VerificationResult(
            status="failed",
            checks=[CheckOutcome("changeset-recomputation", "failed", "ERR-VERIFY-010")],
            statement=None,
            failure_code="ERR-VERIFY-010",
            verified_identity=None,
            verified_issuer=None,
            transparency_log_verified=False,
        )

    monkeypatch.setattr("attest_sign.verify", fake_verify)
    result = CliRunner().invoke(
        app,
        [
            "gate",
            "--input",
            str(bundle),
            "--repository",
            str(repository),
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            "main",
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--git-backend",
            "subprocess",
            "--json",
        ],
    )

    assert result.exit_code == 4, result.output
    repository_input = seen["repository"]
    assert isinstance(repository_input, RepositoryConstraint)
    assert repository_input.base_revision == base
    assert repository_input.head_revision == head
    report = json.loads(result.stdout)
    assert report["outcome"] == "denied"
    assert report["data"]["decision"]["outcome"] == "deny"
    assert report["data"]["decision"]["exitCode"] == 4
    assert "error" not in report


@pytest.mark.ac("AC-F10-070")
@pytest.mark.ac("AC-F10-140")
def test_gate_preserves_complete_paths_and_policy_denial_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    monkeypatch.chdir(tmp_path)
    repository, base, head = _repository(tmp_path)
    bundle = tmp_path / "bundle.json"
    bundle.write_bytes(b"opaque")
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        """version: 1
policies:
  - id: BLOCK-MISSING-CHECK
    match:
      branches: [main]
      paths: ["**"]
    require:
      attestation: true
      checks:
        mustPass: [definitely-absent-check]
    onViolation: block
""",
        encoding="utf-8",
    )

    def fake_verify(
        raw: bytes,
        constraint: IdentityConstraint,
        trust: TrustRootSource,
        repository_input: RepositoryConstraint | None,
    ) -> VerificationResult:
        return VerificationResult(
            status="verified",
            checks=[CheckOutcome("bundle-structure", "passed", None)],
            statement=statement,
            failure_code=None,
            verified_identity="identity",
            verified_issuer="issuer",
            transparency_log_verified=True,
        )

    monkeypatch.setattr("attest_sign.verify", fake_verify)
    result = CliRunner().invoke(
        app,
        [
            "gate",
            "--input",
            str(bundle),
            "--repository",
            str(repository),
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            "main",
            "--policy",
            str(policy),
            "--identity",
            "identity",
            "--issuer",
            "issuer",
            "--git-backend",
            "subprocess",
            "--json",
        ],
    )

    assert result.exit_code == 3, result.output
    report = json.loads(result.stdout)
    assert report["outcome"] == "denied"
    assert "error" not in report
    assert report["data"]["decision"]["outcome"] == "deny"
    assert report["data"]["decision"]["exitCode"] == 3
    predicate = next(
        item
        for item in report["data"]["decision"]["policies"][0]["predicates"]
        if item["name"] == "require.checks.mustPass"
    )
    assert predicate["reason"] == "check-missing"
    assert predicate["detail"] == "definitely-absent-check"
