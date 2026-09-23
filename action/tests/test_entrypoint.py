"""F-11 Action-boundary contract tests."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from action import entrypoint

_OID = "a" * 40
_DIGEST = "d" * 64
_TOKEN = "github-token-must-not-leak"
_OIDC_TOKEN = "oidc-request-token-must-not-leak"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
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
    policy = repository / ".attest" / "policy.yaml"
    policy.parent.mkdir()
    policy.write_text("version: 1\npolicies: []\n", encoding="utf-8")
    (repository / "bundle.json").write_bytes(_bundle())
    return repository, base, _git(repository, "rev-parse", "HEAD")


def _push_event(base: str, head: str) -> dict[str, object]:
    return {
        "before": base,
        "after": head,
        "created": False,
        "deleted": False,
        "ref": "refs/heads/main",
        "repository": {"full_name": "example/repo"},
    }


def _pull_request_event(base: str, head: str) -> dict[str, object]:
    return {
        "action": "synchronize",
        "number": 7,
        "repository": {"full_name": "example/repo"},
        "pull_request": {
            "base": {
                "sha": base,
                "ref": "main",
                "repo": {"full_name": "example/repo"},
            },
            "head": {
                "sha": head,
                "ref": "feature",
                "repo": {"full_name": "example/repo"},
            },
        },
    }


def _runner_environment(
    tmp_path: Path,
    repository: Path,
    base: str,
    head: str,
    *,
    event_name: str = "push",
    event: Mapping[str, object] | None = None,
) -> dict[str, str]:
    payload = dict(_push_event(base, head) if event is None else event)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    output_path = tmp_path / "github-output"
    summary_path = tmp_path / "github-summary"
    output_path.touch()
    summary_path.touch()
    environment = {
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": _OIDC_TOKEN,
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://pipelines.actions.githubusercontent.com/oidc",
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": os.fspath(event_path),
        "GITHUB_OUTPUT": os.fspath(output_path),
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_SHA": head,
        "GITHUB_STEP_SUMMARY": os.fspath(summary_path),
        "GITHUB_TOKEN": _TOKEN,
        "GITHUB_WORKFLOW_REF": "example/repo/.github/workflows/attest.yml@refs/heads/main",
        "GITHUB_WORKSPACE": os.fspath(repository),
    }
    if event_name == "pull_request":
        environment.update(
            GITHUB_BASE_REF="main",
            GITHUB_HEAD_REF="feature",
            GITHUB_REF="refs/pull/7/merge",
        )
    return environment


def _statement(
    *, authorship: str = "ai-assisted", review_state: str = "approved"
) -> dict[str, object]:
    return {
        "subject": [{"name": "changeset", "digest": {"sha256": _DIGEST}}],
        "predicate": {
            "authorship": {"mode": authorship},
            "review": {
                "required": True,
                "state": review_state,
                "humanApprovals": 1,
            },
        },
    }


def _report(
    mode: str,
    *,
    decision: str = "allow",
    exit_code: int = 0,
    location: str = "refs/attestations/sha256/example",
    statement: dict[str, object] | None = None,
    verification_failure: str | None = None,
) -> dict[str, object]:
    verification: dict[str, object] = {
        "status": "failed" if verification_failure is not None else "verified",
        "checks": [],
        "statement": None
        if verification_failure is not None
        else _statement()
        if statement is None
        else statement,
        "failureCode": verification_failure,
        "verifiedIdentity": None
        if verification_failure is not None
        else "https://github.com/example/repo/.github/workflows/attest.yml@refs/heads/main",
        "verifiedIssuer": None
        if verification_failure is not None
        else "https://token.actions.githubusercontent.com",
        "transparencyLogVerified": verification_failure is None,
    }
    if mode == "verify":
        data: dict[str, object] = {"verification": verification}
        outcome = "success"
    elif mode == "gate":
        data = {
            "verification": verification,
            "decision": {"outcome": decision, "exitCode": exit_code},
        }
        outcome = "denied" if decision == "deny" else "warning" if decision == "warn" else "success"
    else:
        data = {
            "stages": [],
            "storeRef": {
                "backend": "git-ref",
                "digest": _DIGEST,
                "bundleDigest": "e" * 64,
                "location": location,
                "storedAt": "2026-09-16T00:00:00Z",
            },
            "verification": verification,
            "decision": {"outcome": decision, "exitCode": exit_code},
        }
        outcome = "denied" if decision == "deny" else "warning" if decision == "warn" else "success"
    return {
        "schemaVersion": "0.1.0",
        "command": mode,
        "outcome": outcome,
        "exitCode": exit_code,
        "data": data,
        "warnings": [],
    }


def _failure_report(mode: str, *, exit_code: int) -> dict[str, object]:
    return {
        "schemaVersion": "0.1.0",
        "command": mode,
        "outcome": "failed",
        "exitCode": exit_code,
        "data": None,
        "warnings": [],
        "error": {
            "code": "ERR-STORE-405" if exit_code == 5 else "ERR-SIGN-302",
            "message": "The operation failed",
            "remediation": "Retry or reject the evidence",
        },
    }


def _bundle(log_index: str = "42") -> bytes:
    return json.dumps({"verificationMaterial": {"tlogEntries": [{"logIndex": log_index}]}}).encode()


def _fake_attest(
    tmp_path: Path,
    report: Mapping[str, object],
    *,
    exit_code: int,
    record: Path | None = None,
    stderr_text: str = "",
) -> Path:
    executable = tmp_path / f"fake-attest-{len(list(tmp_path.glob('fake-attest-*')))}"
    record_path = "" if record is None else os.fspath(record)
    source = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

report = {json.dumps(dict(report))!r}
record = {record_path!r}
if record:
    Path(record).write_text(json.dumps({{"argv": sys.argv[1:], "environment": dict(os.environ)}}))
for index, argument in enumerate(sys.argv):
    if argument == "--output" and index + 1 < len(sys.argv):
        Path(sys.argv[index + 1]).write_bytes({bytes(_bundle())!r})
sys.stdout.write(report + "\\n")
sys.stderr.write({stderr_text!r})
raise SystemExit({exit_code})
"""
    executable.write_text(source, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _invoke(
    arguments: list[str],
    environment: Mapping[str, str],
    executable: Path,
) -> tuple[int, str]:
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8", closefd=True) as stderr:
            result = entrypoint.run_action(
                arguments,
                environment,
                stderr=stderr,
                attest_executable=executable,
            )
        with os.fdopen(read_fd, encoding="utf-8", closefd=True) as output:
            rendered = output.read()
    except Exception:
        os.close(read_fd)
        raise
    return result, rendered


def _error_code(rendered: str) -> str:
    return str(json.loads(rendered)["error"]["code"])


@pytest.mark.ac("AC-F11-020")
def test_run_rejects_missing_oidc_before_any_repository_read(tmp_path: Path) -> None:
    environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": os.fspath(tmp_path / "must-not-be-read"),
        "GITHUB_WORKSPACE": os.fspath(tmp_path / "must-not-be-read-either"),
    }
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 2
    diagnostic = json.loads(rendered)["error"]
    assert diagnostic["code"] == "ERR-SIGN-301"
    assert "id-token: write" in diagnostic["message"] + diagnostic["remediation"]


