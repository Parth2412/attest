"""F-10 collect and build command integration tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from attest_cli.app import app
from attest_cli.artifacts import read_collection_artifact, read_statement
from attest_collect import GitHubChangeSetContext, GitHubCollection, GitHubPullRequestInput
from attest_core import ReviewState, Statement


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "remote", "add", "origin", "https://github.com/example/repo.git")
    source = repository / "example.txt"
    source.write_text("first\n", encoding="utf-8")
    _git(repository, "add", "example.txt")
    _git(repository, "commit", "-m", "first")
    base = _git(repository, "rev-parse", "HEAD")
    source.write_text("second\n", encoding="utf-8")
    _git(repository, "commit", "-am", "second")
    return repository, base, _git(repository, "rev-parse", "HEAD")


@pytest.mark.ac("AC-F10-110")
@pytest.mark.ac("AC-F10-180")
def test_local_collect_and_build_are_independently_consumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repository, base, head = _repository(tmp_path)
    collection_path = tmp_path / "collection.json"
    statement_path = tmp_path / "statement.json"
    runner = CliRunner()

    collected = runner.invoke(
        app,
        [
            "collect",
            "--repository",
            str(repository),
            "--output",
            str(collection_path),
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            "main",
            "--git-backend",
            "subprocess",
            "--json",
        ],
    )

    assert collected.exit_code == 0, collected.output
    report = json.loads(collected.stdout)
    assert report["command"] == "collect"
    assert report["data"]["baseCommit"] == base
    assert report["data"]["headCommit"] == head
    artifact = read_collection_artifact(collection_path)
    assert artifact.review.state is ReviewState.UNKNOWN
    assert tuple(entry.path for entry in artifact.change_set_record.entries) == ("example.txt",)

    built = runner.invoke(
        app,
        [
            "build",
            "--input",
            str(collection_path),
            "--output",
            str(statement_path),
            "--json",
        ],
    )

    assert built.exit_code == 0, built.output
    assert read_statement(statement_path).predicate.change_set.digest == artifact.change_set.digest
    assert statement_path.read_bytes().endswith(b"\n")


@pytest.mark.ac("AC-F10-180")
def test_conflicting_collect_context_fails_before_github_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    event = tmp_path / "event.json"
    event.write_bytes(b"{}")
    result = CliRunner().invoke(
        app,
        [
            "collect",
            "--output",
            str(tmp_path / "collection.json"),
            "--github-event",
            str(event),
            "--base",
            "1" * 40,
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-001"


@pytest.mark.ac("AC-F10-180")
@pytest.mark.parametrize("mode", ["event", "explicit"])
def test_github_inputs_and_resolved_context_reach_public_collectors_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    mode: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    repository, base, head = _repository(tmp_path)
    event = tmp_path / "event.json"
    event_bytes = b'{"exact":"event bytes"}'
    event.write_bytes(event_bytes)
    request = GitHubPullRequestInput(
        repository="example/repo",
        pr_number=7,
        base_revision=base,
        head_revision=head,
        target_branch="main",
    )
    context = GitHubChangeSetContext(
        repository="example/repo",
        pr_number=7,
        base_revision=base,
        head_revision=head,
        merge_base_revision=base,
        target_branch="main",
        change_author_ids=frozenset({"123"}),
    )
    seen: dict[str, object] = {}

    class Client:
        def __init__(self, token: object) -> None:
            seen["token"] = token

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def parse(payload: bytes) -> GitHubPullRequestInput:
        seen["event"] = payload
        return request

    def resolve(client: object, supplied: GitHubPullRequestInput) -> GitHubChangeSetContext:
        seen["request"] = supplied
        return context

    def github_collect(adapter: object, review_context: object) -> GitHubCollection:
        seen["review_context"] = review_context
        return GitHubCollection(
            review=statement.predicate.review,
            checks=statement.predicate.checks,
            warnings=(),
        )

    monkeypatch.setattr(
        "attest_collect.collect_environment", lambda _environment: statement.predicate.collection
    )
    monkeypatch.setattr("attest_collect.load_github_token", lambda _environment: object())
    monkeypatch.setattr("attest_collect.GitHubHttpClient", Client)
    monkeypatch.setattr("attest_collect.parse_github_pull_request_event", parse)
    monkeypatch.setattr("attest_collect.resolve_github_changeset_context", resolve)
    monkeypatch.setattr("attest_collect.collect_github", github_collect)
    output = tmp_path / "github-collection.json"
    context_arguments = (
        ["--github-event", str(event)]
        if mode == "event"
        else [
            "--github-repository",
            "example/repo",
            "--pr",
            "7",
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            "main",
        ]
    )
    result = CliRunner().invoke(
        app,
        [
            "collect",
            "--repository",
            str(repository),
            "--output",
            str(output),
            *context_arguments,
            "--git-backend",
            "subprocess",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    if mode == "event":
        assert seen["event"] == event_bytes
    else:
        assert "event" not in seen
    assert seen["request"] == request
    artifact = read_collection_artifact(output)
    assert artifact.context.base_commit == context.merge_base_revision
    assert artifact.context.head_commit == context.head_revision
    assert artifact.context.target_branch == context.target_branch


@pytest.mark.ac("AC-F10-180")
def test_explicit_github_mode_requires_every_bound_context_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "collect",
            "--output",
            str(tmp_path / "collection.json"),
            "--github-repository",
            "example/repo",
            "--pr",
            "7",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-001"
