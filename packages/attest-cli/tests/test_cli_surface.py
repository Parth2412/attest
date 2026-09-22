"""F-10 installed command, option, entry-point, and boundary tests."""

from __future__ import annotations

import ast
import json
import os
import site
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import cast

import pytest
from click import Group
from typer.main import get_command
from typer.testing import CliRunner

from attest_cli.app import COMMAND_EXIT_CODES, app
from attest_cli.exit_codes import ExitCode

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_COMMANDS = {
    "build",
    "collect",
    "config",
    "doctor",
    "gate",
    "init",
    "inspect",
    "push",
    "run",
    "sign",
    "verify",
    "version",
}
EXPECTED_EXITS = {
    "build": (0, 1, 2),
    "collect": (0, 1, 2, 6),
    "config-show": (0, 1, 2),
    "doctor": (0, 1, 2),
    "gate": (0, 1, 2, 3, 4, 5),
    "init": (0, 1, 2),
    "inspect": (0, 1, 2, 5),
    "push": (0, 1, 2, 6),
    "run": (0, 1, 2, 3, 4, 5, 6),
    "sign": (0, 1, 2, 6),
    "verify": (0, 1, 2, 4, 5),
    "version": (0, 1),
}
EXPECTED_OPTIONS = {
    "init": {
        "--action-ref",
        "--checkout-ref",
        "--config",
        "--default-branch",
        "--github-repository",
        "--json",
        "--no-color",
        "--repository",
    },
    "collect": {
        "--base",
        "--claim",
        "--config",
        "--git-backend",
        "--github-event",
        "--github-repository",
        "--head",
        "--json",
        "--no-color",
        "--output",
        "--overwrite",
        "--pr",
        "--repository",
        "--target-branch",
    },
    "build": {"--config", "--input", "--json", "--no-color", "--output", "--overwrite"},
    "sign": {
        "--config",
        "--input",
        "--json",
        "--no-color",
        "--output",
        "--overwrite",
        "--signing-environment",
        "--signing-timeout-seconds",
    },
    "push": {
        "--change-set-digest",
        "--config",
        "--fallback-directory",
        "--git-backend",
        "--git-remote",
        "--git-timeout-seconds",
        "--input",
        "--json",
        "--no-color",
        "--oci-insecure",
        "--oci-repository",
        "--oci-staging-directory",
        "--oci-subject-digest",
        "--oci-subject-media-type",
        "--oci-subject-size",
        "--oci-timeout-seconds",
        "--oci-tls-verify",
        "--repository",
        "--store-backend",
        "--store-directory",
    },
    "verify": {
        "--base",
        "--config",
        "--head",
        "--identity",
        "--input",
        "--issuer",
        "--json",
        "--no-color",
        "--offline",
        "--online",
        "--repository",
        "--trust-config-file",
        "--verify-environment",
    },
    "gate": {
        "--base",
        "--config",
        "--git-backend",
        "--head",
        "--identity",
        "--input",
        "--issuer",
        "--json",
        "--no-color",
        "--offline",
        "--online",
        "--policy",
        "--repository",
        "--target-branch",
        "--trust-config-file",
        "--verify-environment",
    },
    "run": {
        "--base",
        "--claim",
        "--config",
        "--fallback-directory",
        "--git-backend",
        "--git-remote",
        "--git-timeout-seconds",
        "--github-event",
        "--github-repository",
        "--head",
        "--identity",
        "--issuer",
        "--json",
        "--no-color",
        "--oci-insecure",
        "--oci-repository",
        "--oci-staging-directory",
        "--oci-subject-digest",
        "--oci-subject-media-type",
        "--oci-subject-size",
        "--oci-timeout-seconds",
        "--oci-tls-verify",
        "--offline",
        "--online",
        "--output",
        "--overwrite",
        "--policy",
        "--pr",
        "--repository",
        "--signing-environment",
        "--signing-timeout-seconds",
        "--store-backend",
        "--store-directory",
        "--target-branch",
        "--trust-config-file",
        "--verify-environment",
        "--work-directory",
    },
    "inspect": {"--config", "--input", "--json", "--no-color"},
    "config-show": {
        "--config",
        "--fallback-directory",
        "--git-backend",
        "--git-remote",
        "--git-timeout-seconds",
        "--github-event",
        "--identity",
        "--issuer",
        "--json",
        "--no-color",
        "--oci-insecure",
        "--oci-repository",
        "--oci-staging-directory",
        "--oci-subject-digest",
        "--oci-subject-media-type",
        "--oci-subject-size",
        "--oci-timeout-seconds",
        "--oci-tls-verify",
        "--offline",
        "--online",
        "--policy",
        "--repository",
        "--resolved",
        "--signing-environment",
        "--signing-timeout-seconds",
        "--store-backend",
        "--store-directory",
        "--trust-config-file",
        "--verify-environment",
    },
    "doctor": {
        "--config",
        "--git-backend",
        "--json",
        "--no-color",
        "--offline",
        "--online",
        "--policy",
        "--probe-network",
        "--repository",
        "--signing-environment",
        "--store-backend",
        "--trust-config-file",
        "--verify-environment",
    },
    "version": {"--json", "--no-color"},
}


