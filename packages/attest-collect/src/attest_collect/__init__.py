"""Git and provenance-signal collection adapters for attest."""

from attest_collect.authorship import (
    AuthorshipCollection,
    AuthorshipDiagnosticCode,
    AuthorshipWarning,
    ClaimCollector,
    ClaimCollectorResult,
    CollectContext,
    KnownAgentPattern,
    collect_authorship,
    standard_collectors,
)
from attest_collect.changeset import (
    ChangeSetCollection,
    CollectionDiagnostics,
    CollectionWarning,
    collect_changeset,
)
from attest_collect.errors import CollectError
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.gitnotes import GitNoteCollector
from attest_collect.protocols import BackendName, BackendOverride, GitBackend
from attest_collect.sidecar import SidecarCollector
from attest_collect.trailers import ManualClaimCollector, TrailerCollector

__all__ = [
    "AuthorshipCollection",
    "AuthorshipDiagnosticCode",
    "AuthorshipWarning",
    "BackendName",
    "BackendOverride",
    "ChangeSetCollection",
    "ClaimCollector",
    "ClaimCollectorResult",
    "CollectContext",
    "CollectError",
    "CollectionDiagnostics",
    "CollectionWarning",
    "GitBackend",
    "GitNoteCollector",
    "KnownAgentPattern",
    "ManualClaimCollector",
    "Pygit2Backend",
    "SidecarCollector",
    "SubprocessBackend",
    "TrailerCollector",
    "collect_authorship",
    "collect_changeset",
    "standard_collectors",
]
