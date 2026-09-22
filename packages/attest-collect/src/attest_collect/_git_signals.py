"""Hardened, read-only Git plumbing for F-03 claim sources."""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Final

_FULL_OID: Final[re.Pattern[bytes]] = re.compile(rb"[0-9a-f]{40}")
_SAFE_GIT_CONFIG: Final[tuple[str, ...]] = (
    "core.fsmonitor=false",
    f"core.hooksPath={os.devnull}",
)
_MALFORMED_GIT_OUTPUT = "Git returned malformed signal data"


class GitSignalError(RuntimeError):
    """Represent an opaque read failure inside an optional F-03 collector."""


class GitSignalUnavailableError(GitSignalError):
    """Represent an unavailable Git executable."""


class GitSignalRepositoryError(GitSignalError):
    """Represent a path that Git cannot open as a repository."""


class GitSignalRevisionError(GitSignalError):
    """Represent a commit that is unavailable or malformed."""


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["LC_ALL"] = "C"
    return environment


class GitSignalReader:
    """Read raw commits, parsed trailers, and notes without executing repository hooks."""

    def __init__(self, repo_path: Path) -> None:
        executable = shutil.which("git")
        if executable is None:
            raise GitSignalUnavailableError
        self._executable = executable
        self._repo_path = repo_path
        try:
            result = self._run("rev-parse", "--git-dir")
        except OSError as error:
            raise GitSignalUnavailableError from error
        if result.returncode != 0:
            raise GitSignalRepositoryError

    def _run(
        self,
        *arguments: str,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = [self._executable, "--no-replace-objects"]
        for setting in _SAFE_GIT_CONFIG:
            command.extend(("-c", setting))
        command.extend(("-C", os.fspath(self._repo_path), *arguments))
        return subprocess.run(  # noqa: S603  # nosec B603
            command,
            input=input_bytes,
            capture_output=True,
            check=False,
            env=_git_environment(),
        )

    def validate_commit(self, oid: str) -> None:
        """Require one already-resolved lowercase full OID to identify a readable commit."""
        try:
            encoded = oid.encode("ascii")
        except UnicodeEncodeError as error:
            raise GitSignalRevisionError from error
        if _FULL_OID.fullmatch(encoded) is None:
            raise GitSignalRevisionError
        result = self._run("cat-file", "-e", f"{oid}^{{commit}}")
        if result.returncode != 0:
            raise GitSignalRevisionError

    def commit_oids(self, base_commit: str, head_commit: str) -> tuple[str, ...]:
        """Return the complete base-exclusive reachable range sorted by full OID."""
        result = self._run("rev-list", f"{base_commit}..{head_commit}")
        if result.returncode != 0:
            raise GitSignalError
        values = result.stdout.splitlines()
        if any(_FULL_OID.fullmatch(value) is None for value in values):
            raise GitSignalError(_MALFORMED_GIT_OUTPUT)
        return tuple(sorted(value.decode("ascii") for value in values))

    def raw_commit_message(self, oid: str) -> bytes:
        """Return exact commit-message bytes after the raw commit header separator."""
        result = self._run("cat-file", "commit", oid)
        if result.returncode != 0:
            raise GitSignalError
        separator = result.stdout.find(b"\n\n")
        if separator < 0:
            raise GitSignalError(_MALFORMED_GIT_OUTPUT)
        return result.stdout[separator + 2 :]

    def parsed_trailers(self, message: bytes) -> tuple[tuple[bytes, bytes], ...]:
        """Use Git's installed trailer parser and retain its ordered token/value output."""
        result = self._run("interpret-trailers", "--parse", input_bytes=message)
        if result.returncode != 0:
            raise GitSignalError
        trailers: list[tuple[bytes, bytes]] = []
        for line in result.stdout.splitlines():
            token, separator, value = line.partition(b":")
            if not separator or not token:
                raise GitSignalError(_MALFORMED_GIT_OUTPUT)
            trailers.append((token, value.lstrip(b" \t")))
        return tuple(trailers)

    def notes_ref_exists(self, notes_ref: str) -> bool:
        """Validate the configured notes namespace and report whether it exists."""
        if not notes_ref.startswith("refs/notes/"):
            raise GitSignalError
        valid = self._run("check-ref-format", notes_ref)
        if valid.returncode != 0:
            raise GitSignalError
        result = self._run("show-ref", "--verify", "--quiet", notes_ref)
        if result.returncode == 1:
            return False
        if result.returncode != 0:
            raise GitSignalError
        return True

    def note_blob(self, notes_ref: str, commit_oid: str) -> bytes | None:
        """Return the exact note blob attached to a commit, when one exists."""
        result = self._run("notes", f"--ref={notes_ref}", "list", commit_oid)
        if result.returncode == 1:
            return None
        if result.returncode != 0:
            raise GitSignalError
        fields = result.stdout.split()
        if not fields:
            return None
        if len(fields) != 1 or _FULL_OID.fullmatch(fields[0]) is None:
            raise GitSignalError(_MALFORMED_GIT_OUTPUT)
        blob = self._run("cat-file", "blob", fields[0].decode("ascii"))
        if blob.returncode != 0:
            raise GitSignalError
        return blob.stdout
