"""Executable checks for the two F-03 harness-hook examples."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from attest_collect import CollectContext, SidecarCollector

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOOKS = REPOSITORY_ROOT / "examples" / "hooks"


def _run_hook(script: Path, repository: Path, payload: dict[str, object]) -> None:
    result = subprocess.run(
        ["sh", str(script)],
        cwd=repository,
        input=json.dumps(payload).encode(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == b""


def test_claude_and_codex_examples_emit_collectable_scoped_sidecars(
    single_add_repo: Any,
) -> None:
    target = single_add_repo.path / "src" / "edited.py"
    target.parent.mkdir()
    target.write_text("value = 1\n", encoding="utf-8")
    _run_hook(
        HOOKS / "claude-code" / "post-tool-use.sh",
        single_add_repo.path,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
            "cwd": str(single_add_repo.path),
            "session_id": "claude-session",
        },
    )
    _run_hook(
        HOOKS / "codex" / "post-tool-use.sh",
        single_add_repo.path,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Update File: src/edited.py\n@@\n"},
            "cwd": str(single_add_repo.path),
            "session_id": "codex-session",
            "model": "gpt-5",
        },
    )

    result = SidecarCollector().collect(
        CollectContext(single_add_repo.path, single_add_repo.base, single_add_repo.head)
    )
    assert result.warnings == ()
    assert {claim.agent.name for claim in result.claims} == {"claude-code", "codex-cli"}
    assert {claim.session_id for claim in result.claims} == {"claude-session", "codex-session"}
    assert all(claim.scope is not None for claim in result.claims)
    assert all(claim.scope.paths == ("src/edited.py",) for claim in result.claims if claim.scope)
    assert all(claim.model is None for claim in result.claims)


def test_hook_configs_match_only_verified_success_events() -> None:
    claude = json.loads((HOOKS / "claude-code" / "settings.example.json").read_text())
    codex = json.loads((HOOKS / "codex" / "hooks.example.json").read_text())

    assert claude["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write|NotebookEdit"
    assert codex["hooks"]["PostToolUse"][0]["matcher"] == "^apply_patch$"


def test_hook_fails_open_without_following_claim_directory_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(
        ["git", "-C", str(repository), "init", "--quiet"],
        capture_output=True,
        check=True,
    )
    target = repository / "edited.py"
    target.write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repository / ".attest").symlink_to(outside, target_is_directory=True)

    _run_hook(
        HOOKS / "codex" / "post-tool-use.sh",
        repository,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Update File: edited.py\n@@\n"},
            "cwd": str(repository),
            "session_id": "codex-session",
        },
    )

    assert list(outside.iterdir()) == []
