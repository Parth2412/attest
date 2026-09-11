"""Cross-backend and normative-vector conformance for F-02."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest_collect.changeset import collect_changeset
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_core import ChangeSetEntry, ChangeSetRecord, build_changeset_record, decode_git_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VECTOR_ROOT = REPOSITORY_ROOT / "spec" / "testvectors"
REPOSITORY_URL = "https://github.com/Org/Repo"


@pytest.mark.ac("AC-F02-170")
def test_full_real_repository_matrix_is_identical_between_backends(
    conformance_cases: Any,
) -> None:
    for case in conformance_cases:
        native = collect_changeset(
            case.path,
            case.base,
            case.head,
            Pygit2Backend(case.path),
            repository_url=REPOSITORY_URL,
        )
        command = collect_changeset(
            case.path,
            case.base,
            case.head,
            SubprocessBackend(case.path),
            repository_url=REPOSITORY_URL,
        )
        assert native.record.model_dump() == command.record.model_dump(), case.name
        assert native.info.digest == command.info.digest, case.name


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _tree(repository: Path, entries: dict[bytes, tuple[str, str]]) -> str:
    children: dict[bytes, dict[bytes, tuple[str, str]]] = {}
    direct: dict[bytes, tuple[str, str]] = {}
    for path, value in entries.items():
        first, separator, remainder = path.partition(b"/")
        if separator:
            children.setdefault(first, {})[remainder] = value
        else:
            direct[first] = value
    for name, nested in children.items():
        direct[name] = ("040000", _tree(repository, nested))

    records: list[bytes] = []
    for name, (mode, oid) in sorted(direct.items()):
        if mode == "040000":
            object_type = b"tree"
        elif mode == "160000":
            object_type = b"commit"
        else:
            object_type = b"blob"
        records.append(
            mode.encode("ascii")
            + b" "
            + object_type
            + b" "
            + oid.encode("ascii")
            + b"\t"
            + name
            + b"\0"
        )
    return (
        _git(repository, "mktree", "--missing", "-z", input_bytes=b"".join(records))
        .decode("ascii")
        .strip()
    )


def _commit(repository: Path, tree: str, parent: str | None = None) -> str:
    arguments = ["commit-tree", tree, "-m", "vector"]
    if parent is not None:
        arguments[2:2] = ["-p", parent]
    return _git(repository, *arguments).decode("ascii").strip()


def _vector_repository(tmp_path: Path, record: ChangeSetRecord) -> tuple[Path, str, str]:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "attest vectors")
    _git(repository, "config", "user.email", "attest@example.test")
    base_entries: dict[bytes, tuple[str, str]] = {}
    head_entries: dict[bytes, tuple[str, str]] = {}
    for entry in record.entries:
        raw_path = decode_git_path(entry.path)
        if entry.old_mode is not None and entry.old_blob is not None:
            base_entries[raw_path] = (entry.old_mode, entry.old_blob)
        if entry.new_mode is not None and entry.new_blob is not None:
            head_entries[raw_path] = (entry.new_mode, entry.new_blob)
    base = _commit(repository, _tree(repository, base_entries))
    head = _commit(repository, _tree(repository, head_entries), base)
    _git(repository, "update-ref", "refs/heads/main", head)
    return repository, base, head


@pytest.mark.vectors
@pytest.mark.ac("AC-F02-170")
@pytest.mark.parametrize(
    "vector_path",
    sorted(VECTOR_ROOT.glob("csd1-*/input.json")),
    ids=lambda path: path.parent.name,
)
def test_normative_csd1_vector_is_reconstructed_from_real_git_trees(
    vector_path: Path, tmp_path: Path
) -> None:
    payload: dict[str, Any] = json.loads(vector_path.read_text(encoding="utf-8"))
    expected = build_changeset_record(
        tuple(ChangeSetEntry.model_validate(item) for item in payload["entries"])
    )
    repository, base, head = _vector_repository(tmp_path, expected)
    for backend in (Pygit2Backend(repository), SubprocessBackend(repository)):
        actual = collect_changeset(
            repository,
            base,
            head,
            backend,
            repository_url=REPOSITORY_URL,
        )
        assert actual.record == expected
