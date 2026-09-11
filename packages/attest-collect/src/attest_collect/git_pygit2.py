"""Optional pygit2 ChangeSet backend governed by BRD-F02 and ADR-007."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from attest_collect.protocols import (
    BackendName,
    BackendUnavailableError,
    NotGitRepositoryError,
    RevisionResolutionError,
)
from attest_core import ChangeSetEntry, ChangeType, encode_git_path

if TYPE_CHECKING:
    import pygit2


def _mode(value: int) -> str | None:
    return None if value == 0 else f"{value:06o}"


def _oid(value: object, mode: int) -> str | None:
    return None if mode == 0 else str(value)


class Pygit2Backend:
    """Read committed Git objects with optional pygit2 (REQ-F02-010 through REQ-F02-170)."""

    name: BackendName = "pygit2"

    def __init__(self, repo_path: Path) -> None:
        try:
            import pygit2
        except (ImportError, OSError) as error:
            raise BackendUnavailableError from error
        try:
            self._repository: pygit2.Repository = pygit2.Repository(str(repo_path))
        except (pygit2.GitError, ValueError) as error:
            raise NotGitRepositoryError from error

    @classmethod
    def is_available(cls) -> bool:
        """Return whether the optional binding can be imported now (REQ-F02-160)."""
        try:
            import pygit2  # noqa: F401
        except (ImportError, OSError):
            return False
        return True

    def resolve_commit(self, rev: str) -> str:
        """Resolve a revspec and require that it peels to a commit (REQ-F02-120)."""
        import pygit2

        try:
            value = self._repository.revparse_single(rev).peel(pygit2.Commit)
        except (KeyError, ValueError) as error:
            raise RevisionResolutionError(
                revision=rev,
                is_shallow=self._repository.is_shallow,
            ) from error
        return str(value.id)

    def merge_base(self, a: str, b: str) -> str:
        """Return the common ancestor selected by libgit2 (REQ-F02-090/100)."""
        import pygit2

        value = self._repository.merge_base(pygit2.Oid(hex=a), pygit2.Oid(hex=b))
        if value is None:
            raise RevisionResolutionError(
                revision=f"{a} {b}", is_shallow=self._repository.is_shallow
            )
        return str(value)

    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]:
        """Extract tree transitions without similarity detection (REQ-F02-010 through 080)."""
        import pygit2

        base_commit = self._repository[base].peel(pygit2.Commit)
        head_commit = self._repository[head].peel(pygit2.Commit)
        difference = self._repository.diff(
            base_commit,
            head_commit,
            flags=pygit2.enums.DiffOption.INCLUDE_TYPECHANGE,
        )
        status_map = {
            pygit2.GIT_DELTA_ADDED: ChangeType.ADDED,
            pygit2.GIT_DELTA_DELETED: ChangeType.DELETED,
            pygit2.GIT_DELTA_MODIFIED: ChangeType.MODIFIED,
            pygit2.GIT_DELTA_TYPECHANGE: ChangeType.TYPECHANGE,
        }
        entries: list[ChangeSetEntry] = []
        for delta in difference.deltas:
            change_type = status_map[delta.status]
            raw_path = (
                delta.old_file.raw_path
                if change_type is ChangeType.DELETED
                else delta.new_file.raw_path
            )
            entries.append(
                ChangeSetEntry(
                    path=encode_git_path(raw_path),
                    change_type=change_type,
                    old_mode=_mode(delta.old_file.mode),
                    new_mode=_mode(delta.new_file.mode),
                    old_blob=_oid(delta.old_file.id, delta.old_file.mode),
                    new_blob=_oid(delta.new_file.id, delta.new_file.mode),
                )
            )
        return entries

    def repository_url(self) -> str | None:
        """Return origin without changing repository configuration (REQ-F02-110/180)."""
        try:
            remote = self._repository.remotes["origin"]
        except KeyError:
            return None
        return remote.url

    def is_dirty(self) -> bool:
        """Report relevant uncommitted changes (REQ-F02-030/040/130)."""
        return bool(self._repository.status(untracked_files="all", ignored=False))