@pytest.fixture(scope="module")
def installed_cli(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("installed-cli")
    distributions = root / "dist"
    subprocess.run(
        [
            "uv",
            "build",
            "--package",
            "attest-cli",
            "--wheel",
            "--out-dir",
            str(distributions),
            "--no-build-logs",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    wheels = tuple(distributions.glob("attest_cli-*.whl"))
    assert len(wheels) == 1
    environment = root / "environment"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(environment)],
        check=True,
        capture_output=True,
    )
    python = environment / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheels[0])],
        check=True,
        capture_output=True,
    )
    dependency_paths = [
        *(str(path) for path in site.getsitepackages()),
        *(
            str(path)
            for path in sorted((REPOSITORY_ROOT / "packages").glob("*/src"))
            if path.parent.name != "attest-cli"
        ),
    ]
    runtime_environment = os.environ | {
        "NO_COLOR": "1",
        "PYTHONPATH": os.pathsep.join(dependency_paths),
    }
    return environment / "bin" / "attest", python, root, runtime_environment


@pytest.mark.ac("AC-F10-010")
@pytest.mark.ac("AC-F10-150")
def test_command_tree_is_exact_and_export_is_absent() -> None:
    root = cast(Group, get_command(app))
    assert root.commands
    assert set(root.commands) == EXPECTED_COMMANDS
    assert "export" not in CliRunner().invoke(app, ["--help"]).stdout


@pytest.mark.ac("AC-F10-150")
def test_every_leaf_option_is_an_exact_snapshot() -> None:
    root = cast(Group, get_command(app))
    leaves = {name: command for name, command in root.commands.items() if name != "config"}
    config = cast(Group, root.commands["config"])
    leaves["config-show"] = config.commands["show"]

    assert {
        name: {
            option
            for parameter in command.params
            for option in (*parameter.opts, *parameter.secondary_opts)
        }
        for name, command in leaves.items()
    } == EXPECTED_OPTIONS
    assert {
        option
        for parameter in root.params
        for option in (*parameter.opts, *parameter.secondary_opts)
    } == {"--version"}

    runner = CliRunner()
    assert runner.invoke(app, ["export", "--json"]).exit_code == 2
    assert runner.invoke(app, ["--show-completion"]).exit_code == 2


@pytest.mark.ac("AC-F10-010")
def test_command_exit_contract_is_exact() -> None:
    assert COMMAND_EXIT_CODES == EXPECTED_EXITS
    assert {item.name: int(item) for item in ExitCode} == {
        "SUCCESS": 0,
        "INTERNAL_ERROR": 1,
        "USAGE_ERROR": 2,
        "POLICY_VIOLATION": 3,
        "VERIFICATION_FAILURE": 4,
        "ATTESTATION_NOT_FOUND": 5,
        "TRANSIENT_FAILURE": 6,
    }


@pytest.mark.ac("AC-F10-060")
@pytest.mark.ac("AC-F10-150")
def test_no_command_exposes_a_secret_pattern_option() -> None:
    root = cast(Group, get_command(app))
    leaves = [command for name, command in root.commands.items() if name != "config"]
    config = cast(Group, root.commands["config"])
    leaves.extend(config.commands.values())
    options = {
        option
        for command in leaves
        for parameter in command.params
        for option in (*parameter.opts, *parameter.secondary_opts)
    }
    assert not any(
        fragment in option for option in options for fragment in ("token", "password", "auth")
    )


@pytest.mark.ac("AC-F10-150")
def test_leaf_help_exposes_json_and_only_version_omits_config() -> None:
    runner = CliRunner()
    for command in sorted(EXPECTED_COMMANDS - {"config"}):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, (command, result.output)
        assert "--json" in result.output
        assert ("--config" in result.output) is (command != "version")
    config_help = runner.invoke(app, ["config", "show", "--help"])
    assert config_help.exit_code == 0
    assert "--resolved" in config_help.output
    assert "--json" in config_help.output
    assert "--config" in config_help.output


@pytest.mark.ac("AC-F10-040")
def test_cli_source_has_no_peer_private_imports_or_domain_operation_definitions() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "attest_cli"
    forbidden_definitions = {
        "build_statement",
        "canonicalize",
        "collect_authorship",
        "collect_changeset",
        "collect_github",
        "evaluate",
        "inspect_bundle",
        "sign",
        "verify",
    }
    definitions: set[str] = set()
    private_peer_imports: set[str] = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                parts = node.module.split(".")
                if (
                    parts[0].startswith("attest_")
                    and parts[0] != "attest_cli"
                    and any(part.startswith("_") for part in parts[1:])
                ):
                    private_peer_imports.add(node.module)

    assert definitions.isdisjoint(forbidden_definitions)
    assert private_peer_imports == set()


