"""F-11 candidate image supply-chain contract tests."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML lacks typing metadata.

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CONTEXT_SCRIPT: Final[Path] = REPOSITORY_ROOT / "scripts/prepare_action_context.py"
SCAN_CHECK_SCRIPT: Final[Path] = REPOSITORY_ROOT / "scripts/check_action_scan.py"
CANDIDATE_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/action-candidate.yml"
ACTION_MANIFEST: Final[Path] = REPOSITORY_ROOT / "action/action.yml"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    "docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc",
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
    "docker/setup-qemu-action@99012661954931238ded8c8b007157a8430204e1",
}
REVIEWED_IMAGE: Final[str] = (
    "docker://ghcr.io/parth2412/attest@"
    "sha256:50ff206da7d26341776c954bb190005f1e6d10369b29fbbbe68619ce8d7ad627"
)


def _run_context(
    repository: Path, destination: Path, evidence: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CONTEXT_SCRIPT),
            str(destination),
            "--repository-root",
            str(repository),
            "--manifest-output",
            str(evidence / "manifest.json"),
            "--digest-output",
            str(evidence / "digest.txt"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _fixture_repository(root: Path) -> None:
    files = {
        "pyproject.toml": "[tool.uv.workspace]\nmembers = ['packages/*']\n",
        "uv.lock": "version = 1\n",
        "release/packages.toml": (
            "[release]\nversion = '0.1.0'\ndistributions = ['attest-core']\n"
        ),
        "action/Dockerfile": "FROM scratch\nCOPY packages/attest-core /package\n",
        "action/entrypoint.py": "raise SystemExit(0)\n",
        "action/action.yml": "runs:\n  image: docker://example.invalid/mutable:latest\n",
        "packages/attest-core/LICENSE": "licence\n",
        "packages/attest-core/README.md": "readme\n",
        "packages/attest-core/pyproject.toml": "[project]\nname = 'attest-core'\n",
        "packages/attest-core/src/attest_core/__init__.py": "VERSION = '0.1.0'\n",
        "packages/attest-core/tests/test_ignored.py": "raise RuntimeError\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, timeout=30)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, timeout=30)


def _uses(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "uses" and isinstance(child, str):
                found.add(child)
            found.update(_uses(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_uses(child))
    return found


def _run_scan_check(
    tmp_path: Path, results: list[dict[str, Any]]
) -> subprocess.CompletedProcess[str]:
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps({"SchemaVersion": 2, "Results": results}),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(SCAN_CHECK_SCRIPT), str(report)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-150")
def test_action_context_is_closed_deterministic_and_excludes_manifest(tmp_path: Path) -> None:
    """REQ-F11-150: candidate bytes come only from the enumerated context."""
    repository = tmp_path / "repository"
    _fixture_repository(repository)
    first = _run_context(repository, tmp_path / "context-one", tmp_path / "evidence-one")
    assert first.returncode == 0, first.stderr
    first_digest = (tmp_path / "evidence-one/digest.txt").read_text(encoding="utf-8")
    first_manifest = json.loads(
        (tmp_path / "evidence-one/manifest.json").read_text(encoding="utf-8")
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}\n", first_digest)
    assert first_manifest["contextDigest"] == first_digest.strip()
    assert [entry["path"] for entry in first_manifest["files"]] == [
        "action/Dockerfile",
        "action/entrypoint.py",
        "packages/attest-core/LICENSE",
        "packages/attest-core/README.md",
        "packages/attest-core/pyproject.toml",
        "packages/attest-core/src/attest_core/__init__.py",
        "pyproject.toml",
        "uv.lock",
    ]
    assert not (tmp_path / "context-one/action/action.yml").exists()
    assert not (tmp_path / "context-one/packages/attest-core/tests").exists()

    (repository / "action/action.yml").write_text("reviewed digest pin\n", encoding="utf-8")
    second = _run_context(repository, tmp_path / "context-two", tmp_path / "evidence-two")
    assert second.returncode == 0, second.stderr
    assert (tmp_path / "evidence-two/digest.txt").read_text(encoding="utf-8") == first_digest

    (repository / "packages/attest-core/src/attest_core/__init__.py").write_text(
        "VERSION = 'changed'\n", encoding="utf-8"
    )
    third = _run_context(repository, tmp_path / "context-three", tmp_path / "evidence-three")
    assert third.returncode == 0, third.stderr
    assert (tmp_path / "evidence-three/digest.txt").read_text(encoding="utf-8") != first_digest


@pytest.mark.ac("AC-F11-150")
def test_action_context_rejects_non_regular_source(tmp_path: Path) -> None:
    """REQ-F11-150: context staging fails closed on filesystem indirection."""
    repository = tmp_path / "repository"
    _fixture_repository(repository)
    source = repository / "packages/attest-core/src/attest_core/__init__.py"
    source.unlink()
    source.symlink_to(repository / "action/entrypoint.py")
    result = _run_context(repository, tmp_path / "context", tmp_path / "evidence")
    assert result.returncode == 1
    assert "context source must be a regular file" in result.stderr
    assert not (tmp_path / "context").exists()


@pytest.mark.ac("AC-F11-150")
def test_action_context_will_not_replace_an_unowned_directory(tmp_path: Path) -> None:
    """REQ-F11-150: staging never recursively replaces an unrelated directory."""
    repository = tmp_path / "repository"
    _fixture_repository(repository)
    destination = tmp_path / "context"
    destination.mkdir()
    (destination / "unrelated.txt").write_text("preserve\n", encoding="utf-8")
    result = _run_context(repository, destination, tmp_path / "evidence")
    assert result.returncode == 1
    assert "not a prior closed Action context" in result.stderr
    assert (destination / "unrelated.txt").read_text(encoding="utf-8") == "preserve\n"


@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-180")
def test_candidate_workflow_has_closed_supply_chain() -> None:
    """REQ-F11-150: the candidate workflow proves every pre-publication artifact property."""
    workflow: dict[Any, Any] = yaml.safe_load(CANDIDATE_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get("on")
    if triggers is None:
        triggers = workflow.get(True)
    assert isinstance(triggers, dict)
    assert triggers["push"]["branches"] == ["dev"]
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False

    jobs = workflow["jobs"]
    assert set(jobs) == {"validate", "build", "scan", "attest"}
    assert jobs["build"]["needs"] == "validate"
    assert jobs["scan"]["needs"] == "build"
    assert jobs["attest"]["needs"] == ["build", "scan"]
    release_gate = jobs["validate"]["steps"][-1]["run"]
    for required_command in (
        "uv run ruff check .",
        "uv run python scripts/run_mypy.py",
        "uv run pytest",
        "uv run python scripts/run_test_group.py vectors F-01 F-02",
        "uv run python scripts/run_test_group.py adversarial F-08",
        "uv run --no-project python scripts/validate_release_artifacts.py",
        "uv run --no-project python scripts/prepare_action_context.py",
        "uv run pytest action/tests/test_container.py -m container",
        "uv run python scripts/check_traceability.py",
        "uv run bandit",
        "uv run pip-audit",
    ):
        assert required_command in release_gate
    assert jobs["build"]["permissions"] == {"contents": "read", "packages": "write"}
    assert jobs["scan"]["strategy"]["matrix"]["include"] == [
        {"platform": "linux/amd64", "slug": "linux-amd64"},
        {"platform": "linux/arm64", "slug": "linux-arm64"},
    ]
    assert "scripts/check_action_scan.py" in triggers["push"]["paths"]
    assert "org.opencontainers.image.version=0.1.2-candidate" in str(jobs["build"]["steps"])
    scan_steps = jobs["scan"]["steps"]
    upload_index = next(
        index
        for index, step in enumerate(scan_steps)
        if step.get("name") == "Upload platform scan evidence"
    )
    gate_index = next(
        index
        for index, step in enumerate(scan_steps)
        if step.get("name") == "Enforce the candidate security gate"
    )
    assert upload_index < gate_index
    assert scan_steps[gate_index]["run"] == (
        'python3 scripts/check_action_scan.py "trivy-${{ matrix.slug }}.json"'
    )
    assert jobs["attest"]["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }

    build_step = next(step for step in jobs["build"]["steps"] if step.get("id") == "build")
    assert build_step["with"]["context"] == "${{ runner.temp }}/attest-action-context"
    assert (
        build_step["with"]["file"] == "${{ runner.temp }}/attest-action-context/action/Dockerfile"
    )
    assert build_step["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert build_step["with"]["push"] is True
    assert build_step["with"]["sbom"] is True
    assert build_step["with"]["provenance"] == "mode=max"

    attest_step = next(step for step in jobs["attest"]["steps"] if step.get("id") == "attest")
    assert attest_step["with"] == {
        "subject-name": "ghcr.io/parth2412/attest",
        "subject-digest": "${{ needs.build.outputs.image-digest }}",
        "push-to-registry": True,
    }

    action_references = _uses(workflow)
    assert action_references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in action_references)


@pytest.mark.ac("AC-F11-010")
def test_public_action_manifest_pins_the_reviewed_candidate() -> None:
    """REQ-F11-010: the closed public Action executes only the reviewed immutable image."""
    manifest: dict[str, Any] = yaml.safe_load(ACTION_MANIFEST.read_text(encoding="utf-8"))
    assert manifest == {
        "name": "attest",
        "description": "Verify AI-authorship provenance and enforce human-review policy",
        "inputs": {
            "mode": {
                "description": "Operation to execute: run, verify, or gate.",
                "required": False,
                "default": "run",
            },
            "policy": {
                "description": "Repository-relative policy YAML path for run or gate.",
                "required": False,
            },
            "bundle": {
                "description": "Repository-relative Bundle JSON path for verify or gate.",
                "required": False,
            },
            "push-attestation": {
                "description": "Whether run publishes to the configured durable store.",
                "required": False,
            },
            "fail-on-violation": {
                "description": "Whether a policy violation fails run or gate.",
                "required": False,
            },
        },
        "outputs": {
            "changeset-digest": {"description": "Verified lowercase SHA-256 ChangeSet Digest."},
            "attestation-ref": {
                "description": "Published attestation reference or validated Bundle path."
            },
            "decision": {"description": "Verified policy decision or verification result."},
            "log-index": {"description": "Verified Rekor log index when present."},
        },
        "runs": {
            "using": "docker",
            "image": REVIEWED_IMAGE,
            "args": [
                "--mode",
                "${{ inputs.mode }}",
                "--policy",
                "${{ inputs.policy }}",
                "--bundle",
                "${{ inputs.bundle }}",
                "--push-attestation",
                "${{ inputs.push-attestation }}",
                "--fail-on-violation",
                "${{ inputs.fail-on-violation }}",
            ],
        },
    }
    assert "github." not in ACTION_MANIFEST.read_text(encoding="utf-8")
    assert re.fullmatch(r"docker://ghcr\.io/parth2412/attest@sha256:[0-9a-f]{64}", REVIEWED_IMAGE)


@pytest.mark.ac("AC-F11-150")
@pytest.mark.parametrize(
    ("results", "expected_exit", "expected_fragment"),
    [
        ([], 0, "security gate passed"),
        (
            [
                {
                    "Target": "candidate",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-UNFIXED-HIGH",
                            "PkgName": "base-package",
                            "InstalledVersion": "1",
                            "FixedVersion": "",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
            0,
            "unfixed high=1",
        ),
        (
            [
                {
                    "Target": "candidate",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-FIXABLE-HIGH",
                            "PkgName": "base-package",
                            "InstalledVersion": "1",
                            "FixedVersion": "2",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
            1,
            "fixable high=1",
        ),
        (
            [
                {
                    "Target": "candidate",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-UNFIXED-CRITICAL",
                            "PkgName": "base-package",
                            "InstalledVersion": "1",
                            "Severity": "CRITICAL",
                        }
                    ],
                }
            ],
            1,
            "critical=1",
        ),
        (
            [{"Target": "candidate", "Secrets": [{"RuleID": "private-key"}]}],
            1,
            "secrets=1",
        ),
    ],
)
def test_candidate_scan_gate_is_fail_closed(
    tmp_path: Path,
    results: list[dict[str, Any]],
    expected_exit: int,
    expected_fragment: str,
) -> None:
    """REQ-F11-150: candidates cannot attest known actionable security findings."""
    completed = _run_scan_check(tmp_path, results)
    assert completed.returncode == expected_exit
    assert expected_fragment in completed.stdout + completed.stderr


@pytest.mark.ac("AC-F11-150")
def test_candidate_scan_gate_rejects_malformed_report(tmp_path: Path) -> None:
    """REQ-F11-150: missing or malformed scanner output cannot become an attested candidate."""
    report = tmp_path / "trivy.json"
    report.write_text('{"SchemaVersion": 2, "Results": {}}', encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCAN_CHECK_SCRIPT), str(report)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 2
    assert completed.stderr == "invalid Trivy report\n"


@pytest.mark.ac("AC-F11-150")
def test_root_dockerignore_excludes_every_non_runtime_tree() -> None:
    """REQ-F11-150: ad-hoc root builds retain the candidate context boundary."""
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "!action/action.yml" not in dockerignore
    assert "!packages/attest-export" not in dockerignore
    assert "!packages/attest-core/tests" not in dockerignore
    assert "!packages/attest-core/mutants" not in dockerignore
    for package in (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-cli",
    ):
        assert f"!packages/{package}/src/**" in dockerignore
        for name in ("LICENSE", "README.md", "pyproject.toml"):
            assert f"!packages/{package}/{name}" in dockerignore
