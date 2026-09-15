"""F-10 sign and push command orchestration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from attest_cli.app import app
from attest_cli.artifacts import serialize_statement
from attest_core import Statement
from attest_sign import Bundle, SigningEnvironment
from attest_store import OciSubject, StoreError, StoreRef


@pytest.mark.ac("AC-F10-110")
@pytest.mark.ac("AC-F10-230")
def test_sign_writes_exact_signer_bundle_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    monkeypatch.chdir(tmp_path)
    statement_path = tmp_path / "statement.json"
    statement_path.write_bytes(serialize_statement(statement))
    exact_bundle = b'{"opaque":"exact upstream bytes"}'

    class FakeSigner:
        def __init__(self, *, environment: SigningEnvironment, attempt_timeout: timedelta) -> None:
            assert environment is SigningEnvironment.STAGING
            assert attempt_timeout.total_seconds() == 9

        def sign(self, supplied: Statement) -> Bundle:
            assert supplied == statement
            return Bundle(
                raw=exact_bundle,
                environment=SigningEnvironment.STAGING,
                certificate_identity="workflow-identity",
                certificate_issuer="issuer",
                log_index=7,
                log_integrated_time=datetime(2026, 1, 1, tzinfo=UTC),
            )

    monkeypatch.setattr("attest_sign.SigstoreSigner", FakeSigner)
    output = tmp_path / "bundle.sigstore.json"
    result = CliRunner().invoke(
        app,
        [
            "sign",
            "--input",
            str(statement_path),
            "--output",
            str(output),
            "--signing-environment",
            "staging",
            "--signing-timeout-seconds",
            "9",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.read_bytes() == exact_bundle
    assert json.loads(result.stdout)["data"]["rekorIndex"] == 7


@pytest.mark.ac("AC-F10-210")
def test_filesystem_push_preserves_opaque_bundle_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    exact_bundle = b"not-json-but-an-exact-non-empty-bundle"
    bundle_path = tmp_path / "bundle.bin"
    bundle_path.write_bytes(exact_bundle)
    primary = tmp_path / "primary"
    fallback = tmp_path / "fallback"
    digest = "a" * 64

    result = CliRunner().invoke(
        app,
        [
            "push",
            "--input",
            str(bundle_path),
            "--change-set-digest",
            digest,
            "--store-backend",
            "filesystem",
            "--store-directory",
            str(primary),
            "--fallback-directory",
            str(fallback),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    stored = Path(report["data"]["storeRef"]["location"])
    assert stored.read_bytes() == exact_bundle
    assert report["data"]["fallbackPath"] is None


@pytest.mark.ac("AC-F10-210")
def test_git_ref_push_calls_local_put_then_explicit_remote_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    bundle = tmp_path / "bundle.bin"
    bundle.write_bytes(b"opaque")
    digest = "a" * 64
    reference = StoreRef(
        backend="git-ref",
        digest=digest,
        bundle_digest="b" * 64,
        location=f"refs/attestations/{digest}",
        stored_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    calls: list[str] = []

    class Filesystem:
        def __init__(self, directory: Path) -> None:
            self.directory = directory

    class GitStore:
        def __init__(self, repository_path: Path, **kwargs: object) -> None:
            calls.append("construct-git")
            assert repository_path == repository

        def push(self, supplied: StoreRef, remote: str, fallback: object) -> StoreRef:
            calls.append("push")
            assert supplied == reference
            assert remote == "upstream"
            return supplied

    def put(primary: object, fallback: object, supplied_digest: str, raw: bytes) -> StoreRef:
        calls.append("put")
        assert supplied_digest == digest
        assert raw == b"opaque"
        return reference

    monkeypatch.setattr("attest_store.FilesystemStore", Filesystem)
    monkeypatch.setattr("attest_store.GitRefStore", GitStore)
    monkeypatch.setattr("attest_store.put_with_fallback", put)
    result = CliRunner().invoke(
        app,
        [
            "push",
            "--input",
            str(bundle),
            "--change-set-digest",
            digest,
            "--repository",
            str(repository),
            "--store-backend",
            "git-ref",
            "--git-remote",
            "upstream",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == ["construct-git", "put", "push"]


@pytest.mark.ac("AC-F10-210")
def test_oci_push_constructs_complete_subject_and_safe_auth_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle.bin"
    bundle.write_bytes(b"opaque")
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    digest = "a" * 64
    reference = StoreRef(
        backend="oci",
        digest=digest,
        bundle_digest="b" * 64,
        location="ghcr.io/example/repo@sha256:" + "c" * 64,
        stored_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    seen: dict[str, object] = {}

    class Filesystem:
        def __init__(self, directory: Path) -> None:
            self.directory = directory

    class Oci:
        def __init__(
            self,
            repository: str,
            *,
            subject: OciSubject,
            staging_directory: Path,
            **kwargs: object,
        ) -> None:
            seen.update(
                repository=repository,
                subject=subject,
                staging=staging_directory,
                auth=kwargs["auth_config"],
            )

    monkeypatch.setattr("attest_store.FilesystemStore", Filesystem)
    monkeypatch.setattr("attest_store.OciStore", Oci)
    monkeypatch.setattr("attest_store.put_with_fallback", lambda *_args: reference)
    monkeypatch.setenv("ATTEST_OCI_AUTH_CONFIG_FILE", str(auth))
    result = CliRunner().invoke(
        app,
        [
            "push",
            "--input",
            str(bundle),
            "--change-set-digest",
            digest,
            "--store-backend",
            "oci",
            "--oci-repository",
            "ghcr.io/example/repo",
            "--oci-subject-media-type",
            "application/vnd.oci.image.manifest.v1+json",
            "--oci-subject-digest",
            "sha256:" + "d" * 64,
            "--oci-subject-size",
            "42",
            "--oci-staging-directory",
            str(tmp_path / "staging"),
            "--fallback-directory",
            str(tmp_path / "fallback"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    subject = cast(OciSubject, seen["subject"])
    assert subject.digest == "sha256:" + "d" * 64
    assert subject.size == 42
    assert seen["auth"] == auth


@pytest.mark.ac("AC-F10-070")
@pytest.mark.ac("AC-F10-210")
def test_push_command_retains_primary_exit_and_fallback_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    raw = b"exact opaque fallback bytes"
    bundle = tmp_path / "bundle.bin"
    bundle.write_bytes(raw)
    digest = "a" * 64
    fallback_path = tmp_path / "fallback" / "preserved.sigstore.json"

    def fail_with_fallback(
        primary: object,
        fallback: object,
        supplied_digest: str,
        supplied_raw: bytes,
    ) -> StoreRef:
        assert supplied_digest == digest
        assert supplied_raw == raw
        raise StoreError("ERR-STORE-402", fallback_path=str(fallback_path))

    monkeypatch.setattr("attest_store.put_with_fallback", fail_with_fallback)
    result = CliRunner().invoke(
        app,
        [
            "push",
            "--input",
            str(bundle),
            "--change-set-digest",
            digest,
            "--store-backend",
            "filesystem",
            "--store-directory",
            str(tmp_path / "primary"),
            "--fallback-directory",
            str(tmp_path / "fallback"),
            "--json",
        ],
    )

    assert result.exit_code == 6
    report = json.loads(result.stdout)
    assert report["error"]["code"] == "ERR-STORE-402"
    assert report["data"] == {"storeRef": None, "fallbackPath": str(fallback_path)}
