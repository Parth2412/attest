"""F-10 exact secure project initialisation tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from attest_cli.errors import CliError, cli_error
from attest_cli.initialize import initialize
from attest_cli.safe_io import write_atomic

CHECKOUT = "actions/checkout@" + "1" * 40
ACTION = "parth2412/attest/action@" + "2" * 40
IDENTITY = "https://github.com/example/repo/.github/workflows/attest.yml@refs/heads/main"

EXPECTED_CONFIG = f"""version: 1
repository:
  path: "."
  backend: auto
signing:
  environment: production
  timeoutSeconds: 120
verification:
  identity: "{IDENTITY}"
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
""".encode()

EXPECTED_POLICY = f"""version: 1
policies:
  - id: ATTEST-DEFAULT-001
    description: "Require trusted signed provenance and independent human review"
    match:
      branches: ["main"]
      paths: ["**"]
    require:
      attestation: true
      environment:
        trusted: true
      signer:
        issuer: "https://token.actions.githubusercontent.com"
        identity: "{IDENTITY}"
      transparencyLog: true
      review:
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
    onViolation: block
""".encode()

EXPECTED_WORKFLOW = f"""name: attest

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
      - uses: {CHECKOUT}
        with:
          fetch-depth: 0
      - uses: {ACTION}
        env:
          GITHUB_TOKEN: ${{{{ github.token }}}}
        with:
          mode: run
          policy: .attest/policy.yaml
          push-attestation: "true"
          fail-on-violation: "true"
""".encode()


@pytest.mark.ac("AC-F10-190")
def test_init_writes_the_three_exact_golden_files(tmp_path: Path) -> None:
    result = initialize(
        repository=tmp_path,
        github_repository="example/repo",
        default_branch="main",
        checkout_ref=CHECKOUT,
        action_ref=ACTION,
    )

    assert result.workflow_identity == IDENTITY
    assert result.created_paths == (
        str(tmp_path / ".attest" / "config.yaml"),
        str(tmp_path / ".attest" / "policy.yaml"),
        str(tmp_path / ".github" / "workflows" / "attest.yml"),
    )
    assert (tmp_path / ".attest" / "config.yaml").read_bytes() == EXPECTED_CONFIG
    assert (tmp_path / ".attest" / "policy.yaml").read_bytes() == EXPECTED_POLICY
    assert (tmp_path / ".github" / "workflows" / "attest.yml").read_bytes() == EXPECTED_WORKFLOW
    assert b"pull_request_target" not in EXPECTED_WORKFLOW


@pytest.mark.ac("AC-F10-190")
def test_any_existing_target_leaves_all_targets_unchanged(tmp_path: Path) -> None:
    existing = tmp_path / ".github" / "workflows" / "attest.yml"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")

    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        initialize(
            repository=tmp_path,
            github_repository="example/repo",
            default_branch="main",
            checkout_ref=CHECKOUT,
            action_ref=ACTION,
        )

    assert existing.read_bytes() == b"existing"
    assert not (tmp_path / ".attest").exists()


@pytest.mark.ac("AC-F10-190")
@pytest.mark.parametrize(
    "reference",
    [
        "actions/checkout@main",
        "actions/checkout@" + "A" * 40,
        "actions/checkout@" + "1" * 39,
        "https://github.com/actions/checkout@" + "1" * 40,
        "actions//checkout@" + "1" * 40,
    ],
)
def test_init_rejects_every_mutable_or_malformed_action_ref(
    tmp_path: Path,
    reference: str,
) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        initialize(
            repository=tmp_path,
            github_repository="example/repo",
            default_branch="main",
            checkout_ref=reference,
            action_ref=ACTION,
        )


@pytest.mark.ac("AC-F10-190")
def test_init_discovers_unambiguous_github_remote_and_default_branch(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", "git@github.com:example/repo.git"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main",
        ],
        check=True,
        capture_output=True,
    )

    result = initialize(
        repository=tmp_path,
        github_repository=None,
        default_branch=None,
        checkout_ref=CHECKOUT,
        action_ref=ACTION,
    )

    assert result.workflow_identity == IDENTITY


@pytest.mark.ac("AC-F10-160")
@pytest.mark.ac("AC-F10-190")
@pytest.mark.parametrize("failure", [cli_error("ERR-CONFIG-004"), OSError()])
def test_init_rolls_back_every_created_file_and_only_created_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    github = tmp_path / ".github"
    github.mkdir()
    marker = github / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")
    calls = 0

    def fail_second_write(path: Path, content: bytes, *, overwrite: bool) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure
        write_atomic(path, content, overwrite=overwrite)

    monkeypatch.setattr("attest_cli.initialize.write_atomic", fail_second_write)
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        initialize(
            repository=tmp_path,
            github_repository="example/repo",
            default_branch="main",
            checkout_ref=CHECKOUT,
            action_ref=ACTION,
        )

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not (tmp_path / ".attest").exists()
    assert not (github / "workflows").exists()


@pytest.mark.ac("AC-F10-190")
@pytest.mark.parametrize(
    "remote",
    [
        "https://gitlab.com/example/repo.git",
        "https://user:password@github.com/example/repo.git",
        "https://github.com/example/repo.git?ref=main",
        "file:///tmp/example/repo",
        "git@github.com:example/../repo.git",
    ],
)
def test_init_rejects_ambiguous_or_non_github_discovery_remote(
    tmp_path: Path,
    remote: str,
) -> None:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", remote],
        check=True,
        capture_output=True,
    )

    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        initialize(
            repository=tmp_path,
            github_repository=None,
            default_branch="main",
            checkout_ref=CHECKOUT,
            action_ref=ACTION,
        )


@pytest.mark.ac("AC-F10-190")
@pytest.mark.parametrize(
    "branch",
    [
        "",
        ".hidden",
        "-main",
        "/main",
        "main/",
        "main.",
        "main.lock",
        "main//next",
        "main..next",
        "x@{y",
        "feature/.hidden",
        "foo.lock/bar",
    ],
)
def test_init_rejects_unsafe_default_branch(tmp_path: Path, branch: str) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        initialize(
            repository=tmp_path,
            github_repository="example/repo",
            default_branch=branch,
            checkout_ref=CHECKOUT,
            action_ref=ACTION,
        )


@pytest.mark.ac("AC-F10-190")
def test_init_rejects_non_directory_or_symlink_repository(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.write_text("content", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path, target_is_directory=True)

    for repository in (regular, linked):
        with pytest.raises(CliError, match="ERR-CONFIG-001"):
            initialize(
                repository=repository,
                github_repository="example/repo",
                default_branch="main",
                checkout_ref=CHECKOUT,
                action_ref=ACTION,
            )
