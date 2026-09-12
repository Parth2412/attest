"""Programmatic real-repository fixtures for BRD-F02."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True, slots=True)
class GitCase:
    """Identify a committed tree-to-tree collection case."""

    name: str
    path: Path
    base: str
    head: str


def run_git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git without a shell and return byte-preserving output."""
    result = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def _oid(repository: Path, revision: str = "HEAD") -> str:
    return run_git(repository, "rev-parse", "--verify", revision).stdout.decode("ascii").strip()


def _init(repository: Path) -> None:
    repository.mkdir(parents=True)
    run_git(repository, "init", "--quiet", "--initial-branch=main")
    run_git(repository, "config", "user.name", "attest tests")
    run_git(repository, "config", "user.email", "attest@example.test")
    run_git(repository, "config", "core.fileMode", "true")
    run_git(repository, "remote", "add", "origin", "git@github.com:Org/Repo.git")


def _commit(repository: Path, message: str, *, allow_empty: bool = False) -> str:
    run_git(repository, "add", "--all")
    arguments = ["commit", "--quiet", "-m", message]
    if allow_empty:
        arguments.insert(1, "--allow-empty")
    run_git(repository, *arguments)
    return _oid(repository)


def _case_root(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    root = tmp_path_factory.mktemp(name)
    repository = root / "repo"
    _init(repository)
    return repository


@pytest.fixture(scope="session")
def empty_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "empty-repo")
    base = _commit(repository, "base", allow_empty=True)
    head = _commit(repository, "head", allow_empty=True)
    return GitCase("empty-repo", repository, base, head)


@pytest.fixture(scope="session")
def single_add_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "single-add")
    base = _commit(repository, "base", allow_empty=True)
    (repository / "a.txt").write_bytes(b"added\n")
    head = _commit(repository, "add a")
    return GitCase("single-add", repository, base, head)


@pytest.fixture
def trailer_repo(tmp_path: Path) -> GitCase:
    repository = tmp_path / "trailer-repo"
    _init(repository)
    base = _commit(repository, "base", allow_empty=True)
    (repository / "a.txt").write_bytes(b"added\n")
    head = _commit(
        repository,
        "change\n\n"
        "Co-Authored-By: Jane Doe <jane@example.com>\n"
        "Co-Authored-By: Tool Bot <bot@example.test>",
    )
    return GitCase("trailer-repo", repository, base, head)


@pytest.fixture
def duplicate_claim_repo(tmp_path: Path) -> GitCase:
    repository = tmp_path / "duplicate-claim-repo"
    _init(repository)
    base = _commit(repository, "base", allow_empty=True)
    (repository / "a.txt").write_bytes(b"added\n")
    head = _commit(
        repository,
        "change\n\n"
        "X-Attest-Claim: agent=trailer-agent; "
        "claim-id=01890f5e-7b8a-7cc3-98c4-dc0c0c07398f",
    )
    return GitCase("duplicate-claim-repo", repository, base, head)


@pytest.fixture(scope="session")
def modify_delete_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "modify-delete")
    (repository / "modify.txt").write_bytes(b"before\n")
    (repository / "delete.txt").write_bytes(b"delete\n")
    base = _commit(repository, "base")
    (repository / "modify.txt").write_bytes(b"after\n")
    (repository / "delete.txt").unlink()
    head = _commit(repository, "modify and delete")
    return GitCase("modify-delete", repository, base, head)


@pytest.fixture(scope="session")
def rename_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "rename")
    old_path = repository / "old.txt"
    old_path.write_bytes(b"same\n")
    base = _commit(repository, "base")
    old_path.rename(repository / "new.txt")
    head = _commit(repository, "rename")
    return GitCase("rename", repository, base, head)


@pytest.fixture(scope="session")
def copy_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "copy")
    base = _commit(repository, "base", allow_empty=True)
    (repository / "copy-a.txt").write_bytes(b"same\n")
    (repository / "copy-b.txt").write_bytes(b"same\n")
    head = _commit(repository, "add copies")
    return GitCase("copy", repository, base, head)


@pytest.fixture(scope="session")
def mode_change_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "mode-change")
    script = repository / "run.sh"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o644)
    base = _commit(repository, "base")
    script.chmod(0o755)
    head = _commit(repository, "make executable")
    return GitCase("mode-change", repository, base, head)


@pytest.fixture(scope="session")
def symlink_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "symlink")
    base = _commit(repository, "base", allow_empty=True)
    (repository / "latest").symlink_to("releases/current")
    head = _commit(repository, "add symlink")
    return GitCase("symlink", repository, base, head)


@pytest.fixture(scope="session")
def type_change_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "type-change")
    item = repository / "item"
    item.write_bytes(b"regular file\n")
    base = _commit(repository, "base")
    item.unlink()
    item.symlink_to("target")
    head = _commit(repository, "replace file with symlink")
    return GitCase("type-change", repository, base, head)


