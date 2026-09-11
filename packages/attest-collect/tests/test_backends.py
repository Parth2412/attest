"""Real Git backend acceptance tests for BRD-F02."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest_collect.changeset import collect_changeset
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.protocols import BackendOverride, NotGitRepositoryError
from attest_core import ChangeType, decode_git_path

BACKENDS: tuple[BackendOverride, ...] = ("pygit2", "subprocess")
REPOSITORY_URL = "https://github.com/Org/Repo"


@pytest.mark.ac("AC-F02-010")
@pytest.mark.parametrize("backend", BACKENDS)
def test_rename_is_one_delete_and_one_add(rename_repo: Any, backend: BackendOverride) -> None:
    collection = collect_changeset(
        rename_repo.path, rename_repo.base, rename_repo.head, backend, repository_url=REPOSITORY_URL
    )
    assert [(entry.path, entry.change_type) for entry in collection.record.entries] == [
        ("new.txt", ChangeType.ADDED),
        ("old.txt", ChangeType.DELETED),
    ]


@pytest.mark.ac("AC-F02-020")
@pytest.mark.parametrize("backend", BACKENDS)
def test_identical_files_remain_independent_additions(
    copy_repo: Any, backend: BackendOverride
) -> None:
    collection = collect_changeset(
        copy_repo.path, copy_repo.base, copy_repo.head, backend, repository_url=REPOSITORY_URL
    )
    assert [entry.change_type for entry in collection.record.entries] == [
        ChangeType.ADDED,
        ChangeType.ADDED,
    ]
    assert collection.record.entries[0].new_blob == collection.record.entries[1].new_blob


@pytest.mark.ac("AC-F02-030")
@pytest.mark.ac("AC-F02-040")
@pytest.mark.parametrize("backend", BACKENDS)
def test_worktree_untracked_and_ignored_state_does_not_change_digest(
    single_add_repo: Any, backend: BackendOverride
) -> None:
    clean = collect_changeset(
        single_add_repo.path,
        single_add_repo.base,
        single_add_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    tracked = single_add_repo.path / "a.txt"
    untracked = single_add_repo.path / "untracked.txt"
    ignore_file = single_add_repo.path / ".gitignore"
    ignored = single_add_repo.path / "ignored.txt"
    original = tracked.read_bytes()
    try:
        tracked.write_bytes(b"uncommitted\n")
        untracked.write_bytes(b"untracked\n")
        ignore_file.write_text("ignored.txt\n", encoding="utf-8")
        ignored.write_bytes(b"ignored\n")
        dirty = collect_changeset(
            single_add_repo.path,
            single_add_repo.base,
            single_add_repo.head,
            backend,
            repository_url=REPOSITORY_URL,
        )
    finally:
        tracked.write_bytes(original)
        untracked.unlink(missing_ok=True)
        ignore_file.unlink(missing_ok=True)
        ignored.unlink(missing_ok=True)
    assert dirty.info.digest == clean.info.digest
    assert [entry.path for entry in dirty.record.entries] == ["a.txt"]


@pytest.mark.ac("AC-F02-050")
@pytest.mark.parametrize("backend", BACKENDS)
def test_mode_only_change_preserves_blob_identity(
    mode_change_repo: Any, backend: BackendOverride
) -> None:
    entry = collect_changeset(
        mode_change_repo.path,
        mode_change_repo.base,
        mode_change_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    ).record.entries[0]
    assert entry.change_type is ChangeType.MODIFIED
    assert (entry.old_mode, entry.new_mode) == ("100644", "100755")
    assert entry.old_blob == entry.new_blob


@pytest.mark.ac("AC-F02-060")
@pytest.mark.parametrize("backend", BACKENDS)
def test_gitlink_pointer_is_collected_as_a_commit_oid(
    submodule_repo: Any, backend: BackendOverride
) -> None:
    entry = collect_changeset(
        submodule_repo.path,
        submodule_repo.base,
        submodule_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    ).record.entries[0]
    assert entry.change_type is ChangeType.MODIFIED
    assert (entry.old_mode, entry.new_mode) == ("160000", "160000")
    assert entry.old_blob != entry.new_blob


@pytest.mark.ac("AC-F02-070")
@pytest.mark.parametrize("backend", BACKENDS)
def test_symlink_uses_the_link_target_blob(symlink_repo: Any, backend: BackendOverride) -> None:
    entry = collect_changeset(
        symlink_repo.path,
        symlink_repo.base,
        symlink_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    ).record.entries[0]
    assert entry.change_type is ChangeType.ADDED
    assert entry.new_mode == "120000"
    assert entry.new_blob is not None


@pytest.mark.parametrize("backend", BACKENDS)
def test_file_to_symlink_is_a_typechange(type_change_repo: Any, backend: BackendOverride) -> None:
    collection = collect_changeset(
        type_change_repo.path,
        type_change_repo.base,
        type_change_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    entry = collection.record.entries[0]
    assert entry.change_type is ChangeType.TYPECHANGE
    assert (entry.old_mode, entry.new_mode) == ("100644", "120000")
    assert entry.old_blob != entry.new_blob
    assert collection.info.stats.model_dump() == {
        "filesChanged": 1,
        "filesAdded": 0,
        "filesModified": 0,
        "filesDeleted": 0,
    }


@pytest.mark.ac("AC-F02-080")
@pytest.mark.parametrize("backend", BACKENDS)
def test_git_paths_are_encoded_from_raw_bytes(
    unicode_paths_repo: Any, invalid_utf8_path_repo: Any, backend: BackendOverride
) -> None:
    unicode_collection = collect_changeset(
        unicode_paths_repo.path,
        unicode_paths_repo.base,
        unicode_paths_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    invalid_collection = collect_changeset(
        invalid_utf8_path_repo.path,
        invalid_utf8_path_repo.base,
        invalid_utf8_path_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    assert [entry.path for entry in unicode_collection.record.entries] == [
        "caf%C3%A9.txt",
        "percent%25.txt",
    ]
    assert invalid_collection.record.entries[0].path == "bad-%FF.txt"
    assert decode_git_path(invalid_collection.record.entries[0].path) == b"bad-\xff.txt"
    repeated = collect_changeset(
        invalid_utf8_path_repo.path,
        invalid_utf8_path_repo.base,
        invalid_utf8_path_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    assert repeated.info.digest == invalid_collection.info.digest


@pytest.mark.ac("AC-F02-150")
@pytest.mark.parametrize("backend", BACKENDS)
def test_large_changeset_paths_are_truncated(
    large_1500_files_repo: Any, backend: BackendOverride
) -> None:
    collection = collect_changeset(
        large_1500_files_repo.path,
        large_1500_files_repo.base,
        large_1500_files_repo.head,
        backend,
        repository_url=REPOSITORY_URL,
    )
    assert len(collection.record.entries) == 1500
    assert collection.info.paths is not None
    assert len(collection.info.paths) == 1000
    assert collection.info.paths_truncated is True


@pytest.mark.ac("AC-F02-090")
def test_backend_merge_base_operations_match(merge_commit_repo: Any) -> None:
    native = Pygit2Backend(merge_commit_repo.path)
    command = SubprocessBackend(merge_commit_repo.path)
    assert (
        native.merge_base(merge_commit_repo.base, merge_commit_repo.head) == merge_commit_repo.base
    )
    assert (
        command.merge_base(merge_commit_repo.base, merge_commit_repo.head) == merge_commit_repo.base
    )


@pytest.mark.ac("AC-F02-190")
def test_pygit2_backend_rejects_non_repository(tmp_path: Any) -> None:
    with pytest.raises(NotGitRepositoryError):
        Pygit2Backend(tmp_path)


@pytest.mark.ac("AC-F02-180")
def test_real_backend_repository_discovery(single_add_repo: Any) -> None:
    assert Pygit2Backend(single_add_repo.path).repository_url() == "git@github.com:Org/Repo.git"
    assert SubprocessBackend(single_add_repo.path).repository_url() == "git@github.com:Org/Repo.git"


def test_subprocess_backend_ignores_git_environment_repository_override(
    single_add_repo: Any, empty_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_DIR", os.fspath(empty_repo.path / ".git"))
    backend = SubprocessBackend(single_add_repo.path)
    assert backend.resolve_commit(single_add_repo.head) == single_add_repo.head


def test_subprocess_backend_disables_repository_fsmonitor_hook(
    single_add_repo: Any, tmp_path: Path
) -> None:
    sentinel = tmp_path / "fsmonitor-invoked"
    hook = tmp_path / "fsmonitor"
    hook.write_text(f"#!/bin/sh\n: > '{sentinel}'\nprintf '\\n'\n", encoding="utf-8")
    hook.chmod(0o755)
    subprocess.run(
        ["git", "-C", os.fspath(single_add_repo.path), "config", "core.fsmonitor", os.fspath(hook)],
        check=True,
    )
    try:
        SubprocessBackend(single_add_repo.path).is_dirty()
        assert not sentinel.exists()
    finally:
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(single_add_repo.path),
                "config",
                "--unset-all",
                "core.fsmonitor",
            ],
            check=True,
        )


def test_subprocess_backend_ignores_git_replace_refs(single_add_repo: Any) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(single_add_repo.path),
            "replace",
            single_add_repo.head,
            single_add_repo.base,
        ],
        check=True,
    )
    try:
        collection = collect_changeset(
            single_add_repo.path,
            single_add_repo.base,
            single_add_repo.head,
            "subprocess",
            repository_url=REPOSITORY_URL,
        )
        assert [entry.path for entry in collection.record.entries] == ["a.txt"]
    finally:
        subprocess.run(
            ["git", "-C", os.fspath(single_add_repo.path), "replace", "-d", single_add_repo.head],
            check=True,
        )
