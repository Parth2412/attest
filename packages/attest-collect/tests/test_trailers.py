"""Trailer and manual claim grammar tests for F-03."""

from __future__ import annotations

import hashlib
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from attest_collect import CollectContext, ManualClaimCollector, TrailerCollector

CLAIM_A = "01890f5e-7b8a-7cc3-98c4-dc0c0c07398f"
CLAIM_B = "01890f5e-7b8a-7cc3-a8c4-dc0c0c07398f"


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def _repository(
    tmp_path: Path, messages: tuple[bytes, ...]
) -> tuple[CollectContext, tuple[str, ...]]:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "attest tests")
    _git(repository, "config", "user.email", "attest@example.test")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "base")
    base = _git(repository, "rev-parse", "HEAD").decode().strip()
    commits: list[str] = []
    for index, message in enumerate(messages):
        (repository / f"file-{index}.txt").write_text(str(index), encoding="utf-8")
        _git(repository, "add", "--all")
        _git(repository, "commit", "--quiet", "--cleanup=verbatim", "-F", "-", input_bytes=message)
        commits.append(_git(repository, "rev-parse", "HEAD").decode().strip())
    return CollectContext(repository, base, commits[-1]), tuple(commits)


def _raw_message(repository: Path, commit: str) -> bytes:
    content = _git(repository, "cat-file", "commit", commit)
    return content.split(b"\n\n", 1)[1]


@pytest.mark.ac("AC-F03-020")
def test_manual_claim_maps_every_supported_key_and_exact_digest() -> None:
    value = (
        f"paths=src/a.py,bad-%FF.py; model=openai/gpt-5; agent=codex-cli; "
        f"claim-id={CLAIM_A}; agent-version=1.2.3; session=session-1; "
        f"prompt-digest={'a' * 64}; claimed-at=2099-01-01T00:00:00Z"
    )
    context = CollectContext(Path(), "1" * 40, "2" * 40)

    result = ManualClaimCollector((value,)).collect(context)

    assert result.warnings == ()
    assert result.claims[0].model_dump() == {
        "claimId": CLAIM_A,
        "agent": {"name": "codex-cli", "version": "1.2.3"},
        "model": {"provider": "openai", "name": "gpt-5"},
        "sessionId": "session-1",
        "promptDigest": "a" * 64,
        "scope": {"paths": ["src/a.py", "bad-%FF.py"]},
        "source": {
            "kind": "manual",
            "reference": "cli:--claim:1",
            "digest": hashlib.sha256(value.encode()).hexdigest(),
        },
        "claimedAt": "2099-01-01T00:00:00Z",
    }


@pytest.mark.parametrize(
    "value",
    [
        "",
        "model=openai/gpt-5",
        "Agent=codex-cli",
        "agent=",
        "agent=codex-cli;; model=openai/gpt-5",
        "agent=codex-cli; agent=other",
        "agent=codex-cli; unknown=value",
        "agent=codex-cli; model=/gpt-5",
        "agent=codex-cli; model=openai/gpt/5",
        "agent=codex-cli; paths=",
        "agent=codex-cli; paths=café.py",
        "agent=codex-cli; prompt-digest=ABC",
        "agent=codex-cli; claimed-at=tomorrow",
        "agent=codex-cli; claim-id=not-an-id",
    ],
)
def test_malformed_manual_value_isolated_with_stable_warning(value: str) -> None:
    context = CollectContext(Path(), "1" * 40, "2" * 40)

    result = ManualClaimCollector((value,)).collect(context)

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-117"]
    assert result.warnings[0].reference == "cli:--claim:1"
    if value:
        assert value not in result.warnings[0].message


def test_missing_claim_id_generates_rfc9562_uuidv7() -> None:
    context = CollectContext(Path(), "1" * 40, "2" * 40)

    result = ManualClaimCollector(("agent=some-future-tool",)).collect(context)

    parsed = uuid.UUID(result.claims[0].claim_id)
    assert parsed.version == 7
    assert parsed.variant == uuid.RFC_4122
    assert result.claims[0].claimed_at is None


@pytest.mark.ac("AC-F03-020")
def test_trailers_use_sorted_commit_oids_raw_message_digest_and_exact_references(
    tmp_path: Path,
) -> None:
    context, commits = _repository(
        tmp_path,
        (
            (
                f"first\n\nX-Attest-Claim: agent=codex-cli; claim-id={CLAIM_A}; paths=file-0.txt\n"
            ).encode(),
            (
                "second\n\n"
                "Co-Authored-By: Human <human@example.test>\n"
                f"x-attest-claim: agent=claude-code; claim-id={CLAIM_B}; paths=file-1.txt\n"
            ).encode(),
        ),
    )

    result = TrailerCollector().collect(context)

    assert result.warnings == ()
    expected_commits = sorted(commits)
    assert [claim.source.reference for claim in result.claims] == [
        f"commit:{expected_commits[0]}:x-attest-claim:1",
        f"commit:{expected_commits[1]}:x-attest-claim:1",
    ]
    by_commit = {
        claim.source.reference.split(":", 2)[1]: claim.source.digest for claim in result.claims
    }
    assert by_commit == {
        commit: hashlib.sha256(_raw_message(context.repo_path, commit)).hexdigest()
        for commit in commits
    }


def test_valid_trailer_survives_malformed_sibling(tmp_path: Path) -> None:
    context, _ = _repository(
        tmp_path,
        (
            (
                "change\n\n"
                "X-Attest-Claim: model=openai/gpt-5\n"
                f"X-Attest-Claim: agent=codex-cli; claim-id={CLAIM_A}\n"
            ).encode(),
        ),
    )

    result = TrailerCollector().collect(context)

    assert [claim.claim_id for claim in result.claims] == [CLAIM_A]
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-113"]
    assert result.warnings[0].reference.endswith("x-attest-claim:1")


def test_unmatched_coauthor_is_silent(trailer_repo: Any) -> None:
    context = CollectContext(trailer_repo.path, trailer_repo.base, trailer_repo.head)

    result = TrailerCollector().collect(context)

    assert result == type(result)(claims=(), warnings=())
