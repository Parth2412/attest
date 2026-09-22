"""Pinned Git AI authorship/3.0.0 interoperability tests for F-03."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from attest_collect import CollectContext, GitNoteCollector

SESSION_KEY = "s_0123456789abcd"
TRACE_A = "t_0123456789abcd"
TRACE_B = "t_abcdef01234567"
HUMAN_KEY = "h_0123456789abcd"
LEGACY_KEY = "0123456789abcdef"


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def _repository(tmp_path: Path) -> CollectContext:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "attest tests")
    _git(repository, "config", "user.email", "attest@example.test")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "base")
    base = _git(repository, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    (repository / "a.py").write_text("value = 1\n", encoding="utf-8")
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "head")
    head = _git(repository, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    return CollectContext(repository, base, head)


def _attach_note(context: CollectContext, raw: bytes) -> None:
    note_oid = (
        _git(context.repo_path, "hash-object", "-w", "--stdin", input_bytes=raw)
        .stdout.decode("ascii")
        .strip()
    )
    _git(
        context.repo_path,
        "notes",
        f"--ref={context.notes_ref}",
        "add",
        "-C",
        note_oid,
        context.head_commit,
    )


def _metadata(context: CollectContext) -> dict[str, object]:
    return {
        "schema_version": "authorship/3.0.0",
        "git_ai_version": "1.4.5",
        "base_commit_sha": context.base_commit,
        "prompts": {
            LEGACY_KEY: {
                "agent_id": {"tool": "cursor", "id": "legacy-session", "model": "gpt-4"},
                "human_author": "Developer <dev@example.test>",
                "total_additions": 2,
                "total_deletions": 0,
                "accepted_lines": 2,
                "overriden_lines": 0,
            }
        },
        "humans": {HUMAN_KEY: {"author": "Developer <dev@example.test>"}},
        "sessions": {
            SESSION_KEY: {
                "agent_id": {
                    "tool": "codex",
                    "id": "session-1",
                    "model": "openai/gpt-5",
                },
                "human_author": "dev@example.test",
                "custom_attributes": {"team": "core"},
            },
            "s_aaaaaaaaaaaaaa": {
                "agent_id": {"tool": "unused", "id": "unused", "model": "vendor/model"},
                "human_author": None,
            },
        },
    }


def _note(context: CollectContext, metadata: dict[str, object] | None = None) -> bytes:
    payload = _metadata(context) if metadata is None else metadata
    attestation = (
        f"z.py\n  {SESSION_KEY}::{TRACE_A} 1-2\n"
        f"a.py\n  {SESSION_KEY}::{TRACE_B} 1\n"
        f"  {HUMAN_KEY} 2\n"
        f"legacy.py\n  {LEGACY_KEY} 1\n"
    )
    return (attestation + "---\n" + json.dumps(payload, indent=2)).encode()


@pytest.mark.ac("AC-F03-020")
def test_git_ai_mixed_note_maps_only_referenced_ai_records(tmp_path: Path) -> None:
    context = _repository(tmp_path)
    raw = _note(context)
    _attach_note(context, raw)

    result = GitNoteCollector().collect(context)

    assert result.warnings == ()
    assert [claim.source.reference for claim in result.claims] == [
        f"refs/notes/ai:{context.head_commit}:{LEGACY_KEY}",
        f"refs/notes/ai:{context.head_commit}:{SESSION_KEY}",
    ]
    legacy, session = result.claims
    assert legacy.agent.name == "cursor"
    assert legacy.session_id == "legacy-session"
    assert legacy.model is None
    assert legacy.scope is not None
    assert legacy.scope.paths == ("legacy.py",)
    assert session.agent.name == "codex"
    assert session.session_id == "session-1"
    assert session.model is not None
    assert session.model.model_dump() == {"provider": "openai", "name": "gpt-5"}
    assert session.scope is not None
    assert session.scope.paths == ("a.py", "z.py")
    assert all(claim.source.digest == hashlib.sha256(raw).hexdigest() for claim in result.claims)


@pytest.mark.ac("AC-F03-110")
def test_absent_note_ref_is_silent_but_invalid_ref_warns(tmp_path: Path) -> None:
    context = _repository(tmp_path)
    assert GitNoteCollector().collect(context).warnings == ()

    invalid = CollectContext(
        context.repo_path,
        context.base_commit,
        context.head_commit,
        notes_ref="refs/heads/main",
    )
    result = GitNoteCollector().collect(invalid)
    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-116"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-divider",
        "unsupported-version",
        "missing-session-record",
        "invalid-range",
        "forbidden-session-field",
        "missing-human-record",
        "invalid-prompt-record",
    ],
)
def test_malformed_or_unsupported_note_isolated_to_that_commit(
    tmp_path: Path, mutation: str
) -> None:
    context = _repository(tmp_path)
    metadata = _metadata(context)
    raw = _note(context, metadata)
    if mutation == "missing-divider":
        raw = raw.replace(b"---\n", b"")
    elif mutation == "unsupported-version":
        metadata["schema_version"] = "authorship/4.0.0"
        raw = _note(context, metadata)
    elif mutation == "missing-session-record":
        metadata["sessions"] = {}
        raw = _note(context, metadata)
    elif mutation == "invalid-range":
        raw = raw.replace(b" 1-2", b" 2-1")
    elif mutation == "forbidden-session-field":
        sessions = metadata["sessions"]
        assert isinstance(sessions, dict)
        session = sessions[SESSION_KEY]
        assert isinstance(session, dict)
        session["messages_url"] = "https://example.test"
        raw = _note(context, metadata)
    elif mutation == "missing-human-record":
        metadata["humans"] = {}
        raw = _note(context, metadata)
    else:
        prompts = metadata["prompts"]
        assert isinstance(prompts, dict)
        prompt = prompts[LEGACY_KEY]
        assert isinstance(prompt, dict)
        prompt.pop("accepted_lines")
        raw = _note(context, metadata)
    _attach_note(context, raw)

    result = GitNoteCollector().collect(context)

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-116"]
    assert result.warnings[0].reference == f"refs/notes/ai:{context.head_commit}"


def test_quoted_path_removes_only_outer_quotes(tmp_path: Path) -> None:
    context = _repository(tmp_path)
    metadata = _metadata(context)
    raw = _note(context, metadata).replace(b"z.py\n", b'"dir\\name with space.py"\n')
    _attach_note(context, raw)

    result = GitNoteCollector().collect(context)

    session = next(claim for claim in result.claims if claim.session_id == "session-1")
    assert session.scope is not None
    assert "dir%5Cname%20with%20space.py" in session.scope.paths


def test_note_blob_is_read_exactly_without_worktree_or_note_mutation(tmp_path: Path) -> None:
    context = _repository(tmp_path)
    raw = _note(context) + b"\n"
    _attach_note(context, raw)
    before = _git(
        context.repo_path,
        "notes",
        f"--ref={context.notes_ref}",
        "list",
        context.head_commit,
    ).stdout

    result = GitNoteCollector().collect(context)

    after = _git(
        context.repo_path,
        "notes",
        f"--ref={context.notes_ref}",
        "list",
        context.head_commit,
    ).stdout
    assert before == after
    assert all(claim.source.digest == hashlib.sha256(raw).hexdigest() for claim in result.claims)


def test_existing_notes_ref_is_silent_for_unnoted_commits(tmp_path: Path) -> None:
    noted_context = _repository(tmp_path)
    raw = _note(noted_context)
    _attach_note(noted_context, raw)
    (noted_context.repo_path / "later.py").write_text("value = 2\n", encoding="utf-8")
    _git(noted_context.repo_path, "add", "--all")
    _git(noted_context.repo_path, "commit", "--quiet", "-m", "later")
    head = _git(noted_context.repo_path, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    context = CollectContext(
        noted_context.repo_path,
        noted_context.base_commit,
        head,
        notes_ref=noted_context.notes_ref,
    )

    result = GitNoteCollector().collect(context)

    assert result.warnings == ()
    assert len(result.claims) == 2
    assert all(claim.source.digest == hashlib.sha256(raw).hexdigest() for claim in result.claims)
