"""Typed Git backend boundary governed by BRD-F02 and ADR-032."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from attest_core import ChangeSetEntry

BackendName = Literal["pygit2", "subprocess"]
BackendOverride = Literal["auto", "pygit2", "subprocess"]


class BackendUnavailableError(RuntimeError):
    """Report that a selected backend dependency cannot be loaded (REQ-F02-160)."""


class NotGitRepositoryError(ValueError):
    """Report that a backend cannot open the supplied repository path (REQ-F02-190)."""


class RevisionResolutionError(ValueError):
    """Retain revision and shallow state without exposing diagnostics (REQ-F02-120)."""

    revision: str
    is_shallow: bool

    def __init__(self, *, revision: str, is_shallow: bool) -> None:
        self.revision = revision
        self.is_shallow = is_shallow
        super().__init__(revision)


@runtime_checkable
class GitBackend(Protocol):
    """Provide the backend-neutral conformance seam (REQ-F02-160/170)."""

    name: BackendName

    def resolve_commit(self, rev: str) -> str:
        """Resolve a revision to a full commit OID (REQ-F02-090/100/120)."""

    def merge_base(self, a: str, b: str) -> str:
        """Return the merge base without implicit invocation (REQ-F02-090/100)."""

    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]:
        """Return a deterministic tree-to-tree diff (REQ-F02-010 through REQ-F02-080)."""

    def repository_url(self) -> str | None:
        """Return the configured origin URL when present (REQ-F02-110/180)."""

    def is_dirty(self) -> bool:
        """Report tracked, staged, or untracked state (REQ-F02-030/040/130)."""
