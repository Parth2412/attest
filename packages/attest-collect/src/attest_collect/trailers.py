"""Git trailer and manual claim collection governed by BRD-F03."""

from __future__ import annotations

import fnmatch
import hashlib
from collections.abc import Sequence
from typing import Final

from attest_collect._git_signals import GitSignalReader
from attest_collect.authorship import (
    AuthorshipWarning,
    ClaimCollectorResult,
    CollectContext,
    authorship_warning,
    generate_uuid7,
)
from attest_core import (
    AgentRef,
    AuthorshipClaim,
    ClaimScope,
    ClaimSource,
    ClaimSourceKind,
    ModelRef,
)

_ASCII_WHITESPACE: Final[str] = " \t\r\n\f\v"
_CLAIM_KEYS: Final[frozenset[str]] = frozenset(
    {
        "agent",
        "claim-id",
        "agent-version",
        "model",
        "session",
        "prompt-digest",
        "paths",
        "claimed-at",
    }
)
_X_ATTEST_CLAIM: Final[bytes] = b"x-attest-claim"
_CO_AUTHORED_BY: Final[bytes] = b"co-authored-by"


def _claim_from_payload(
    payload: str,
    *,
    kind: ClaimSourceKind,
    reference: str,
    digest: str,
) -> AuthorshipClaim:
    segments = payload.split(";")
    if not segments:
        raise ValueError
    values: dict[str, str] = {}
    for raw_segment in segments:
        segment = raw_segment.strip(_ASCII_WHITESPACE)
        if not segment:
            raise ValueError
        key, separator, value = segment.partition("=")
        if not separator or key not in _CLAIM_KEYS or key in values or not value:
            raise ValueError
        values[key] = value
    if "agent" not in values:
        raise ValueError

    agent = AgentRef(name=values["agent"], version=values.get("agent-version"))
    model: ModelRef | None = None
    if model_value := values.get("model"):
        if model_value.count("/") != 1:
            raise ValueError
        provider, name = model_value.split("/")
        if not provider or not name:
            raise ValueError
        model = ModelRef(provider=provider, name=name)
    scope: ClaimScope | None = None
    if path_value := values.get("paths"):
        paths = tuple(path_value.split(","))
        if any(not path for path in paths):
            raise ValueError
        scope = ClaimScope(paths=paths)

    claim_id = values.get("claim-id")
    if claim_id is None:
        claim_id = generate_uuid7()
    return AuthorshipClaim.model_validate(
        {
            "claim_id": claim_id,
            "agent": agent,
            "model": model,
            "session_id": values.get("session"),
            "prompt_digest": values.get("prompt-digest"),
            "scope": scope,
            "source": ClaimSource(kind=kind, reference=reference, digest=digest),
            "claimed_at": values.get("claimed-at"),
        }
    )


def _matched_agent(value: str, ctx: CollectContext) -> AgentRef | None:
    for known in ctx.known_agent_patterns:
        if fnmatch.fnmatchcase(value, known.pattern):
            return known.agent
    return None


class ManualClaimCollector:
    """Collect repeated manual claim values in CLI occurrence order (REQ-F03-020)."""

    kind = ClaimSourceKind.MANUAL

    def __init__(self, values: Sequence[str]) -> None:
        self._values = tuple(values)

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        _ = ctx
        claims: list[AuthorshipClaim] = []
        warnings: list[AuthorshipWarning] = []
        for occurrence, value in enumerate(self._values, start=1):
            reference = f"cli:--claim:{occurrence}"
            try:
                raw = value.encode("utf-8")
                claim = _claim_from_payload(
                    value,
                    kind=self.kind,
                    reference=reference,
                    digest=hashlib.sha256(raw).hexdigest(),
                )
            except (UnicodeError, ValueError):
                warnings.append(authorship_warning("ERR-COLLECT-117", reference))
            else:
                claims.append(claim)
        return ClaimCollectorResult(claims=tuple(claims), warnings=tuple(warnings))


class TrailerCollector:
    """Collect claim and configured agent co-author trailers (REQ-F03-020/080)."""

    kind = ClaimSourceKind.TRAILER

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        claims: list[AuthorshipClaim] = []
        warnings: list[AuthorshipWarning] = []
        try:
            reader = GitSignalReader(ctx.repo_path)
            commits = reader.commit_oids(ctx.base_commit, ctx.head_commit)
        except Exception:
            warning = authorship_warning("ERR-COLLECT-113", "commit-range")
            return ClaimCollectorResult(claims=(), warnings=(warning,))

        for commit in commits:
            try:
                message = reader.raw_commit_message(commit)
                trailers = reader.parsed_trailers(message)
            except Exception:
                warnings.append(authorship_warning("ERR-COLLECT-113", f"commit:{commit}"))
                continue
            digest = hashlib.sha256(message).hexdigest()
            occurrences = {_X_ATTEST_CLAIM: 0, _CO_AUTHORED_BY: 0}
            for raw_token, raw_value in trailers:
                try:
                    token = raw_token.lower()
                except AttributeError:
                    continue
                if token not in occurrences:
                    continue
                occurrences[token] += 1
                reference = f"commit:{commit}:{token.decode('ascii')}:{occurrences[token]}"
                try:
                    value = raw_value.decode("utf-8")
                    if token == _X_ATTEST_CLAIM:
                        claim = _claim_from_payload(
                            value,
                            kind=self.kind,
                            reference=reference,
                            digest=digest,
                        )
                    else:
                        agent = _matched_agent(value, ctx)
                        if agent is None:
                            continue
                        claim = AuthorshipClaim(
                            claim_id=generate_uuid7(),
                            agent=agent,
                            source=ClaimSource(
                                kind=self.kind,
                                reference=reference,
                                digest=digest,
                            ),
                        )
                except (UnicodeError, ValueError):
                    warnings.append(authorship_warning("ERR-COLLECT-113", reference))
                else:
                    claims.append(claim)
        return ClaimCollectorResult(claims=tuple(claims), warnings=tuple(warnings))