@pytest.mark.ac("AC-F11-030")
@pytest.mark.parametrize("mode", ["run", "verify", "gate"])
def test_every_mode_rejects_shallow_history_with_exact_remediation(
    tmp_path: Path, mode: str
) -> None:
    source, base, head = _repository(tmp_path)
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{source}", os.fspath(shallow)],
        check=True,
        capture_output=True,
    )
    (shallow / ".attest").mkdir()
    (shallow / ".attest" / "policy.yaml").write_text("version: 1\npolicies: []\n", encoding="utf-8")
    (shallow / "bundle.json").write_text("{}\n", encoding="utf-8")
    environment = _runner_environment(tmp_path, shallow, base, head)
    executable = _fake_attest(tmp_path, _report(mode), exit_code=0)
    arguments = ["--mode", mode]
    if mode in {"verify", "gate"}:
        arguments.extend(["--bundle", "bundle.json"])

    exit_code, rendered = _invoke(arguments, environment, executable)

    assert exit_code == 2
    diagnostic = json.loads(rendered)["error"]
    assert diagnostic["code"] == "ERR-CONFIG-008"
    assert "fetch-depth: 0" in diagnostic["message"] + diagnostic["remediation"]


@pytest.mark.ac("AC-F11-040")
@pytest.mark.parametrize(
    ("mode", "decision", "cli_exit", "fail_on_violation", "expected_exit"),
    [
        ("run", "allow", 0, "true", 0),
        ("run", "deny", 3, "true", 3),
        ("run", "deny", 3, "false", 0),
        ("run", "deny", 4, "false", 4),
        ("gate", "deny", 5, "false", 0),
        ("verify", "verified", 0, None, 0),
    ],
)
def test_outputs_are_earned_before_success_or_policy_exit(
    tmp_path: Path,
    mode: str,
    decision: str,
    cli_exit: int,
    fail_on_violation: str | None,
    expected_exit: int,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    report_decision = "allow" if decision == "verified" else decision
    executable = _fake_attest(
        tmp_path,
        _report(mode, decision=report_decision, exit_code=cli_exit),
        exit_code=cli_exit,
    )
    arguments = ["--mode", mode]
    if mode in {"verify", "gate"}:
        arguments.extend(["--bundle", "bundle.json"])
    if fail_on_violation is not None:
        arguments.extend(["--fail-on-violation", fail_on_violation])

    exit_code, rendered = _invoke(arguments, environment, executable)

    assert exit_code == expected_exit, rendered
    output = Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8")
    assert _DIGEST in output
    assert "decision<<" in output
    assert f"\n{decision}\n" in output
    assert "log-index<<" in output
    assert "\n42\n" in output
    if mode == "run":
        assert "refs/attestations/sha256/example" in output
    else:
        assert "\nbundle.json\n" in output


@pytest.mark.ac("AC-F11-040")
def test_outputs_remain_empty_before_their_prerequisite_stage(tmp_path: Path) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    failure = {
        "schemaVersion": "0.1.0",
        "command": "verify",
        "outcome": "failed",
        "exitCode": 4,
        "data": {
            "verification": {
                "status": "failed",
                "checks": [],
                "statement": None,
                "failureCode": "ERR-VERIFY-013",
                "verifiedIdentity": None,
                "verifiedIssuer": None,
                "transparencyLogVerified": False,
            }
        },
        "warnings": [],
        "error": {
            "code": "ERR-VERIFY-013",
            "message": "Sigstore verification failed",
            "remediation": "Reject the bundle",
        },
    }
    executable = _fake_attest(tmp_path, failure, exit_code=4)

    exit_code, _ = _invoke(["--mode", "verify", "--bundle", "bundle.json"], environment, executable)

    assert exit_code == 4
    output = Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8")
    assert "attestation-ref<<" in output
    assert "changeset-digest" not in output
    assert "decision" not in output
    assert "log-index" not in output


@pytest.mark.ac("AC-F11-040")
@pytest.mark.ac("AC-F11-180")
def test_denied_run_preserves_safe_verification_failure_without_fact_outputs(
    tmp_path: Path,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(
        tmp_path,
        _report(
            "run",
            decision="deny",
            exit_code=4,
            verification_failure="ERR-VERIFY-013",
        ),
        exit_code=4,
    )

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 4
    diagnostic = json.loads(rendered)["error"]
    assert diagnostic == {
        "code": "ERR-VERIFY-013",
        "message": "Sigstore cryptographic verification failed",
        "remediation": "Reject the bundle and inspect the signer and trust configuration",
    }
    assert Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8") == ""
    assert Path(environment["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8") == ""


@pytest.mark.ac("AC-F11-160")
@pytest.mark.ac("AC-F11-180")
def test_denied_run_rejects_unknown_verification_failure_code(tmp_path: Path) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(
        tmp_path,
        _report(
            "run",
            decision="deny",
            exit_code=4,
            verification_failure="ERR-VERIFY-999",
        ),
        exit_code=4,
    )

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 1
    assert _error_code(rendered) == "ERR-INTERNAL-001"
    assert Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8") == ""
    assert Path(environment["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8") == ""


@pytest.mark.ac("AC-F11-040")
def test_run_resolves_a_platform_temporary_directory_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    alias = tmp_path / "runtime-link"
    alias.symlink_to(runtime, target_is_directory=True)

    @contextmanager
    def linked_temporary_directory(*, prefix: str) -> Iterator[str]:
        assert prefix == "attest-action-"
        yield os.fspath(alias)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", linked_temporary_directory)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 0, rendered


@pytest.mark.ac("AC-F11-050")
def test_summary_contains_only_escaped_validated_decision_and_evidence_facts(
    tmp_path: Path,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 0, rendered
    summary = Path(environment["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
    assert "Decision" in summary
    assert "allow" in summary
    assert "Authorship mode" in summary
    assert "ai-assisted" in summary
    assert "Review state" in summary
    assert "approved" in summary
    assert "Human approvals" in summary
    assert "1" in summary
    assert "<" not in summary
    assert ">" not in summary


@pytest.mark.ac("AC-F11-050")
@pytest.mark.ac("AC-F11-160")
def test_adversarial_report_text_cannot_inject_markup_or_workflow_commands(
    tmp_path: Path,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    malicious = _statement(authorship="ai-assisted\n::error::owned<script>")
    executable = _fake_attest(
        tmp_path,
        _report("run", statement=malicious, location="x\n::error::owned"),
        exit_code=0,
    )

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 1
    assert _error_code(rendered) == "ERR-INTERNAL-001"
    combined = (
        Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8")
        + Path(environment["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
        + rendered
    )
    assert "::error::owned" not in combined
    assert "<script>" not in combined


@pytest.mark.ac("AC-F11-060")
def test_run_needs_only_automatic_github_and_oidc_tokens_and_never_emits_them(
    tmp_path: Path,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 0, rendered
    emitted = (
        rendered
        + Path(environment["GITHUB_OUTPUT"]).read_text(encoding="utf-8")
        + Path(environment["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
    )
    assert _TOKEN not in emitted
    assert _OIDC_TOKEN not in emitted
    assert not any("SECRET" in name for name in environment)


@pytest.mark.ac("AC-F11-070")
@pytest.mark.parametrize("event_name", ["push", "pull_request"])
def test_supported_branch_events_reach_the_cli(tmp_path: Path, event_name: str) -> None:
    repository, base, head = _repository(tmp_path)
    event = _push_event(base, head)
    if event_name == "pull_request":
        event = _pull_request_event(base, head)
    environment = _runner_environment(
        tmp_path,
        repository,
        base,
        head,
        event_name=event_name,
        event=event,
    )
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 0, rendered


@pytest.mark.ac("AC-F11-070")
@pytest.mark.parametrize(
    "mutation",
    [
        "pull-request-target",
        "unsupported",
        "tag",
        "created",
        "deleted",
        "zero-before",
        "zero-after",
        "repository-mismatch",
        "ref-mismatch",
        "missing-before",
        "malformed",
    ],
)
def test_unsupported_malformed_or_inconsistent_events_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    repository, base, head = _repository(tmp_path)
    event = _push_event(base, head)
    event_name = "push"
    if mutation == "pull-request-target":
        event_name = "pull_request_target"
        event = _pull_request_event(base, head)
    elif mutation == "unsupported":
        event_name = "schedule"
    elif mutation == "tag":
        event["ref"] = "refs/tags/v0.1.0"
    elif mutation == "created":
        event["created"] = True
    elif mutation == "deleted":
        event["deleted"] = True
    elif mutation == "zero-before":
        event["before"] = "0" * 40
    elif mutation == "zero-after":
        event["after"] = "0" * 40
    elif mutation == "repository-mismatch":
        event["repository"] = {"full_name": "attacker/repo"}
    elif mutation == "ref-mismatch":
        event["ref"] = "refs/heads/other"
    elif mutation == "missing-before":
        del event["before"]
    environment = _runner_environment(
        tmp_path,
        repository,
        base,
        head,
        event_name=event_name,
        event=event,
    )
    if mutation == "malformed":
        Path(environment["GITHUB_EVENT_PATH"]).write_text("{", encoding="utf-8")
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 2
    assert _error_code(rendered) == "ERR-CONFIG-007"


@pytest.mark.ac("AC-F11-130")
@pytest.mark.parametrize(
    ("arguments", "valid"),
    [
        (["--mode", "run"], True),
        (["--mode", "run", "--push-attestation", "false"], True),
        (["--mode", "run", "--fail-on-violation", "false"], True),
        (
            [
                "--mode",
                "run",
                "--policy",
                "",
                "--bundle",
                "",
                "--push-attestation",
                "",
                "--fail-on-violation",
                "",
            ],
            True,
        ),
        (["--mode", "verify", "--bundle", "bundle.json"], True),
        (
            [
                "--mode",
                "verify",
                "--policy",
                "",
                "--bundle",
                "bundle.json",
                "--push-attestation",
                "",
                "--fail-on-violation",
                "",
            ],
            True,
        ),
        (["--mode", "gate", "--bundle", "bundle.json"], True),
        (["--mode", "gate", "--bundle", "bundle.json", "--policy", ".attest/policy.yaml"], True),
        (["--mode", ""], False),
        (["--mode", "unknown"], False),
        (["--mode", "run", "--bundle", "bundle.json"], False),
        (["--mode", "verify"], False),
        (["--mode", "verify", "--policy", ".attest/policy.yaml", "--bundle", "bundle.json"], False),
        (["--mode", "verify", "--bundle", "bundle.json", "--push-attestation", "true"], False),
        (["--mode", "gate"], False),
        (["--mode", "gate", "--bundle", "bundle.json", "--push-attestation", "false"], False),
        (["--mode", "run", "--push-attestation", "TRUE"], False),
        (["--mode", "run", "--fail-on-violation", "0"], False),
        (["--mode", "run", "--mode", "run"], False),
        (["--mode", "run", "--unknown", "value"], False),
    ],
)
def test_closed_mode_and_input_combinations(
    tmp_path: Path, arguments: list[str], valid: bool
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    mode = arguments[arguments.index("--mode") + 1] if "--mode" in arguments else "run"
    report_mode = mode if mode in {"run", "verify", "gate"} else "run"
    executable = _fake_attest(tmp_path, _report(report_mode), exit_code=0)

    exit_code, rendered = _invoke(arguments, environment, executable)

    if valid:
        assert exit_code == 0, rendered
    else:
        assert exit_code == 2
        assert _error_code(rendered) == "ERR-CONFIG-007"


@pytest.mark.ac("AC-F11-130")
@pytest.mark.parametrize(
    "unsafe_path",
    ["/absolute.json", "../escape.json", "nested/../../escape.json", ".", ""],
)
def test_unsafe_bundle_paths_are_rejected(tmp_path: Path, unsafe_path: str) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(tmp_path, _report("verify"), exit_code=0)

    exit_code, rendered = _invoke(
        ["--mode", "verify", "--bundle", unsafe_path], environment, executable
    )

    assert exit_code == 2
    assert _error_code(rendered) == "ERR-CONFIG-007"


@pytest.mark.ac("AC-F11-130")
@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "oversized", "invalid-utf8"])
def test_non_regular_oversized_or_non_utf8_bundle_is_rejected(tmp_path: Path, kind: str) -> None:
    repository, base, head = _repository(tmp_path)
    candidate = repository / "unsafe.json"
    if kind == "symlink":
        candidate.symlink_to("bundle.json")
    elif kind == "directory":
        candidate.mkdir()
    elif kind == "fifo":
        os.mkfifo(candidate)
    elif kind == "oversized":
        with candidate.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
    else:
        candidate.write_bytes(b"\xff")
    environment = _runner_environment(tmp_path, repository, base, head)
    executable = _fake_attest(tmp_path, _report("verify"), exit_code=0)

    exit_code, rendered = _invoke(
        ["--mode", "verify", "--bundle", "unsafe.json"], environment, executable
    )

    assert exit_code == 2
    assert _error_code(rendered) == "ERR-CONFIG-007"


@pytest.mark.ac("AC-F11-130")
def test_unexpected_runner_input_is_rejected(tmp_path: Path) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    environment["INPUT_UNDOCUMENTED"] = "value"
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 2
    assert _error_code(rendered) == "ERR-CONFIG-007"


@pytest.mark.ac("AC-F11-160")
def test_environment_is_sanitized_and_repository_executables_never_run(tmp_path: Path) -> None:
    repository, base, head = _repository(tmp_path)
    marker = tmp_path / "executed"
    malicious = repository / "git"
    malicious.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
    malicious.chmod(0o755)
    (repository / "attest.py").write_text(
        f"from pathlib import Path\nPath({os.fspath(marker)!r}).touch()\n", encoding="utf-8"
    )
    environment = _runner_environment(tmp_path, repository, base, head)
    environment.update(
        PATH=f"{repository}:{os.environ.get('PATH', '')}",
        PYTHONPATH=os.fspath(repository),
        PYTHONHOME=os.fspath(repository),
        BASH_ENV=os.fspath(repository / "attest.py"),
        ENV=os.fspath(repository / "attest.py"),
        GIT_CONFIG_SYSTEM=os.fspath(repository / "attest.py"),
        LD_PRELOAD=os.fspath(repository / "attest.py"),
    )
    record = tmp_path / "record.json"
    executable = _fake_attest(tmp_path, _report("run"), exit_code=0, record=record)

    exit_code, rendered = _invoke(["--mode", "run"], environment, executable)

    assert exit_code == 0, rendered
    assert not marker.exists()
    observed = json.loads(record.read_text(encoding="utf-8"))["environment"]
    for forbidden in (
        "PYTHONPATH",
        "PYTHONHOME",
        "BASH_ENV",
        "ENV",
        "GIT_CONFIG_SYSTEM",
        "LD_PRELOAD",
    ):
        assert forbidden not in observed
    assert repository.name not in observed["PATH"]
    assert observed["GITHUB_EVENT_NAME"] == "push"
    assert observed["GITHUB_TOKEN"] == _TOKEN


@pytest.mark.ac("AC-F11-160")
@pytest.mark.parametrize(
    ("cli_exit", "decision", "fail_on_violation", "expected"),
    [
        (3, "deny", "false", 0),
        (5, "deny", "false", 0),
        (4, "deny", "false", 4),
        (5, "failure", "false", 5),
        (6, "deny", "false", 6),
        (3, "deny", "true", 3),
    ],
)
def test_advisory_policy_never_neutralizes_fatal_failures(
    tmp_path: Path,
    cli_exit: int,
    decision: str,
    fail_on_violation: str,
    expected: int,
) -> None:
    repository, base, head = _repository(tmp_path)
    environment = _runner_environment(tmp_path, repository, base, head)
    report = (
        _failure_report("run", exit_code=cli_exit)
        if decision == "failure" or cli_exit in {4, 6}
        else _report("run", decision=decision, exit_code=cli_exit)
    )
    executable = _fake_attest(tmp_path, report, exit_code=cli_exit)

    exit_code, rendered = _invoke(
        ["--mode", "run", "--fail-on-violation", fail_on_violation],
        environment,
        executable,
    )

    assert exit_code == expected
    if decision == "failure":
        assert _error_code(rendered) == "ERR-STORE-405"


@pytest.mark.ac("AC-F11-010")
def test_dockerfile_uses_pinned_multi_platform_bases_and_exec_entrypoint() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    python_base = (
        "python:3.12.14-slim-trixie@"
        "sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
    )
    assert dockerfile.count(python_base) == 2
    assert "ghcr.io/astral-sh/uv:0.11.2@sha256:" in dockerfile
    assert 'ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/attest/entrypoint.py"]' in dockerfile
    assert "COPY action/action.yml" not in dockerfile