@pytest.mark.ac("AC-F10-020")
@pytest.mark.ac("AC-F10-030")
def test_json_usage_error_is_one_sanitised_report() -> None:
    result = CliRunner().invoke(app, ["build", "--json"])

    assert result.exit_code == 2
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    report = json.loads(result.stdout)
    assert report == {
        "schemaVersion": "0.1.0",
        "command": "build",
        "outcome": "failed",
        "exitCode": 2,
        "data": None,
        "warnings": [],
        "error": {
            "code": "ERR-CONFIG-001",
            "message": "Invocation or resolved configuration is invalid or conflicting",
            "remediation": "Correct the documented command options and configuration values",
        },
    }


@pytest.mark.ac("AC-F10-230")
def test_help_and_root_version_do_not_read_configuration_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.stdout.startswith("attest ")


@pytest.mark.ac("AC-F10-250")
@pytest.mark.parametrize(
    ("arguments", "expected_exit"),
    [
        (["init", "--json"], 2),
        (["collect", "--json"], 2),
        (["build", "--json"], 2),
        (["sign", "--json"], 2),
        (["push", "--json"], 2),
        (["verify", "--json"], 2),
        (["gate", "--json"], 2),
        (["run", "--json"], 2),
        (["inspect", "--json"], 2),
        (["config", "show", "--json"], 2),
        (["doctor", "--json"], 0),
        (["version", "--json"], 0),
    ],
)
def test_every_command_is_noninteractive_with_closed_stdin_and_ci(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected_exit: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "attest_cli.commands._signing_endpoints",
        lambda _environment: ("https://fulcio.example",),
    )

    result = CliRunner().invoke(app, arguments, input="", env={"CI": "true"})

    assert result.exit_code == expected_exit
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout)["exitCode"] == expected_exit
    assert "Aborted" not in result.output


@pytest.mark.ac("AC-F10-250")
def test_no_option_has_a_prompt() -> None:
    root = cast(Group, get_command(app))
    commands = [command for name, command in root.commands.items() if name != "config"]
    config = cast(Group, root.commands["config"])
    commands.extend(config.commands.values())

    assert all(
        getattr(parameter, "prompt", None) is None
        for command in commands
        for parameter in command.params
    )


@pytest.mark.ac("AC-F10-240")
def test_distribution_exposes_exactly_one_console_script() -> None:
    package = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(package.read_text(encoding="utf-8"))["project"]
    assert project["scripts"] == {"attest": "attest_cli.__main__:main"}


@pytest.mark.ac("AC-F10-240")
def test_console_script_and_module_entry_point_are_equivalent() -> None:
    environment = os.environ | {"NO_COLOR": "1"}
    console = subprocess.run(
        ["uv", "run", "attest", "version", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    module = subprocess.run(
        ["uv", "run", sys.executable, "-m", "attest_cli", "version", "--json"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert console.returncode == module.returncode == 0
    assert console.stdout == module.stdout
    assert console.stderr == module.stderr == ""


@pytest.mark.ac("AC-F10-240")
def test_module_main_calls_the_single_root_application(monkeypatch: pytest.MonkeyPatch) -> None:
    from attest_cli import __main__ as main_module

    calls: list[None] = []
    monkeypatch.setattr(main_module, "app", lambda: calls.append(None))

    main_module.main()

    assert calls == [None]


@pytest.mark.ac("AC-F10-080")
@pytest.mark.performance
@pytest.mark.slow
def test_ten_clean_installed_help_processes_each_finish_under_300ms(
    installed_cli: tuple[Path, Path, Path, dict[str, str]],
) -> None:
    console, _, working_directory, environment = installed_cli
    durations: list[float] = []
    for _ in range(10):
        started = time.perf_counter()
        result = subprocess.run(
            [console, "--help"],
            check=False,
            capture_output=True,
            cwd=working_directory,
            env=environment,
        )
        durations.append(time.perf_counter() - started)
        assert result.returncode == 0
    assert max(durations) < 0.3, durations


@pytest.mark.ac("AC-F10-240")
@pytest.mark.slow
def test_installed_wheel_console_and_module_entry_points_are_equivalent(
    installed_cli: tuple[Path, Path, Path, dict[str, str]],
) -> None:
    console, python, working_directory, environment = installed_cli
    console_result = subprocess.run(
        [console, "version", "--json"],
        check=False,
        capture_output=True,
        text=True,
        cwd=working_directory,
        env=environment,
    )
    module_result = subprocess.run(
        [python, "-m", "attest_cli", "version", "--json"],
        check=False,
        capture_output=True,
        text=True,
        cwd=working_directory,
        env=environment,
    )

    assert console_result.returncode == module_result.returncode == 0
    assert console_result.stdout == module_result.stdout
    assert console_result.stderr == module_result.stderr == ""
