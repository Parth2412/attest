"""Public F-03 orchestration and mode-derivation acceptance tests."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest

from attest_collect import (
    AuthorshipWarning,
    ClaimCollectorResult,
    CollectContext,
    CollectError,
    KnownAgentPattern,
    ManualClaimCollector,
    SidecarCollector,
    TrailerCollector,
    collect_authorship,
    standard_collectors,
)
from attest_core import (
    AgentRef,
    AuthorshipClaim,
    ClaimScope,
    ClaimSource,
    ClaimSourceKind,
)

CLAIM_A = "01890f5e-7b8a-7cc3-98c4-dc0c0c07398f"
CLAIM_B = "01890f5e-7b8a-7cc3-a8c4-dc0c0c07398f"
CLAIM_C = "01890f5e-7b8a-7cc3-b8c4-dc0c0c07398f"
SOURCE_DIGEST = "a" * 64
PRIVATE_COLLECTOR_FAILURE = "private collector failure"


@pytest.fixture(autouse=True)
def _isolate_shared_repository(single_add_repo: Any) -> Iterator[None]:
    marker = single_add_repo.path / ".attest"
    if marker.exists():
        shutil.rmtree(marker)
    yield
    if marker.exists():
        shutil.rmtree(marker)


def _context(
    case: Any,
    *,
    notes_ref: str = "refs/notes/ai",
    known_agent_patterns: tuple[KnownAgentPattern, ...] = (),
) -> CollectContext:
    return CollectContext(
        repo_path=case.path,
        base_commit=case.base,
        head_commit=case.head,
        notes_ref=notes_ref,
        known_agent_patterns=known_agent_patterns,
    )


def _claim(
    claim_id: str,
    *,
    kind: ClaimSourceKind = ClaimSourceKind.SIDECAR,
    paths: tuple[str, ...] | None = None,
    agent: str = "codex-cli",
) -> AuthorshipClaim:
    return AuthorshipClaim(
        claim_id=claim_id,
        agent=AgentRef(name=agent),
        scope=None if paths is None else ClaimScope(paths=paths),
        source=ClaimSource(
            kind=kind,
            reference=f"test:{claim_id}",
            digest=SOURCE_DIGEST,
        ),
    )


@dataclass(frozen=True, slots=True)
class StaticCollector:
    claims: tuple[AuthorshipClaim, ...]
    warnings: tuple[AuthorshipWarning, ...] = ()
    kind: ClaimSourceKind = ClaimSourceKind.SIDECAR

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        return ClaimCollectorResult(claims=self.claims, warnings=self.warnings)


class ExplodingCollector:
    kind = ClaimSourceKind.GIT_NOTE

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        raise RuntimeError(PRIVATE_COLLECTOR_FAILURE)


def test_standard_collectors_use_normative_duplicate_precedence() -> None:
    collectors = standard_collectors(("agent=manual-tool",))

    assert [collector.kind for collector in collectors] == [
        ClaimSourceKind.SIDECAR,
        ClaimSourceKind.TRAILER,
        ClaimSourceKind.GIT_NOTE,
        ClaimSourceKind.MANUAL,
    ]


def _write_sidecar(
    repository: Path,
    claim_id: str,
    *,
    agent: str = "codex-cli",
    paths: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schemaVersion": "0.1.0",
        "claimId": claim_id,
        "agent": {"name": agent},
    }
    if paths is not None:
        payload["scope"] = {"paths": paths}
    if extra is not None:
        payload.update(extra)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    directory = repository / ".attest" / "claims.d"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{claim_id}.json").write_bytes(raw)
    return raw


@pytest.mark.ac("AC-F03-010")
def test_malformed_sidecar_does_not_abort_valid_siblings(single_add_repo: Any) -> None:
    _write_sidecar(single_add_repo.path, CLAIM_A)
    _write_sidecar(single_add_repo.path, CLAIM_B, agent="some-future-tool")
    (single_add_repo.path / ".attest" / "claims.d" / "malformed.json").write_text("{")

    result = collect_authorship(
        _context(single_add_repo),
        (SidecarCollector(),),
        ("a.txt",),
    )

    assert [claim.claim_id for claim in result.authorship.claims] == [CLAIM_A, CLAIM_B]
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-111"]
    for warning in result.warnings:
        assert warning.message
        assert warning.remediation
        assert warning.reference


@pytest.mark.ac("AC-F03-030")
def test_duplicate_sidecar_and_trailer_retains_standard_first_source(
    duplicate_claim_repo: Any,
) -> None:
    _write_sidecar(duplicate_claim_repo.path, CLAIM_A, agent="sidecar-agent")

    result = collect_authorship(
        _context(duplicate_claim_repo),
        standard_collectors(),
        ("a.txt",),
    )

    assert len(result.authorship.claims) == 1
    assert result.authorship.claims[0].agent.name == "sidecar-agent"
    assert result.authorship.claims[0].source.kind == ClaimSourceKind.SIDECAR
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-114"]
    assert result.warnings[0].reference.endswith("x-attest-claim:1")


@pytest.mark.ac("AC-F03-040")
def test_prompt_property_is_omitted_without_leaking_its_value(single_add_repo: Any) -> None:
    _write_sidecar(single_add_repo.path, CLAIM_A, extra={"prompt": "secret"})

    result = collect_authorship(
        _context(single_add_repo),
        (SidecarCollector(),),
        ("a.txt",),
    )
    rendered = json.dumps(
        {
            "authorship": result.authorship.model_dump(),
            "warnings": [asdict(warning) for warning in result.warnings],
        },
        default=str,
    )

    assert [warning.code for warning in result.warnings] == ["WARN-COLLECT-003"]
    assert "secret" not in rendered
    assert "prompt" not in result.authorship.claims[0].model_dump()


@pytest.mark.ac("AC-F03-050")
@pytest.mark.parametrize(
    ("claims", "changed_paths", "marker", "expected"),
    [
        ((_claim(CLAIM_A),), ("a.txt",), False, "ai-authored"),
        ((_claim(CLAIM_A, paths=("a.txt",)),), ("a.txt", "b.txt"), False, "ai-assisted"),
        ((_claim(CLAIM_A, kind=ClaimSourceKind.MANUAL),), ("a.txt",), False, "unknown"),
        ((_claim(CLAIM_A),), (), False, "unknown"),
        ((), ("a.txt",), True, "human-authored"),
        ((), ("a.txt",), False, "unknown"),
    ],
)
def test_mode_is_derived_only_from_normative_coverage_rows(
    single_add_repo: Any,
    claims: tuple[AuthorshipClaim, ...],
    changed_paths: tuple[str, ...],
    marker: bool,
    expected: str,
) -> None:
    marker_path = single_add_repo.path / ".attest"
    if marker:
        marker_path.mkdir(exist_ok=True)
    elif marker_path.exists() and not (marker_path / "claims.d").exists():
        marker_path.rmdir()

    result = collect_authorship(
        _context(single_add_repo),
        (StaticCollector(claims),),
        changed_paths,
    )

    assert result.authorship.mode == expected


@pytest.mark.ac("AC-F03-060")
def test_mode_compares_decoded_raw_paths_and_rejects_noncanonical_input(
    single_add_repo: Any,
) -> None:
    claim = _claim(CLAIM_A, paths=("caf%C3%A9.py", "bad-%FF.py"))
    result = collect_authorship(
        _context(single_add_repo),
        (StaticCollector((claim,)),),
        ("bad-%FF.py", "caf%C3%A9.py"),
    )
    assert result.authorship.mode == "ai-authored"

    with pytest.raises(CollectError) as captured:
        collect_authorship(
            _context(single_add_repo),
            (StaticCollector((claim,)),),
            ("café.py",),
        )
    assert captured.value.code == "ERR-COLLECT-115"


@pytest.mark.ac("AC-F03-070")
def test_outside_scope_path_is_retained_and_warned(single_add_repo: Any) -> None:
    claim = _claim(CLAIM_A, paths=("a.txt", "removed.py"))

    result = collect_authorship(
        _context(single_add_repo),
        (StaticCollector((claim,)),),
        ("a.txt",),
    )

    assert result.authorship.claims[0].scope == claim.scope
    assert [warning.code for warning in result.warnings] == ["WARN-COLLECT-004"]
    assert result.warnings[0].reference == claim.source.reference


@pytest.mark.ac("AC-F03-080")
def test_coauthor_requires_case_sensitive_whole_glob_and_first_match_wins(
    trailer_repo: Any,
) -> None:
    context = _context(
        trailer_repo,
        known_agent_patterns=(
            KnownAgentPattern("Tool * <bot@example.test>", AgentRef(name="first-agent")),
            KnownAgentPattern("* <bot@example.test>", AgentRef(name="second-agent")),
            KnownAgentPattern("tool *", AgentRef(name="wrong-case")),
        ),
    )

    result = collect_authorship(context, (TrailerCollector(),), ("a.txt",))

    assert [claim.agent.name for claim in result.authorship.claims] == ["first-agent"]
    assert result.authorship.claims[0].source.reference.endswith("co-authored-by:2")


@pytest.mark.ac("AC-F03-090")
def test_claimed_at_is_preserved_and_never_controls_order(single_add_repo: Any) -> None:
    values = (
        f"agent=codex-cli; claim-id={CLAIM_C}; claimed-at=2099-01-01T00:00:00Z",
        f"agent=codex-cli; claim-id={CLAIM_A}; claimed-at=2000-01-01T00:00:00Z",
    )
    result = collect_authorship(
        _context(single_add_repo),
        (ManualClaimCollector(values),),
        ("a.txt",),
    )

    assert [claim.claim_id for claim in result.authorship.claims] == [CLAIM_A, CLAIM_C]
    assert [claim.model_dump()["claimedAt"] for claim in result.authorship.claims] == [
        "2000-01-01T00:00:00Z",
        "2099-01-01T00:00:00Z",
    ]


@pytest.mark.ac("AC-F03-100")
def test_absence_of_claims_is_explicit(single_add_repo: Any) -> None:
    result = collect_authorship(_context(single_add_repo), (), ("a.txt",))

    assert result.authorship.claims_present is False
    assert result.authorship.model_dump()["claimsPresent"] is False
    assert result.authorship.claims == ()


@pytest.mark.ac("AC-F03-110")
def test_collector_failure_warns_but_total_repository_failure_is_fatal(
    single_add_repo: Any, tmp_path: Path
) -> None:
    _write_sidecar(single_add_repo.path, CLAIM_A)
    degraded = collect_authorship(
        _context(single_add_repo),
        (ExplodingCollector(), SidecarCollector()),
        ("a.txt",),
    )
    assert [claim.claim_id for claim in degraded.authorship.claims] == [CLAIM_A]
    assert [warning.code for warning in degraded.warnings] == ["ERR-COLLECT-118"]
    assert "private collector failure" not in degraded.warnings[0].message

    with pytest.raises(CollectError) as captured:
        collect_authorship(
            CollectContext(tmp_path, "1" * 40, "2" * 40),
            (SidecarCollector(),),
            (),
        )
    assert captured.value.code == "ERR-COLLECT-102"


@pytest.mark.ac("AC-F03-120")
def test_unknown_agent_name_is_preserved(single_add_repo: Any) -> None:
    _write_sidecar(single_add_repo.path, CLAIM_A, agent="some-future-tool")

    result = collect_authorship(
        _context(single_add_repo),
        (SidecarCollector(),),
        ("a.txt",),
    )

    assert result.authorship.claims[0].agent.name == "some-future-tool"


@pytest.mark.ac("AC-F03-130")
def test_sidecar_collection_is_byte_preserving(single_add_repo: Any) -> None:
    raw_a = _write_sidecar(single_add_repo.path, CLAIM_A)
    raw_b = _write_sidecar(single_add_repo.path, CLAIM_B)
    directory = single_add_repo.path / ".attest" / "claims.d"
    before = {path.name: path.read_bytes() for path in directory.iterdir()}

    collect_authorship(_context(single_add_repo), (SidecarCollector(),), ("a.txt",))

    after = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert before == after == {f"{CLAIM_A}.json": raw_a, f"{CLAIM_B}.json": raw_b}


@pytest.mark.ac("AC-F03-140")
def test_claim_array_is_identical_for_shuffled_collector_order(single_add_repo: Any) -> None:
    claims = (_claim(CLAIM_C), _claim(CLAIM_A), _claim(CLAIM_B))
    forward = collect_authorship(
        _context(single_add_repo),
        (StaticCollector(claims),),
        ("a.txt",),
    )
    reverse = collect_authorship(
        _context(single_add_repo),
        (StaticCollector(tuple(reversed(claims))),),
        ("a.txt",),
    )

    assert forward.authorship == reverse.authorship
    assert [claim.claim_id for claim in forward.authorship.claims] == [CLAIM_A, CLAIM_B, CLAIM_C]
