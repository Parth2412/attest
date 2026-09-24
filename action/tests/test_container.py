"""Real-container contract probes for the F-11 Action runtime."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def docker_mount_root() -> Iterator[Path]:
    """Create fixtures below the checkout so the Docker daemon can mount them."""
    checkout = Path(__file__).resolve().parents[2]
    fixture_root = checkout / "build"
    fixture_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="action-container-", dir=fixture_root) as directory:
        yield Path(directory)


def _image() -> str:
    value = os.environ.get("ATTEST_ACTION_IMAGE")
    if value is None:
        pytest.fail("ATTEST_ACTION_IMAGE is required for container-contract tests")
    return value


def _docker(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _initialize_repository(repository: Path) -> tuple[str, str]:
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Test User")
    _git(repository, "config", "user.email", "test@example.com")
    tracked = repository / "tracked.txt"
    tracked.write_text("first\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "first")
    base = _git(repository, "rev-parse", "HEAD")
    tracked.write_text("second\n", encoding="utf-8")
    _git(repository, "commit", "-am", "second")
    return base, _git(repository, "rev-parse", "HEAD")


def _action_files(repository: Path) -> None:
    (repository / ".attest").mkdir()
    (repository / ".attest" / "policy.yaml").write_text(
        "version: 1\npolicies: []\n", encoding="utf-8"
    )
    (repository / "bundle.json").write_text("{}\n", encoding="utf-8")


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    source = tmp_path / "source"
    base, head = _initialize_repository(source)
    shallow = tmp_path / "workspace"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{source}", os.fspath(shallow)],
        check=True,
        capture_output=True,
    )
    _action_files(shallow)
    return shallow, base, head


def _complete_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "workspace"
    base, head = _initialize_repository(repository)
    _action_files(repository)
    return repository, base, head


def _push_event(root: Path, base: str, head: str) -> Path:
    path = root / "event.json"
    path.write_text(
        json.dumps(
            {
                "before": base,
                "after": head,
                "created": False,
                "deleted": False,
                "ref": "refs/heads/main",
                "repository": {"full_name": "example/repo"},
            }
        ),
        encoding="utf-8",
    )
    return path


def _runner_arguments(root: Path, head: str) -> list[str]:
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": "/github/event.json",
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_SHA": head,
        "GITHUB_WORKFLOW_REF": "example/repo/.github/workflows/attest.yml@refs/heads/main",
        "GITHUB_WORKSPACE": "/github/workspace",
    }
    arguments = ["run", "--rm", "--volume", f"{root}:/github"]
    for name, value in values.items():
        arguments.extend(["--env", f"{name}={value}"])
    return arguments


def _diagnostic(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    decoded: object = json.loads(result.stderr)
    assert isinstance(decoded, dict)
    error = decoded.get("error")
    assert isinstance(error, dict)
    return error


def _fake_attest(root: Path) -> Path:
    digest = "d" * 64
    statement = {
        "subject": [{"name": "changeset", "digest": {"sha256": digest}}],
        "predicate": {
            "authorship": {"mode": "ai-assisted"},
            "review": {"required": True, "state": "approved", "humanApprovals": 1},
        },
    }
    report = {
        "schemaVersion": "0.1.0",
        "command": "run",
        "outcome": "success",
        "exitCode": 0,
        "data": {
            "stages": [],
            "storeRef": {
                "backend": "git-ref",
                "digest": digest,
                "bundleDigest": "e" * 64,
                "location": "refs/attestations/sha256/example",
                "storedAt": "2026-09-16T00:00:00Z",
            },
            "verification": {"status": "verified", "statement": statement},
            "decision": {"outcome": "allow", "exitCode": 0},
        },
        "warnings": [],
    }
    bundle = {"verificationMaterial": {"tlogEntries": [{"logIndex": "42"}]}}
    executable = root / "fake-attest"
    executable.write_text(
        "#!/opt/venv/bin/python\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"report = {json.dumps(report, separators=(',', ':'))!r}\n"
        f"bundle = {json.dumps(bundle, separators=(',', ':'))!r}\n"
        "Path('/github/observed.json').write_text(json.dumps(dict(os.environ)))\n"
        "for index, argument in enumerate(sys.argv):\n"
        "    if argument == '--output' and index + 1 < len(sys.argv):\n"
        "        Path(sys.argv[index + 1]).write_text(bundle)\n"
        "sys.stdout.write(report + '\\n')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


@pytest.mark.container
@pytest.mark.ac("AC-F11-180")
def test_image_installs_exact_cli_and_uses_the_isolated_exec_entrypoint() -> None:
    inspected = _docker("image", "inspect", _image(), "--format", "{{json .Config.Entrypoint}}")
    version = _docker(
        "run",
        "--rm",
        "--entrypoint",
        "/opt/venv/bin/attest",
        _image(),
        "--version",
    )

    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout) == [
        "/opt/venv/bin/python",
        "-I",
        "/opt/attest/entrypoint.py",
    ]
    assert version.returncode == 0, version.stderr
    assert version.stdout == "attest 0.1.3\n"


@pytest.mark.container
@pytest.mark.ac("AC-F11-020")
def test_container_checks_oidc_before_missing_repository_paths() -> None:
    result = _docker("run", "--rm", _image(), "--mode", "run")

    assert result.returncode == 2
    diagnostic = _diagnostic(result)
    assert diagnostic["code"] == "ERR-SIGN-301"
    assert "id-token: write" in str(diagnostic)


@pytest.mark.container
@pytest.mark.ac("AC-F11-040")
@pytest.mark.ac("AC-F11-050")
@pytest.mark.ac("AC-F11-060")
@pytest.mark.ac("AC-F11-130")
@pytest.mark.ac("AC-F11-160")
def test_container_runs_the_full_sanitized_output_boundary(docker_mount_root: Path) -> None:
    _, base, head = _complete_repository(docker_mount_root)
    _push_event(docker_mount_root, base, head)
    fake_attest = _fake_attest(docker_mount_root)
    output = docker_mount_root / "output"
    summary = docker_mount_root / "summary"
    output.touch()
    summary.touch()
    secret = "container-token-must-not-leak"
    arguments = _runner_arguments(docker_mount_root, head)
    arguments.extend(
        [
            "--volume",
            f"{fake_attest}:/opt/venv/bin/attest:ro",
            "--env",
            "ACTIONS_ID_TOKEN_REQUEST_URL=https://example.invalid/oidc",
            "--env",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN=opaque",
            "--env",
            f"GITHUB_TOKEN={secret}",
            "--env",
            "GITHUB_OUTPUT=/github/output",
            "--env",
            "GITHUB_STEP_SUMMARY=/github/summary",
            "--env",
            "PYTHONPATH=/github/workspace",
            "--env",
            "BASH_ENV=/github/workspace/tracked.txt",
            _image(),
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
        ]
    )

    result = _docker(*arguments)

    assert result.returncode == 0, result.stderr
    rendered_output = output.read_text(encoding="utf-8")
    rendered_summary = summary.read_text(encoding="utf-8")
    assert "changeset-digest<<" in rendered_output
    assert "attestation-ref<<" in rendered_output
    assert "decision<<" in rendered_output
    assert "log-index<<" in rendered_output
    assert "ai-assisted" in rendered_summary
    assert "approved" in rendered_summary
    assert secret not in result.stdout + result.stderr + rendered_output + rendered_summary
    observed = json.loads((docker_mount_root / "observed.json").read_text(encoding="utf-8"))
    assert observed["GITHUB_EVENT_NAME"] == "push"
    assert "PYTHONPATH" not in observed
    assert "BASH_ENV" not in observed


@pytest.mark.container
@pytest.mark.ac("AC-F11-070")
def test_container_rejects_pull_request_target() -> None:
    result = _docker(
        "run",
        "--rm",
        "--env",
        "ACTIONS_ID_TOKEN_REQUEST_URL=https://example.invalid/oidc",
        "--env",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN=opaque",
        "--env",
        "GITHUB_ACTIONS=true",
        "--env",
        "GITHUB_EVENT_NAME=pull_request_target",
        "--env",
        "GITHUB_SERVER_URL=https://github.com",
        _image(),
        "--mode",
        "run",
    )

    assert result.returncode == 2
    assert _diagnostic(result)["code"] == "ERR-CONFIG-007"


@pytest.mark.container
@pytest.mark.ac("AC-F11-030")
@pytest.mark.parametrize("mode", ["run", "verify", "gate"])
def test_container_rejects_shallow_history_in_every_mode(
    docker_mount_root: Path, mode: str
) -> None:
    _, base, head = _repository(docker_mount_root)
    _push_event(docker_mount_root, base, head)
    arguments = _runner_arguments(docker_mount_root, head)
    if mode == "run":
        arguments.extend(
            [
                "--env",
                "ACTIONS_ID_TOKEN_REQUEST_URL=https://example.invalid/oidc",
                "--env",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN=opaque",
            ]
        )
    arguments.extend([_image(), "--mode", mode])
    if mode in {"verify", "gate"}:
        arguments.extend(["--bundle", "bundle.json"])

    result = _docker(*arguments)

    assert result.returncode == 2
    diagnostic = _diagnostic(result)
    assert diagnostic["code"] == "ERR-CONFIG-008"
    assert "fetch-depth: 0" in str(diagnostic)


@pytest.mark.container
@pytest.mark.ac("AC-F11-130")
@pytest.mark.parametrize(
    "arguments",
    [
        ("--mode", "run", "--push-attestation", "TRUE"),
        ("--mode", "verify"),
        ("--mode", "gate", "--bundle", "../escape.json"),
    ],
)
def test_container_rejects_invalid_closed_inputs(arguments: tuple[str, ...]) -> None:
    result = _docker("run", "--rm", _image(), *arguments)

    assert result.returncode == 2
    assert _diagnostic(result)["code"] == "ERR-CONFIG-007"


@pytest.mark.container
@pytest.mark.ac("AC-F11-160")
def test_isolated_python_ignores_repository_import_and_shell_startup_paths(
    docker_mount_root: Path,
) -> None:
    marker = docker_mount_root / "executed"
    workspace = docker_mount_root / "workspace"
    workspace.mkdir()
    (workspace / "sitecustomize.py").write_text(
        "from pathlib import Path\nPath('/github/executed').touch()\n", encoding="utf-8"
    )
    startup = workspace / "startup"
    startup.write_text("touch /github/executed\n", encoding="utf-8")
    result = _docker(
        "run",
        "--rm",
        "--volume",
        f"{docker_mount_root}:/github",
        "--env",
        "PYTHONPATH=/github/workspace",
        "--env",
        "PYTHONHOME=/github/workspace",
        "--env",
        "BASH_ENV=/github/workspace/startup",
        "--env",
        "ENV=/github/workspace/startup",
        _image(),
        "--mode",
        "run",
        "--push-attestation",
        "TRUE",
    )

    assert result.returncode == 2
    assert _diagnostic(result)["code"] == "ERR-CONFIG-007"
    assert not marker.exists()
