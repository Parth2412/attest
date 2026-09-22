"""Authorship Claim orchestration governed by BRD-F03 and ADR-035."""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, cast, runtime_checkable

from attest_collect._git_signals import (
    GitSignalReader,
    GitSignalRepositoryError,
    GitSignalRevisionError,
)
from attest_collect.errors import (
    CollectDiagnosticCode,
    collect_diagnostic_details,
    collect_error,
)
from attest_core import (
    AgentRef,
    Authorship,
    AuthorshipClaim,
    AuthorshipMode,
    ClaimSourceKind,
    decode_git_path,
)

AuthorshipDiagnosticCode = Literal[
    "ERR-COLLECT-111",
    "ERR-COLLECT-112",
    "ERR-COLLECT-113",
    "ERR-COLLECT-114",
    "ERR-COLLECT-116",
    "ERR-COLLECT-117",
    "ERR-COLLECT-118",
    "WARN-COLLECT-003",
    "WARN-COLLECT-004",
]
WarningCode = Literal["WARN-COLLECT-003", "WARN-COLLECT-004"]

_ELIGIBLE_KINDS: Final[frozenset[ClaimSourceKind]] = frozenset(
    {
        ClaimSourceKind.TRAILER,
        ClaimSourceKind.SIDECAR,
        ClaimSourceKind.GIT_NOTE,
        ClaimSourceKind.FORGE_API,
    }
)
_WARNING_DETAILS: Final[dict[WarningCode, tuple[str, str]]] = {
    "WARN-COLLECT-003": (
        "A raw prompt sidecar property was omitted",
        "Supply only promptDigest when prompt correlation is required",
    ),
    "WARN-COLLECT-004": (
        "A claim scope contains paths outside the ChangeSet",
        "Confirm the claim scope and collected base and head commits",
    ),
}


@dataclass(frozen=True, slots=True)
class KnownAgentPattern:
    """Map a whole-value shell glob to an agent identity (REQ-F03-080)."""

    pattern: str
    agent: AgentRef


