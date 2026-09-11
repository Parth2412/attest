"""Git and provenance-signal collection adapters for attest."""

from attest_collect.changeset import (
    ChangeSetCollection,
    CollectionDiagnostics,
    CollectionWarning,
    collect_changeset,
)
from attest_collect.errors import CollectError
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.protocols import BackendName, BackendOverride, GitBackend

__all__ = [
    "BackendName",
    "BackendOverride",
    "ChangeSetCollection",
    "CollectError",
    "CollectionDiagnostics",
    "CollectionWarning",
    "GitBackend",
    "Pygit2Backend",
    "SubprocessBackend",
    "collect_changeset",
]
