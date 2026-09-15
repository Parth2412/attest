"""Git and provenance-signal collection adapters for attest."""

from attest_collect._github_http import GitHubHttpClient, GitHubToken, load_github_token
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
from attest_collect.environment import collect_environment
from attest_collect.errors import CollectError
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.github import (
    ForgeAdapter,
    ForgeCheckData,
    ForgeReviewData,
    GitHubChangeSetContext,
    GitHubCollection,
    GitHubContextAdapter,
    GitHubForgeAdapter,
    GitHubPullRequestInput,
    GitHubReviewContext,
    GitHubWarning,
    ReviewContextKind,
    ReviewRequirementData,
    collect_github,
    collect_review,
    parse_github_pull_request_event,
    resolve_github_changeset_context,
)
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
    "ForgeAdapter",
    "ForgeCheckData",
    "ForgeReviewData",
    "GitBackend",
    "GitHubChangeSetContext",
    "GitHubCollection",
    "GitHubContextAdapter",
    "GitHubForgeAdapter",
    "GitHubHttpClient",
    "GitHubPullRequestInput",
    "GitHubReviewContext",
    "GitHubToken",
    "GitHubWarning",
    "GitNoteCollector",
    "KnownAgentPattern",
    "ManualClaimCollector",
    "Pygit2Backend",
    "ReviewContextKind",
    "ReviewRequirementData",
    "SidecarCollector",
    "SubprocessBackend",
    "TrailerCollector",
    "collect_authorship",
    "collect_changeset",
    "collect_environment",
    "collect_github",
    "collect_review",
    "load_github_token",
    "parse_github_pull_request_event",
    "resolve_github_changeset_context",
    "standard_collectors",
]
