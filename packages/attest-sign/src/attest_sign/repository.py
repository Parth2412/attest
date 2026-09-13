"""Independent read-only Git verification path governed by BRD-F08."""

from __future__ import annotations

import os
import shutil as _shutil
import subprocess as _subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from attest_core import (
    ChangeSetEntry,
    ChangeType,
    build_changeset_record,
    compute_changeset_digest,
    encode_git_path,
)

GIT_TIMEOUT_SECONDS: Final[int] = 30
_SAFE_GIT_CONFIG: Final[tuple[str, ...]] = (
    "core.fsmonitor=false",
    f"core.hooksPath={os.devnull}",
)
_STATUS_MAP: Final[dict[bytes, ChangeType]] = {
    b"A": ChangeType.ADDED,
    b"D": ChangeType.DELETED,
    b"M": ChangeType.MODIFIED,
    b"T": ChangeType.TYPECHANGE,
}


@dataclass(frozen=True, slots=True)
class RepositoryConstraint:
    """Identify one caller-selected committed ChangeSet."""

    path: Path
    base_revision: str
    head_revision: str


class RepositoryVerificationError(RuntimeError):
    """Signal a private repository-boundary failure."""


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _mode(value: bytes) -> str | None:
    decoded = value.decode("ascii")
    return None if decoded == "000000" else decoded


def _oid(value: bytes, mode: bytes) -> str | None:
    return None if mode == b"000000" else value.decode("ascii")


class _GitRepository:
    def __init__(self, path: Path) -> None:
        executable = _shutil.which("git")
        if executable is None:
            raise RepositoryVerificationError
        self._executable = executable
        self._path = path
        if self._run("rev-parse", "--git-dir").returncode != 0:
            raise RepositoryVerificationError

    def _run(self, *arguments: str) -> _subprocess.CompletedProcess[bytes]:
        command = [self._executable, "--no-replace-objects"]
        for setting in _SAFE_GIT_CONFIG:
            command.extend(("-c", setting))
        command.extend(("-C", os.fspath(self._path), *arguments))
        return _subprocess.run(  # noqa: S603  # nosec B603
            command,
            capture_output=True,
            check=False,
            env=_git_environment(),
            timeout=GIT_TIMEOUT_SECONDS,
        )

    def resolve_commit(self, revision: str) -> str:
        result = self._run(
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        )
        if result.returncode != 0:
            raise RepositoryVerificationError
        resolved = result.stdout.decode("ascii").strip()
        if len(resolved) != 40 or any(
            character not in "0123456789abcdef" for character in resolved
        ):
            raise RepositoryVerificationError
        return resolved

    def diff_entries(self, base: str, head: str) -> tuple[ChangeSetEntry, ...]:
        result = self._run(
            "-c",
            "core.quotepath=false",
            "diff-tree",
            "-r",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--raw",
            "-z",
            "--no-commit-id",
            "--no-abbrev",
            base,
            head,
            "--",
        )
        if result.returncode != 0:
            raise RepositoryVerificationError
        fields = result.stdout.split(b"\0")
        if fields and fields[-1] == b"":
            fields.pop()
        if len(fields) % 2 != 0:
            raise RepositoryVerificationError

        entries: list[ChangeSetEntry] = []
        for index in range(0, len(fields), 2):
            header = fields[index]
            path = fields[index + 1]
            parts = header.split(b" ")
            if len(parts) != 5 or not parts[0].startswith(b":"):
                raise RepositoryVerificationError
            old_mode = parts[0][1:]
            new_mode = parts[1]
            change_type = _STATUS_MAP.get(parts[4])
            if change_type is None:
                raise RepositoryVerificationError
            entries.append(
                ChangeSetEntry(
                    path=encode_git_path(path),
                    change_type=change_type,
                    old_mode=_mode(old_mode),
                    new_mode=_mode(new_mode),
                    old_blob=_oid(parts[2], old_mode),
                    new_blob=_oid(parts[3], new_mode),
                )
            )
        return tuple(entries)


def recompute_changeset_digest(constraint: RepositoryConstraint) -> str:
    """Recompute CSD-1 from explicit committed revisions (REQ-F08-110)."""
    try:
        repository = _GitRepository(constraint.path)
        base = repository.resolve_commit(constraint.base_revision)
        head = repository.resolve_commit(constraint.head_revision)
        record = build_changeset_record(repository.diff_entries(base, head))
        return compute_changeset_digest(record)
    except RepositoryVerificationError:
        raise
    except Exception:
        raise RepositoryVerificationError from None
