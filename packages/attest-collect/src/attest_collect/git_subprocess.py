"""Git CLI ChangeSet backend governed by BRD-F02 and ADR-007."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
from pathlib import Path

from attest_collect.protocols import (
    BackendName,
    BackendUnavailableError,
    NotGitRepositoryError,
    RevisionResolutionError,
)
from attest_core import ChangeSetEntry, ChangeType, encode_git_path

# ADR-007 requires this fallback; every invocation uses an absolute executable and argv.

_STATUS_MAP = {
    b"A": ChangeType.ADDED,
    b"D": ChangeType.DELETED,
    b"M": ChangeType.MODIFIED,
    b"T": ChangeType.TYPECHANGE,
}
_DIFF_FAILED = "git diff-tree failed"
_MALFORMED_SEQUENCE = "git diff-tree returned a malformed record sequence"
_MALFORMED_HEADER = "git diff-tree returned a malformed header"
_CONFIG_FAILED = "git config failed"
_STATUS_FAILED = "git status failed"
_SAFE_GIT_CONFIG = ("core.fsmonitor=false", f"core.hooksPath={os.devnull}")


def _mode(value: bytes) -> str | None:
    decoded = value.decode("ascii")
    return None if decoded == "000000" else decoded


def _oid(value: bytes, mode: bytes) -> str | None:
    return None if mode == b"000000" else value.decode("ascii")


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


class SubprocessBackend:
    """Read committed Git objects with Git plumbing (REQ-F02-010 through REQ-F02-170)."""

    name: BackendName = "subprocess"

    def __init__(self, repo_path: Path) -> None:
        executable = shutil.which("git")
        if executable is None:
            raise BackendUnavailableError
        self._executable = executable
        self._repo_path = repo_path
        try:
            result = self._run("rev-parse", "--git-dir")
        except OSError as error:
            raise BackendUnavailableError from error
        except ValueError as error:
            raise NotGitRepositoryError from error
        if result.returncode != 0:
            raise NotGitRepositoryError

    @classmethod
    def is_available(cls) -> bool:
        """Return whether Git can be resolved to an executable path (REQ-F02-160)."""
        return shutil.which("git") is not None

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        command = [self._executable, "--no-replace-objects"]
        for setting in _SAFE_GIT_CONFIG:
            command.extend(("-c", setting))
        command.extend(("-C", os.fspath(self._repo_path), *arguments))
        return subprocess.run(  # noqa: S603  # nosec B603
            command,
            capture_output=True,
            check=False,
            env=_git_environment(),
        )

    def _is_shallow(self) -> bool:
        result = self._run("rev-parse", "--is-shallow-repository")
        return result.returncode == 0 and result.stdout.strip() == b"true"

    def resolve_commit(self, rev: str) -> str:
        """Resolve a revspec safely and require a commit object (REQ-F02-120)."""
        try:
            result = self._run("rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
        except (OSError, ValueError) as error:
            raise RevisionResolutionError(revision=rev, is_shallow=self._is_shallow()) from error
        if result.returncode != 0:
            raise RevisionResolutionError(revision=rev, is_shallow=self._is_shallow())
        try:
            return result.stdout.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise RevisionResolutionError(revision=rev, is_shallow=self._is_shallow()) from error

    def merge_base(self, a: str, b: str) -> str:
        """Return Git's merge base for two resolved commit OIDs (REQ-F02-090/100)."""
        result = self._run("merge-base", a, b)
        if result.returncode != 0:
            raise RevisionResolutionError(revision=f"{a} {b}", is_shallow=self._is_shallow())
        return result.stdout.decode("ascii").strip()

    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]:
        """Parse raw tree transitions without similarity detection (REQ-F02-010 through 080)."""
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
            raise RuntimeError(_DIFF_FAILED)
        fields = result.stdout.split(b"\0")
        if fields and fields[-1] == b"":
            fields.pop()
        if len(fields) % 2 != 0:
            raise ValueError(_MALFORMED_SEQUENCE)

        entries: list[ChangeSetEntry] = []
        for index in range(0, len(fields), 2):
            header = fields[index]
            raw_path = fields[index + 1]
            parts = header.split(b" ")
            if len(parts) != 5 or not parts[0].startswith(b":"):
                raise ValueError(_MALFORMED_HEADER)
            old_mode = parts[0][1:]
            new_mode = parts[1]
            change_type = _STATUS_MAP[parts[4]]
            entries.append(
                ChangeSetEntry(
                    path=encode_git_path(raw_path),
                    change_type=change_type,
                    old_mode=_mode(old_mode),
                    new_mode=_mode(new_mode),
                    old_blob=_oid(parts[2], old_mode),
                    new_blob=_oid(parts[3], new_mode),
                )
            )
        return entries

    def repository_url(self) -> str | None:
        """Return origin without a shell or configuration changes (REQ-F02-110/180)."""
        result = self._run("config", "--get", "remote.origin.url")
        if result.returncode == 1:
            return None
        if result.returncode != 0:
            raise RuntimeError(_CONFIG_FAILED)
        return result.stdout.rstrip(b"\r\n").decode("utf-8", errors="surrogateescape")

    def is_dirty(self) -> bool:
        """Report relevant uncommitted changes (REQ-F02-030/040/130)."""
        result = self._run("status", "--porcelain=v1", "-z", "--untracked-files=all")
        if result.returncode != 0:
            raise RuntimeError(_STATUS_FAILED)
        return bool(result.stdout)
