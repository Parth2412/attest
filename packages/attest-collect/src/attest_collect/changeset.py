"""Public ChangeSet collection operation governed by BRD-F02."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from urllib.parse import SplitResult, urlsplit

from attest_collect.errors import CollectError, collect_error
from attest_collect.git_pygit2 import Pygit2Backend
from attest_collect.git_subprocess import SubprocessBackend
from attest_collect.protocols import (
    BackendName,
    BackendOverride,
    BackendUnavailableError,
    GitBackend,
    NotGitRepositoryError,
    RevisionResolutionError,
)
from attest_core import (
    ChangeSetInfo,
    ChangeSetRecord,
    ChangeSetStats,
    ChangeType,
    build_changeset_record,
    compute_changeset_digest,
)

WarningCode = Literal["WARN-COLLECT-001", "WARN-COLLECT-002"]

_FULL_OID: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")
_HOST: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9.-]+")
_SCP_URL: Final[re.Pattern[str]] = re.compile(
    r"(?:(?P<user>[^@/:]+)@)?(?P<host>[A-Za-z0-9.-]+):(?P<path>[^\s]+)"
)
_URL_SCHEMES: Final[frozenset[str]] = frozenset({"git", "http", "https", "ssh"})
_PATH_LIMIT: Final[int] = 1000
_WARNING_DETAILS: Final[dict[WarningCode, tuple[str, str]]] = {
    "WARN-COLLECT-001": (
        "Working tree or index state was ignored during tree-to-tree collection",
        "Commit or stash changes if they were intended for collection",
    ),
    "WARN-COLLECT-002": (
        "The requested head differs from the checked-out HEAD",
        "Confirm that the requested head revision is intentional",
    ),
}


@dataclass(frozen=True, slots=True)
class CollectionWarning:
    """Represent one stable non-fatal F-02 diagnostic (REQ-F02-130)."""

    code: WarningCode
    message: str
    remediation: str


@dataclass(frozen=True, slots=True)
class CollectionDiagnostics:
    """Identify the backend that produced the collection (REQ-F02-160)."""

    backend: BackendName


@dataclass(frozen=True, slots=True)
class ChangeSetCollection:
    """Return the record, signed context, warnings, and diagnostics (REQ-F02-090/160)."""

    record: ChangeSetRecord
    info: ChangeSetInfo
    warnings: tuple[CollectionWarning, ...]
    diagnostics: CollectionDiagnostics


def _warning(code: WarningCode) -> CollectionWarning:
    message, remediation = _WARNING_DETAILS[code]
    return CollectionWarning(code=code, message=message, remediation=remediation)


def _instantiate_backend(
    backend_type: type[Pygit2Backend] | type[SubprocessBackend],
    repo_path: Path,
) -> GitBackend:
    try:
        return backend_type(repo_path)
    except NotGitRepositoryError as error:
        raise collect_error("ERR-COLLECT-102") from error


def _select_backend(
    repo_path: Path,
    requested: GitBackend | BackendOverride,
) -> GitBackend:
    if not isinstance(requested, str):
        if requested.name not in ("pygit2", "subprocess"):
            raise collect_error("ERR-COLLECT-104")
        return requested

    if requested not in ("auto", "pygit2", "subprocess"):
        raise collect_error("ERR-COLLECT-104")

    if requested in ("auto", "pygit2"):
        if Pygit2Backend.is_available():
            try:
                return _instantiate_backend(Pygit2Backend, repo_path)
            except BackendUnavailableError as error:
                if requested == "pygit2":
                    raise collect_error("ERR-COLLECT-104") from error
        elif requested == "pygit2":
            raise collect_error("ERR-COLLECT-104")

    if requested in ("auto", "subprocess"):
        if not SubprocessBackend.is_available():
            raise collect_error("ERR-COLLECT-104")
        try:
            return _instantiate_backend(SubprocessBackend, repo_path)
        except BackendUnavailableError as error:
            raise collect_error("ERR-COLLECT-104") from error

    raise collect_error("ERR-COLLECT-104")


def _resolve_revision(backend: GitBackend, revision: str, *, diff_base: bool) -> str:
    try:
        oid = backend.resolve_commit(revision)
    except RevisionResolutionError as error:
        if diff_base and error.is_shallow and _FULL_OID.fullmatch(revision) is not None:
            raise collect_error("ERR-COLLECT-101") from error
        raise collect_error("ERR-COLLECT-103") from error
    except Exception as error:
        raise collect_error("ERR-COLLECT-106") from error
    if _FULL_OID.fullmatch(oid) is None:
        raise collect_error("ERR-COLLECT-106")
    return oid


def _split_repository_url(value: str) -> tuple[str, str, int | None] | None:
    scp_match = _SCP_URL.fullmatch(value)
    if scp_match is not None and "://" not in value:
        return scp_match.group("host"), scp_match.group("path"), None

    try:
        parsed: SplitResult = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _URL_SCHEMES or parsed.query or parsed.fragment:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.hostname is None:
        return None
    return parsed.hostname, parsed.path, port


def _normalise_repository_url(value: str | None) -> str:
    if (
        value is None
        or not value
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise collect_error("ERR-COLLECT-105")
    split = _split_repository_url(value)
    if split is None:
        raise collect_error("ERR-COLLECT-105")
    host, path, port = split
    if _HOST.fullmatch(host) is None:
        raise collect_error("ERR-COLLECT-105")
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if path.endswith(".git"):
        raise collect_error("ERR-COLLECT-105")
    segments = path.split("/")
    if not path or any(
        not segment or any(character.isspace() for character in segment) for segment in segments
    ):
        raise collect_error("ERR-COLLECT-105")
    authority = host.lower() if port is None else f"{host.lower()}:{port}"
    return f"https://{authority}/{path}"


def _repository_identity(backend: GitBackend, explicit: str | None) -> str:
    if explicit is not None:
        return _normalise_repository_url(explicit)
    try:
        discovered = backend.repository_url()
    except Exception as error:
        raise collect_error("ERR-COLLECT-105") from error
    return _normalise_repository_url(discovered)


def _stats(record: ChangeSetRecord) -> ChangeSetStats:
    return ChangeSetStats(
        files_changed=len(record.entries),
        files_added=sum(entry.change_type is ChangeType.ADDED for entry in record.entries),
        files_modified=sum(entry.change_type is ChangeType.MODIFIED for entry in record.entries),
        files_deleted=sum(entry.change_type is ChangeType.DELETED for entry in record.entries),
    )


def _warnings(backend: GitBackend, head_commit: str) -> tuple[CollectionWarning, ...]:
    warnings: list[CollectionWarning] = []
    if backend.is_dirty():
        warnings.append(_warning("WARN-COLLECT-001"))
    if backend.resolve_commit("HEAD") != head_commit:
        warnings.append(_warning("WARN-COLLECT-002"))
    return tuple(warnings)


def collect_changeset(
    repo_path: Path,
    base_rev: str,
    head_rev: str,
    backend: GitBackend | BackendOverride = "auto",
    *,
    merge_base_rev: str | None = None,
    repository_url: str | None = None,
) -> ChangeSetCollection:
    """Collect a deterministic tree-to-tree ChangeSet (REQ-F02-090 through REQ-F02-190)."""
    try:
        selected = _select_backend(repo_path, backend)
        selected_base_revision = base_rev if merge_base_rev is None else merge_base_rev
        base_commit = _resolve_revision(selected, selected_base_revision, diff_base=True)
        head_commit = _resolve_revision(selected, head_rev, diff_base=False)
        repository = _repository_identity(selected, repository_url)
        entries = selected.diff_entries(base_commit, head_commit)
        record = build_changeset_record(entries)
        digest = compute_changeset_digest(record)
        paths = tuple(entry.path for entry in record.entries[:_PATH_LIMIT])
        truncated = True if len(record.entries) > _PATH_LIMIT else None
        info = ChangeSetInfo(
            repository=repository,
            algorithm=record.algorithm,
            base_commit=base_commit,
            head_commit=head_commit,
            merge_base=base_commit if merge_base_rev is not None else None,
            digest=digest,
            stats=_stats(record),
            paths=paths,
            paths_truncated=truncated,
        )
        warnings = _warnings(selected, head_commit)
    except CollectError:
        raise
    except Exception as error:
        raise collect_error("ERR-COLLECT-106") from error
    return ChangeSetCollection(
        record=record,
        info=info,
        warnings=warnings,
        diagnostics=CollectionDiagnostics(backend=selected.name),
    )
