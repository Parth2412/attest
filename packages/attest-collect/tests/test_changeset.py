"""Collector orchestration, diagnostics, and public error tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from attest_collect.changeset import (
    ChangeSetCollection,
    _normalise_repository_url,
    collect_changeset,
)
from attest_collect.errors import CollectError
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.protocols import BackendName, BackendOverride, RevisionResolutionError
from attest_core import ChangeSetEntry, ChangeType

BASE = "1" * 40
HEAD = "2" * 40
MERGE_BASE = "3" * 40
CHECKED_OUT = "4" * 40
_NATIVE_FAILURE = "injected native failure"
_PRIVATE_FAILURE = "private backend detail"


def _added_entry() -> ChangeSetEntry:
    return ChangeSetEntry(
        path="src/a.py",
        change_type=ChangeType.ADDED,
        old_mode=None,
        new_mode="100644",
        old_blob=None,
        new_blob="5" * 40,
    )


class FakeBackend:
    """Controllable protocol implementation for public-boundary tests."""

    def __init__(
        self,
        *,
        name: BackendName = "pygit2",
        dirty: bool = False,
        repository: str | None = "git@github.com:Discovered/Repo.git",
        checked_out: str = HEAD,
    ) -> None:
        self.name = name
        self.dirty = dirty
        self.repository = repository
        self.checked_out = checked_out
        self.merge_base_calls = 0
        self.repository_calls = 0

    def resolve_commit(self, revision: str) -> str:
        values = {"base": BASE, "head": HEAD, "merge": MERGE_BASE, "HEAD": self.checked_out}
        try:
            return values[revision]
        except KeyError as error:
            raise RevisionResolutionError(revision=revision, is_shallow=False) from error

    def merge_base(self, first: str, second: str) -> str:
        self.merge_base_calls += 1
        return MERGE_BASE

    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]:
        return [_added_entry()]

    def repository_url(self) -> str | None:
        self.repository_calls += 1
        return self.repository

    def is_dirty(self) -> bool:
        return self.dirty


def _collect(repository_path: Path, backend: FakeBackend, **kwargs: str) -> ChangeSetCollection:
    return collect_changeset(repository_path, "base", "head", backend, **kwargs)


@pytest.mark.ac("AC-F02-090")
def test_base_revision_is_used_without_implicit_merge_base(single_add_repo: Any) -> None:
    backend = FakeBackend()
    collection = _collect(single_add_repo.path, backend)
    assert collection.info.base_commit == BASE
    assert backend.merge_base_calls == 0


@pytest.mark.ac("AC-F02-100")
def test_explicit_merge_base_is_the_diff_base_and_signed_context(single_add_repo: Any) -> None:
    backend = FakeBackend()
    collection = _collect(single_add_repo.path, backend, merge_base_rev="merge")
    assert collection.info.base_commit == MERGE_BASE
    assert collection.info.merge_base == MERGE_BASE
    assert set(collection.record.model_dump()) == {"algorithm", "entries"}
    assert backend.merge_base_calls == 0


@pytest.mark.ac("AC-F02-110")
def test_scp_repository_url_is_normalised(single_add_repo: Any) -> None:
    collection = _collect(single_add_repo.path, FakeBackend())
    assert collection.info.repository == "https://github.com/Discovered/Repo"


@pytest.mark.ac("AC-F02-120")
@pytest.mark.parametrize("backend", ["pygit2", "subprocess"])
def test_missing_full_diff_base_in_shallow_clone_has_specific_error(
    shallow_clone_repo: Any, backend: BackendOverride
) -> None:
    with pytest.raises(CollectError) as captured:
        collect_changeset(
            shallow_clone_repo.path,
            shallow_clone_repo.base,
            "HEAD",
            backend,
            repository_url="https://github.com/Org/Repo",
        )
    assert captured.value.code == "ERR-COLLECT-101"
    assert "fetch-depth" in captured.value.remediation


@pytest.mark.ac("AC-F02-120")
@pytest.mark.parametrize("backend", ["pygit2", "subprocess"])
@pytest.mark.parametrize("revision", ["unknown-ref", "not-an-oid"])
def test_other_unresolved_revisions_have_general_revision_error(
    shallow_clone_repo: Any, revision: str, backend: BackendOverride
) -> None:
    with pytest.raises(CollectError) as captured:
        collect_changeset(
            shallow_clone_repo.path,
            revision,
            "HEAD",
            backend,
            repository_url="https://github.com/Org/Repo",
        )
    assert captured.value.code == "ERR-COLLECT-103"


@pytest.mark.ac("AC-F02-120")
@pytest.mark.parametrize("backend", ["pygit2", "subprocess"])
def test_non_commit_revision_has_general_revision_error(
    single_add_repo: Any, backend: BackendOverride
) -> None:
    result = subprocess.run(
        ["git", "-C", str(single_add_repo.path), "rev-parse", f"{single_add_repo.head}:a.txt"],
        capture_output=True,
        check=True,
        text=True,
    )
    with pytest.raises(CollectError) as captured:
        collect_changeset(
            single_add_repo.path,
            result.stdout.strip(),
            single_add_repo.head,
            backend,
            repository_url="https://github.com/Org/Repo",
        )
    assert captured.value.code == "ERR-COLLECT-103"


@pytest.mark.ac("AC-F02-130")
def test_dirty_and_head_mismatch_warnings_are_structured_and_digest_neutral(
    single_add_repo: Any,
) -> None:
    clean = _collect(single_add_repo.path, FakeBackend())
    warned = _collect(single_add_repo.path, FakeBackend(dirty=True, checked_out=CHECKED_OUT))
    assert [warning.code for warning in warned.warnings] == [
        "WARN-COLLECT-001",
        "WARN-COLLECT-002",
    ]
    assert all(warning.message and warning.remediation for warning in warned.warnings)
    assert warned.info.digest == clean.info.digest


@pytest.mark.ac("AC-F02-140")
def test_stats_count_only_files_and_named_change_types(single_add_repo: Any) -> None:
    collection = _collect(single_add_repo.path, FakeBackend())
    assert collection.info.stats.model_dump() == {
        "filesChanged": 1,
        "filesAdded": 1,
        "filesModified": 0,
        "filesDeleted": 0,
    }


@pytest.mark.ac("AC-F02-160")
def test_auto_prefers_pygit2_and_falls_back_only_on_unavailability(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    preferred = collect_changeset(
        single_add_repo.path,
        single_add_repo.base,
        single_add_repo.head,
        "auto",
        repository_url="https://github.com/Org/Repo",
    )
    assert preferred.diagnostics.backend == "pygit2"

    monkeypatch.setattr(Pygit2Backend, "is_available", classmethod(lambda cls: False))
    fallback = collect_changeset(
        single_add_repo.path,
        single_add_repo.base,
        single_add_repo.head,
        "auto",
        repository_url="https://github.com/Org/Repo",
    )
    assert fallback.diagnostics.backend == "subprocess"


@pytest.mark.ac("AC-F02-160")
def test_unknown_and_unavailable_backend_selections_are_coded(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown = cast(BackendOverride, "unknown")
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        collect_changeset(single_add_repo.path, "base", "head", unknown)

    monkeypatch.setattr(Pygit2Backend, "is_available", classmethod(lambda cls: False))
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        collect_changeset(single_add_repo.path, "base", "head", "pygit2")


@pytest.mark.ac("AC-F02-160")
def test_operational_failure_does_not_switch_backend(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fail_diff(self: Any, base: str, head: str) -> list[ChangeSetEntry]:
        raise OSError(_NATIVE_FAILURE)

    def record_fallback(self: Any, base: str, head: str) -> list[ChangeSetEntry]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(Pygit2Backend, "diff_entries", fail_diff)
    monkeypatch.setattr(SubprocessBackend, "diff_entries", record_fallback)
    with pytest.raises(CollectError, match="ERR-COLLECT-106"):
        collect_changeset(
            single_add_repo.path,
            single_add_repo.base,
            single_add_repo.head,
            "auto",
            repository_url="https://github.com/Org/Repo",
        )
    assert called is False


@pytest.mark.ac("AC-F02-180")
def test_explicit_repository_identity_wins_and_invalid_identity_is_coded(
    single_add_repo: Any,
) -> None:
    backend = FakeBackend(repository="https://wrong.example/repo.git")
    collection = _collect(
        single_add_repo.path,
        backend,
        repository_url="ssh://user:secret@GitHub.com/Explicit/Repo.git/",
    )
    assert collection.info.repository == "https://github.com/Explicit/Repo"
    assert backend.repository_calls == 0

    for invalid_backend, override in (
        (FakeBackend(repository=None), None),
        (FakeBackend(repository="local/path"), None),
        (FakeBackend(), "not a URL"),
    ):
        with pytest.raises(CollectError) as captured:
            collect_changeset(
                single_add_repo.path,
                "base",
                "head",
                invalid_backend,
                repository_url=override,
            )
        assert captured.value.code == "ERR-COLLECT-105"
        assert captured.value.remediation


class FailingBackend(FakeBackend):
    """Raise an opaque backend error at the diff boundary."""

    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]:
        raise PermissionError(_PRIVATE_FAILURE)


class BrokenResolutionBackend(FakeBackend):
    """Raise an unclassified operation error while resolving input."""

    def resolve_commit(self, revision: str) -> str:
        raise OSError(_NATIVE_FAILURE)


class InvalidOidBackend(FakeBackend):
    """Return backend data that violates the full-OID contract."""

    def resolve_commit(self, revision: str) -> str:
        return "short"


class BrokenIdentityBackend(FakeBackend):
    """Fail while discovering repository identity."""

    def repository_url(self) -> str | None:
        raise OSError(_NATIVE_FAILURE)


@pytest.mark.ac("AC-F02-190")
@pytest.mark.parametrize("name", ["pygit2", "subprocess"])
def test_backend_failures_are_stable_public_errors_with_private_causes(
    single_add_repo: Any, name: BackendName
) -> None:
    with pytest.raises(CollectError) as captured:
        _collect(single_add_repo.path, FailingBackend(name=name))
    error = captured.value
    assert error.code == "ERR-COLLECT-106"
    assert error.message
    assert error.remediation
    assert "private backend detail" not in str(error)
    assert isinstance(error.__cause__, PermissionError)


@pytest.mark.ac("AC-F02-190")
@pytest.mark.parametrize("backend", ["pygit2", "subprocess"])
def test_non_repository_is_a_stable_public_error(tmp_path: Path, backend: BackendOverride) -> None:
    with pytest.raises(CollectError) as captured:
        collect_changeset(
            tmp_path,
            "base",
            "head",
            backend,
            repository_url="https://github.com/Org/Repo",
        )
    assert captured.value.code == "ERR-COLLECT-102"


@pytest.mark.ac("AC-F02-110")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://USER:secret@Example.COM:8443/Org/Repo.git", "https://example.com:8443/Org/Repo"),
        ("git://Example.COM/Org/Repo/", "https://example.com/Org/Repo"),
        ("ssh://git@Example.COM/Org/Repo.git/", "https://example.com/Org/Repo"),
    ],
)
def test_supported_remote_url_forms_are_canonical(value: str, expected: str) -> None:
    assert _normalise_repository_url(value) == expected


@pytest.mark.ac("AC-F02-180")
@pytest.mark.parametrize(
    "value",
    [
        " file://host/repo",
        "file://host/repo",
        "https://host:invalid/repo",
        "https:///repo",
        "https://host/",
        "https://host/double//segment",
        "https://host/repo?token=secret",
        "https://host/repo#fragment",
        "https://host/repo.git.git",
        "https://[invalid/repo",
        "https://host/re\npo",
        "https://host/repo\0suffix",
        "https://host/repo\udcff",
    ],
)
def test_non_normalisable_remote_forms_are_rejected(value: str) -> None:
    with pytest.raises(CollectError, match="ERR-COLLECT-105"):
        _normalise_repository_url(value)


@pytest.mark.ac("AC-F02-160")
def test_auto_errors_when_no_backend_is_available(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Pygit2Backend, "is_available", classmethod(lambda cls: False))
    monkeypatch.setattr(SubprocessBackend, "is_available", classmethod(lambda cls: False))
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        collect_changeset(single_add_repo.path, "base", "head", "auto")


@pytest.mark.ac("AC-F02-160")
def test_backend_availability_races_are_coded_without_masking_repository_errors(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def become_unavailable(self: Any, repo_path: Path) -> None:
        from attest_collect.protocols import BackendUnavailableError

        raise BackendUnavailableError

    monkeypatch.setattr(Pygit2Backend, "__init__", become_unavailable)
    fallback = collect_changeset(
        single_add_repo.path,
        single_add_repo.base,
        single_add_repo.head,
        "auto",
        repository_url="https://github.com/Org/Repo",
    )
    assert fallback.diagnostics.backend == "subprocess"
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        collect_changeset(single_add_repo.path, "base", "head", "pygit2")


@pytest.mark.ac("AC-F02-160")
def test_git_executable_availability_race_is_coded(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disappear(self: Any, *arguments: str) -> Any:
        raise FileNotFoundError

    monkeypatch.setattr(Pygit2Backend, "is_available", classmethod(lambda cls: False))
    monkeypatch.setattr(SubprocessBackend, "is_available", classmethod(lambda cls: True))
    monkeypatch.setattr(SubprocessBackend, "_run", disappear)
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        collect_changeset(single_add_repo.path, "base", "head", "auto")


@pytest.mark.ac("AC-F02-160")
def test_invalid_injected_backend_name_is_rejected(single_add_repo: Any) -> None:
    backend = FakeBackend(name=cast(BackendName, "invalid"))
    with pytest.raises(CollectError, match="ERR-COLLECT-104"):
        _collect(single_add_repo.path, backend)


@pytest.mark.ac("AC-F02-190")
@pytest.mark.parametrize(
    ("backend", "code"),
    [
        (BrokenResolutionBackend(), "ERR-COLLECT-106"),
        (InvalidOidBackend(), "ERR-COLLECT-106"),
        (BrokenIdentityBackend(), "ERR-COLLECT-105"),
    ],
)
def test_unclassified_boundary_failures_are_mapped(
    single_add_repo: Any, backend: FakeBackend, code: str
) -> None:
    with pytest.raises(CollectError) as captured:
        _collect(single_add_repo.path, backend)
    assert captured.value.code == code
