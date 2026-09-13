"""Acceptance tests for independent read-only repository recomputation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from attest_sign import RepositoryConstraint
from attest_sign import repository as module


def _git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(path: Path, message: str) -> str:
    _git(path, "add", ".")
    _git(
        path,
        "-c",
        "user.name=Verifier Test",
        "-c",
        "user.email=verifier@example.invalid",
        "commit",
        "-m",
        message,
    )
    return _git(path, "rev-parse", "HEAD")


@pytest.mark.ac("AC-F08-110")
def test_recomputation_uses_committed_revisions_and_ignores_working_tree(tmp_path: Path) -> None:
    """REQ-F08-110: only the caller-selected committed ChangeSet affects CSD-1."""
    _git(tmp_path, "init", "-q")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    tracked.write_text("signed\n", encoding="utf-8")
    signed_head = _commit(tmp_path, "signed")
    constraint = RepositoryConstraint(tmp_path, base, signed_head)

    signed_digest = module.recompute_changeset_digest(constraint)
    tracked.write_text("uncommitted\n", encoding="utf-8")
    dirty_digest = module.recompute_changeset_digest(constraint)
    tracked.write_text("different committed content\n", encoding="utf-8")
    different_head = _commit(tmp_path, "different")
    different_digest = module.recompute_changeset_digest(
        RepositoryConstraint(tmp_path, base, different_head)
    )

    assert signed_digest == dirty_digest
    assert different_digest != signed_digest


@pytest.mark.ac("AC-F08-110")
def test_every_git_call_is_bounded_and_hardened(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """REQ-F08-110: Git execution disables ambient mutation and has a deadline."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    outputs = iter(
        [
            b".git\n",
            (b"a" * 40) + b"\n",
            (b"b" * 40) + b"\n",
            b"",
        ]
    )

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, next(outputs), b"")

    monkeypatch.setattr("attest_sign.repository._shutil.which", lambda executable: "/usr/bin/git")
    monkeypatch.setattr("attest_sign.repository._subprocess.run", run)
    monkeypatch.setenv("GIT_DIR", "/attacker/repository")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "/attacker/diff")

    module.recompute_changeset_digest(RepositoryConstraint(tmp_path, "base", "head"))

    assert len(calls) == 4
    for command, kwargs in calls:
        assert command[0] == "/usr/bin/git"
        assert "--no-replace-objects" in command
        assert "core.fsmonitor=false" in command
        assert f"core.hooksPath={os.devnull}" in command
        assert kwargs["timeout"] == module.GIT_TIMEOUT_SECONDS
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert environment["GIT_OPTIONAL_LOCKS"] == "0"
        assert "GIT_DIR" not in environment
        assert "GIT_EXTERNAL_DIFF" not in environment
    diff_command = calls[-1][0]
    assert "--no-renames" in diff_command
    assert "--no-ext-diff" in diff_command
    assert "--no-textconv" in diff_command


@pytest.mark.ac("AC-F08-110")
@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("git", 30), OSError("private")])
def test_git_execution_failures_are_private_repository_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Exception,
) -> None:
    """REQ-F08-110: execution failures cannot escape the verifier boundary."""
    monkeypatch.setattr("attest_sign.repository._shutil.which", lambda executable: "/usr/bin/git")

    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del command, kwargs
        raise failure

    monkeypatch.setattr("attest_sign.repository._subprocess.run", fail)

    with pytest.raises(module.RepositoryVerificationError):
        module.recompute_changeset_digest(RepositoryConstraint(tmp_path, "base", "head"))