@dataclass(frozen=True, slots=True)
class CollectContext:
    """Carry immutable, resolved inputs for F-03 collection (REQ-F03-110)."""

    repo_path: Path
    base_commit: str
    head_commit: str
    notes_ref: str = "refs/notes/ai"
    known_agent_patterns: tuple[KnownAgentPattern, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorshipWarning:
    """Represent one stable, non-fatal collection diagnostic (REQ-F03-110)."""

    code: AuthorshipDiagnosticCode
    message: str
    remediation: str
    reference: str


@dataclass(frozen=True, slots=True)
class ClaimCollectorResult:
    """Return immutable claims and non-fatal warnings from one source (REQ-F03-110)."""

    claims: tuple[AuthorshipClaim, ...]
    warnings: tuple[AuthorshipWarning, ...]


@runtime_checkable
class ClaimCollector(Protocol):
    """Collect one class of Authorship Claim input (REQ-F03-110)."""

    @property
    def kind(self) -> ClaimSourceKind:
        """Identify the claim source represented by this collector."""

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        """Return this source's valid claims and structured warnings."""


@dataclass(frozen=True, slots=True)
class AuthorshipCollection:
    """Return normalized authorship plus all source degradations (REQ-F03-050)."""

    authorship: Authorship
    warnings: tuple[AuthorshipWarning, ...]


def authorship_warning(
    code: AuthorshipDiagnosticCode,
    reference: str,
) -> AuthorshipWarning:
    """Build one warning without copying untrusted source content into diagnostics."""
    if code in _WARNING_DETAILS:
        message, remediation = _WARNING_DETAILS[code]
    else:
        diagnostic_code = cast(CollectDiagnosticCode, code)
        message, remediation = collect_diagnostic_details(diagnostic_code)
    return AuthorshipWarning(
        code=code,
        message=message,
        remediation=remediation,
        reference=reference,
    )


def generate_uuid7() -> str:
    """Generate an RFC 9562 UUIDv7 using milliseconds and 74 random bits."""
    timestamp_ms = time.time_ns() // 1_000_000
    if not 0 <= timestamp_ms < 1 << 48:
        raise OverflowError
    value = bytearray(timestamp_ms.to_bytes(6, "big") + secrets.token_bytes(10))
    value[6] = 0x70 | (value[6] & 0x0F)
    value[8] = 0x80 | (value[8] & 0x3F)
    return str(uuid.UUID(bytes=bytes(value)))


def _validate_git_boundary(ctx: CollectContext) -> None:
    try:
        reader = GitSignalReader(ctx.repo_path)
    except GitSignalRepositoryError as error:
        raise collect_error("ERR-COLLECT-102") from error
    except Exception as error:
        raise collect_error("ERR-COLLECT-106") from error
    try:
        reader.validate_commit(ctx.base_commit)
        reader.validate_commit(ctx.head_commit)
    except GitSignalRevisionError as error:
        raise collect_error("ERR-COLLECT-103") from error
    except Exception as error:
        raise collect_error("ERR-COLLECT-106") from error


def _decode_changed_paths(changed_paths: Sequence[str]) -> frozenset[bytes]:
    try:
        return frozenset(decode_git_path(path) for path in changed_paths)
    except (TypeError, ValueError) as error:
        raise collect_error("ERR-COLLECT-115") from error


def _collector_reference(collector: object) -> str:
    kind = getattr(collector, "kind", None)
    if isinstance(kind, ClaimSourceKind):
        return f"collector:{kind.value}"
    return f"collector:{type(collector).__name__}"


def _validated_result(value: object) -> ClaimCollectorResult:
    if not isinstance(value, ClaimCollectorResult):
        raise TypeError
    if any(not isinstance(claim, AuthorshipClaim) for claim in value.claims):
        raise TypeError
    if any(not isinstance(warning, AuthorshipWarning) for warning in value.warnings):
        raise TypeError
    return value


def _collect_sources(
    ctx: CollectContext,
    collectors: Sequence[ClaimCollector],
) -> tuple[list[AuthorshipClaim], list[AuthorshipWarning]]:
    claims: list[AuthorshipClaim] = []
    warnings: list[AuthorshipWarning] = []
    for collector in collectors:
        try:
            result = _validated_result(collector.collect(ctx))
        except Exception:
            warnings.append(authorship_warning("ERR-COLLECT-118", _collector_reference(collector)))
            continue
        claims.extend(result.claims)
        warnings.extend(result.warnings)
    return claims, warnings


def _deduplicate(
    claims: Sequence[AuthorshipClaim],
) -> tuple[tuple[AuthorshipClaim, ...], tuple[AuthorshipWarning, ...]]:
    retained: dict[str, AuthorshipClaim] = {}
    warnings: list[AuthorshipWarning] = []
    for claim in claims:
        if claim.claim_id in retained:
            warnings.append(authorship_warning("ERR-COLLECT-114", claim.source.reference))
        else:
            retained[claim.claim_id] = claim
    return tuple(sorted(retained.values(), key=lambda claim: claim.claim_id)), tuple(warnings)


def _scope_bytes(claim: AuthorshipClaim) -> frozenset[bytes] | None:
    if claim.scope is None:
        return None
    return frozenset(decode_git_path(path) for path in claim.scope.paths)


def _mode(
    claims: Sequence[AuthorshipClaim],
    changed_paths: frozenset[bytes],
    marker_present: bool,
) -> AuthorshipMode:
    if not claims:
        return AuthorshipMode.HUMAN_AUTHORED if marker_present else AuthorshipMode.UNKNOWN
    if not changed_paths:
        return AuthorshipMode.UNKNOWN

    partial = False
    for claim in claims:
        if claim.source.kind not in _ELIGIBLE_KINDS:
            continue
        scope = _scope_bytes(claim)
        if scope is None or changed_paths <= scope:
            return AuthorshipMode.AI_AUTHORED
        if scope & changed_paths:
            partial = True
    return AuthorshipMode.AI_ASSISTED if partial else AuthorshipMode.UNKNOWN


def _outside_scope_warnings(
    claims: Sequence[AuthorshipClaim],
    changed_paths: frozenset[bytes],
) -> tuple[AuthorshipWarning, ...]:
    warnings: list[AuthorshipWarning] = []
    for claim in claims:
        scope = _scope_bytes(claim)
        if scope is not None and scope - changed_paths:
            warnings.append(authorship_warning("WARN-COLLECT-004", claim.source.reference))
    return tuple(warnings)


def collect_authorship(
    ctx: CollectContext,
    collectors: Sequence[ClaimCollector],
    changed_paths: Sequence[str],
) -> AuthorshipCollection:
    """Collect and normalize all F-03 claim sources (REQ-F03-010 through REQ-F03-140)."""
    _validate_git_boundary(ctx)
    decoded_paths = _decode_changed_paths(changed_paths)
    collected, warnings = _collect_sources(ctx, collectors)
    claims, duplicate_warnings = _deduplicate(collected)
    warnings.extend(duplicate_warnings)
    warnings.extend(_outside_scope_warnings(claims, decoded_paths))
    authorship = Authorship(
        mode=_mode(claims, decoded_paths, (ctx.repo_path / ".attest").is_dir()),
        claims_present=bool(claims),
        claims=claims,
    )
    return AuthorshipCollection(
        authorship=authorship,
        warnings=tuple(sorted(warnings, key=lambda warning: (warning.code, warning.reference))),
    )


def standard_collectors(manual_claims: Sequence[str] = ()) -> tuple[ClaimCollector, ...]:
    """Build the normative duplicate-precedence sequence (REQ-F03-030)."""
    from attest_collect.gitnotes import GitNoteCollector
    from attest_collect.sidecar import SidecarCollector
    from attest_collect.trailers import ManualClaimCollector, TrailerCollector

    return (
        SidecarCollector(),
        TrailerCollector(),
        GitNoteCollector(),
        ManualClaimCollector(manual_claims),
    )
