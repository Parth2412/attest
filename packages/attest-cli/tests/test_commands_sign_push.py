"""F-10 sign and push command orchestration tests."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from hashlib import sha256
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

        def import_remote(self, supplied_digest: str, remote: str) -> None:
            calls.append("import-remote")
            assert supplied_digest == digest
            assert remote == "upstream"

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
    assert calls == ["construct-git", "import-remote", "put", "push"]


@pytest.mark.ac("AC-F07-050")
@pytest.mark.ac("AC-F07-080")
@pytest.mark.ac("AC-F10-210")
def test_git_remote_import_failure_preserves_bundle_in_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-allocation transport failure retains the exact signed bytes locally."""
    monkeypatch.chdir(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    bundle = tmp_path / "bundle.bin"
    exact = b"signed bytes requiring preservation"
    bundle.write_bytes(exact)
    digest = "a" * 64
    fallback = tmp_path / "fallback"

    class GitStore:
        def __init__(self, repository_path: Path, **_kwargs: object) -> None:
            assert repository_path == repository

        def import_remote(self, supplied_digest: str, remote: str) -> None:
            assert supplied_digest == digest
            assert remote == "upstream"
            raise StoreError("ERR-STORE-402")

    monkeypatch.setattr("attest_store.GitRefStore", GitStore)
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
            "--fallback-directory",
            str(fallback),
            "--json",
        ],
    )

    assert result.exit_code == 6
    report = json.loads(result.stdout)
    preserved = fallback / f"{digest}.sigstore.json"
    assert report["error"]["code"] == "ERR-STORE-402"
    assert report["data"] == {"storeRef": None, "fallbackPath": str(preserved)}
    assert preserved.read_bytes() == exact


@pytest.mark.ac("AC-F07-080")
@pytest.mark.ac("AC-F10-210")
def test_git_remote_import_and_fallback_failure_reports_no_durable_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed import plus failed fallback is surfaced only as ERR-STORE-406."""
    monkeypatch.chdir(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    bundle = tmp_path / "bundle.bin"
    bundle.write_bytes(b"unretained signed bytes")
    digest = "a" * 64

    class GitStore:
        def __init__(self, repository_path: Path, **_kwargs: object) -> None:
            assert repository_path == repository

        def import_remote(self, _digest: str, _remote: str) -> None:
            raise StoreError("ERR-STORE-402")

    class FailingFilesystem:
        def __init__(self, _directory: Path) -> None:
            pass

        def put(self, _digest: str, _bundle: bytes) -> StoreRef:
            raise StoreError("ERR-STORE-404")

    monkeypatch.setattr("attest_store.GitRefStore", GitStore)
    monkeypatch.setattr("attest_store.FilesystemStore", FailingFilesystem)
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

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["error"]["code"] == "ERR-STORE-406"
    assert report["data"] is None


@pytest.mark.ac("AC-F07-010")
@pytest.mark.ac("AC-F07-030")
@pytest.mark.ac("AC-F10-210")
@pytest.mark.ac("AC-F11-190")
def test_fresh_git_checkouts_publish_distinct_bundles_for_one_changeset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two fresh CI-like checkouts retain denied and approved evidence as siblings."""
    monkeypatch.chdir(tmp_path)
    remote = tmp_path / "remote.git"
    first_repository = tmp_path / "first"
    second_repository = tmp_path / "second"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    for repository in (first_repository, second_repository):
        subprocess.run(
            ["git", "init", "-b", "main", str(repository)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "remote", "add", "origin", str(remote)],
            check=True,
            capture_output=True,
        )

    digest = "a" * 64
    first_bundle = tmp_path / "denied.sigstore.json"
    second_bundle = tmp_path / "approved.sigstore.json"
    first_bundle.write_bytes(b"denied evidence")
    second_bundle.write_bytes(b"approved evidence")
    reports: list[dict[str, object]] = []
    for repository, bundle, fallback_name in (
        (first_repository, first_bundle, "first-fallback"),
        (second_repository, second_bundle, "second-fallback"),
    ):
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
                "origin",
                "--fallback-directory",
                str(tmp_path / fallback_name),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.stdout
        reports.append(cast(dict[str, object], json.loads(result.stdout)))

    locations = [
        cast(
            str,
            cast(dict[str, object], cast(dict[str, object], report["data"])["storeRef"])[
                "location"
            ],
        )
        for report in reports
    ]
    assert locations[0] == f"refs/attestations/{digest}"
    assert locations[1] == (
        f"refs/attestations/{digest}-sha256-{sha256(b'approved evidence').hexdigest()}"
    )
    remote_refs = subprocess.run(
        ["git", "-C", str(remote), "for-each-ref", "--format=%(refname)", "refs/attestations/"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert sorted(remote_refs) == sorted(locations)


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