@pytest.fixture(scope="session")
def submodule_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    root = tmp_path_factory.mktemp("submodule")
    child = root / "child"
    _init(child)
    (child / "version.txt").write_bytes(b"one\n")
    child_base = _commit(child, "child base")
    (child / "version.txt").write_bytes(b"two\n")
    child_head = _commit(child, "child head")

    repository = root / "repo"
    _init(repository)
    run_git(
        repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{child_base},vendor/lib",
    )
    run_git(repository, "commit", "--quiet", "-m", "record submodule base")
    base = _oid(repository)
    run_git(
        repository,
        "update-index",
        "--cacheinfo",
        f"160000,{child_head},vendor/lib",
    )
    run_git(repository, "commit", "--quiet", "-m", "record submodule head")
    head = _oid(repository)
    return GitCase("submodule", repository, base, head)


@pytest.fixture(scope="session")
def unicode_paths_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "unicode-paths")
    base = _commit(repository, "base", allow_empty=True)
    (repository / "café.txt").write_bytes(b"utf8\n")
    (repository / "percent%.txt").write_bytes(b"percent\n")
    head = _commit(repository, "add unicode paths")
    return GitCase("unicode-paths", repository, base, head)


@pytest.fixture(scope="session")
def invalid_utf8_path_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "invalid-utf8-path")
    base = _commit(repository, "base", allow_empty=True)
    blob = (
        run_git(repository, "hash-object", "-w", "--stdin", input_bytes=b"invalid path byte\n")
        .stdout.decode("ascii")
        .strip()
    )
    tree_record = b"100644 blob " + blob.encode("ascii") + b"\tbad-\xff.txt\0"
    tree = (
        run_git(repository, "mktree", "-z", input_bytes=tree_record).stdout.decode("ascii").strip()
    )
    head = (
        run_git(repository, "commit-tree", tree, "-p", base, "-m", "add raw path")
        .stdout.decode("ascii")
        .strip()
    )
    return GitCase("invalid-utf8-path", repository, base, head)


@pytest.fixture(scope="session")
def binary_file_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "binary-file")
    base = _commit(repository, "base", allow_empty=True)
    (repository / "binary.dat").write_bytes(bytes(range(256)))
    head = _commit(repository, "add binary")
    return GitCase("binary-file", repository, base, head)


@pytest.fixture(scope="session")
def large_1500_files_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "large-1500-files")
    base = _commit(repository, "base", allow_empty=True)
    files = repository / "files"
    files.mkdir()
    for index in range(1500):
        (files / f"file-{index:04d}.txt").write_bytes(b"content\n")
    head = _commit(repository, "add 1500 files")
    return GitCase("large-1500-files", repository, base, head)


@pytest.fixture(scope="session")
def merge_commit_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    repository = _case_root(tmp_path_factory, "merge-commit")
    (repository / "base.txt").write_bytes(b"base\n")
    base = _commit(repository, "base")
    run_git(repository, "switch", "--quiet", "-c", "feature")
    (repository / "feature.txt").write_bytes(b"feature\n")
    _commit(repository, "feature")
    run_git(repository, "switch", "--quiet", "main")
    (repository / "main.txt").write_bytes(b"main\n")
    _commit(repository, "main")
    run_git(repository, "merge", "--quiet", "--no-ff", "feature", "-m", "merge")
    return GitCase("merge-commit", repository, base, _oid(repository))


@pytest.fixture(scope="session")
def shallow_clone_repo(tmp_path_factory: pytest.TempPathFactory) -> GitCase:
    root = tmp_path_factory.mktemp("shallow-clone")
    source = root / "source"
    _init(source)
    (source / "base.txt").write_bytes(b"base\n")
    base = _commit(source, "base")
    (source / "head.txt").write_bytes(b"head\n")
    head = _commit(source, "head")
    clone = root / "repo"
    result = subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", source.as_uri(), os.fspath(clone)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return GitCase("shallow-clone", clone, base, head)


@pytest.fixture(scope="session")
def conformance_cases(
    empty_repo: GitCase,
    single_add_repo: GitCase,
    modify_delete_repo: GitCase,
    rename_repo: GitCase,
    copy_repo: GitCase,
    mode_change_repo: GitCase,
    symlink_repo: GitCase,
    type_change_repo: GitCase,
    submodule_repo: GitCase,
    unicode_paths_repo: GitCase,
    invalid_utf8_path_repo: GitCase,
    binary_file_repo: GitCase,
    large_1500_files_repo: GitCase,
    merge_commit_repo: GitCase,
) -> tuple[GitCase, ...]:
    """Return every non-shallow BRD-F02 real-repository fixture."""
    return (
        empty_repo,
        single_add_repo,
        modify_delete_repo,
        rename_repo,
        copy_repo,
        mode_change_repo,
        symlink_repo,
        type_change_repo,
        submodule_repo,
        unicode_paths_repo,
        invalid_utf8_path_repo,
        binary_file_repo,
        large_1500_files_repo,
        merge_commit_repo,
    )
