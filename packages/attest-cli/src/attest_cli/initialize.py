"""Exact, fail-closed repository initialisation for F-10."""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
from contextlib import suppress
from pathlib import Path
from typing import Final, Never
from urllib.parse import urlsplit

from attest_cli.errors import CliError, cli_error
from attest_cli.models import InitData
from attest_cli.safe_io import write_atomic

_ACTION_REF: Final[re.Pattern[str]] = re.compile(
    r"(?P<path>[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+)@(?P<sha>[0-9a-f]{40})"
)
_REPOSITORY_NAME: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
_BRANCH_NAME: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._/-]+")
_GIT_TIMEOUT_SECONDS: Final[int] = 5


def _invalid() -> Never:
    raise cli_error("ERR-CONFIG-001")


def _validate_repository_name(value: str) -> str:
    if _REPOSITORY_NAME.fullmatch(value) is None or any(
        part in {".", ".."} for part in value.split("/")
    ):
        _invalid()
    return value


def _validate_branch(value: str) -> str:
    components = value.split("/")
    if (
        _BRANCH_NAME.fullmatch(value) is None
        or value.startswith(("/", ".", "-"))
        or value.endswith(("/", ".", ".lock"))
        or "//" in value
        or ".." in value
        or "@{" in value
        or any(component.startswith(".") or component.endswith(".lock") for component in components)
    ):
        _invalid()
    return value


def _validate_action_ref(value: str) -> str:
    match = _ACTION_REF.fullmatch(value)
    if match is None or any(part in {".", ".."} for part in match.group("path").split("/")):
        _invalid()
    return value


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _git(repository: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        _invalid()
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603: fixed executable and arguments
            [
                executable,
                "--no-replace-objects",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-C",
                os.fspath(repository),
                *arguments,
            ],
            check=False,
            capture_output=True,
            env=_git_environment(),
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        _invalid()
    if result.returncode != 0:
        _invalid()
    try:
        output = result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeError:
        _invalid()
    if not output or "\x00" in output or "\n" in output:
        _invalid()
    return output


def _github_repository_from_remote(remote: str) -> str:
    if remote.startswith("git@github.com:"):
        path = remote.removeprefix("git@github.com:")
    else:
        try:
            parsed = urlsplit(remote)
        except ValueError:
            _invalid()
        if (
            parsed.scheme not in {"https", "ssh", "git"}
            or parsed.hostname != "github.com"
            or parsed.query
            or parsed.fragment
            or (parsed.username not in {None, "git"})
            or parsed.password is not None
        ):
            _invalid()
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return _validate_repository_name(path)


def _discover_repository(repository: Path) -> str:
    return _github_repository_from_remote(_git(repository, "config", "--get", "remote.origin.url"))


def _discover_default_branch(repository: Path) -> str:
    reference = _git(repository, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    prefix = "origin/"
    if not reference.startswith(prefix):
        _invalid()
    return _validate_branch(reference.removeprefix(prefix))


def _config(identity: str) -> bytes:
    return f'''version: 1
repository:
  path: "."
  backend: auto
signing:
  environment: production
  timeoutSeconds: 120
verification:
  identity: "{identity}"
  issuer: "https://token.actions.githubusercontent.com"
  environment: production
  offline: true
policy:
  path: ".attest/policy.yaml"
storage:
  backend: git-ref
  directory: ".attest/bundles"
  fallbackDirectory: ".attest/fallback"
  git:
    remote: origin
    timeoutSeconds: 120
'''.encode()


def _policy(identity: str, default_branch: str) -> bytes:
    return f'''version: 1
policies:
  - id: ATTEST-DEFAULT-001
    description: "Require trusted signed provenance and independent human review"
    match:
      branches: ["{default_branch}"]
      paths: ["**"]
    require:
      attestation: true
      environment:
        trusted: true
      signer:
        issuer: "https://token.actions.githubusercontent.com"
        identity: "{identity}"
      transparencyLog: true
      review:
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
    onViolation: block
'''.encode()


def _workflow(checkout_ref: str, action_ref: str) -> bytes:
    return f"""name: attest

on:
  pull_request:

permissions:
  contents: write
  id-token: write
  pull-requests: read
  checks: read

jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - uses: {checkout_ref}
        with:
          fetch-depth: 0
      - uses: {action_ref}
        env:
          GITHUB_TOKEN: ${{{{ github.token }}}}
        with:
          mode: run
          policy: .attest/policy.yaml
          push-attestation: "true"
          fail-on-violation: "true"
""".encode()


def _safe_repository(value: Path) -> Path:
    try:
        if value.is_symlink() or not value.is_dir():
            _invalid()
        return value.resolve(strict=True)
    except CliError:
        raise
    except (OSError, RuntimeError):
        _invalid()


def _ensure_directory(path: Path, created: list[Path]) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_dir():
            raise cli_error("ERR-CONFIG-004")
        return
    path.mkdir(mode=0o700)
    created.append(path)


def initialize(
    *,
    repository: Path,
    github_repository: str | None,
    default_branch: str | None,
    checkout_ref: str,
    action_ref: str,
) -> InitData:
    """Create the exact three F-10 files after an all-target preflight."""
    root = _safe_repository(repository)
    repository_name = (
        _discover_repository(root)
        if github_repository is None
        else _validate_repository_name(github_repository)
    )
    branch = (
        _discover_default_branch(root)
        if default_branch is None
        else _validate_branch(default_branch)
    )
    checkout = _validate_action_ref(checkout_ref)
    action = _validate_action_ref(action_ref)
    identity = (
        f"https://github.com/{repository_name}/.github/workflows/attest.yml@refs/heads/{branch}"
    )
    targets = (
        root / ".attest" / "config.yaml",
        root / ".attest" / "policy.yaml",
        root / ".github" / "workflows" / "attest.yml",
    )
    if any(path.exists() or path.is_symlink() for path in targets):
        raise cli_error("ERR-CONFIG-004")

    created_directories: list[Path] = []
    created_files: list[Path] = []
    try:
        _ensure_directory(root / ".attest", created_directories)
        _ensure_directory(root / ".github", created_directories)
        _ensure_directory(root / ".github" / "workflows", created_directories)
        contents = (_config(identity), _policy(identity, branch), _workflow(checkout, action))
        for target, content in zip(targets, contents, strict=True):
            write_atomic(target, content, overwrite=False)
            created_files.append(target)
    except CliError:
        for path in reversed(created_files):
            with suppress(OSError):
                path.unlink()
        for path in reversed(created_directories):
            with suppress(OSError):
                path.rmdir()
        raise
    except OSError:
        for path in reversed(created_files):
            with suppress(OSError):
                path.unlink()
        for path in reversed(created_directories):
            with suppress(OSError):
                path.rmdir()
        raise cli_error("ERR-CONFIG-004") from None
    return InitData(created_paths=tuple(str(path) for path in targets), workflow_identity=identity)
