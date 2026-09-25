"""F-11 hosted Action cold-start measurement contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML lacks typing metadata.

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PERFORMANCE_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/action-performance.yml"
PERFORMANCE_CONFIG: Final[Path] = REPOSITORY_ROOT / "action/performance/config.yaml"
PERFORMANCE_POLICY: Final[Path] = REPOSITORY_ROOT / "action/performance/policy.yaml"
SUMMARIZER: Final[Path] = REPOSITORY_ROOT / "scripts/summarize_action_performance.py"
ACTION_SHA: Final[str] = "a" * 40
IMAGE_DIGEST: Final[str] = "sha256:7a38031c42fdb83398ed267937e8642f48964b169554e6792a5acbc4bcbcc745"
ACTION_REFERENCE: Final[str] = "./action"
ACTION_STEP: Final[str] = "Measure exact merged Action"
PULL_STEP: Final[str] = f"Pull ghcr.io/parth2412/attest@{IMAGE_DIGEST}"
WORKFLOW_IDENTITY: Final[str] = (
    "https://github.com/Parth2412/attest/.github/workflows/action-performance.yml@refs/heads/main"
)
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ACTION_REFERENCE,
}


def _workflow() -> dict[Any, Any]:
    workflow = yaml.safe_load(PERFORMANCE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _triggers(workflow: dict[Any, Any]) -> dict[Any, Any]:
    triggers = workflow.get("on")
    if triggers is None:
        triggers = workflow.get(True)
    assert isinstance(triggers, dict)
    return triggers


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


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


@pytest.mark.ac("AC-F11-100")
def test_performance_workflow_runs_twenty_independent_cold_start_jobs() -> None:
    """REQ-F11-100: the immutable Action is measured in 20 hosted jobs on main."""
    workflow = _workflow()
    assert workflow["name"] == "measure Action cold start"
    assert _triggers(workflow) == {
        "push": {
            "branches": ["main"],
            "paths": [
                ".github/workflows/action-performance.yml",
                "action/**",
                "packages/**",
                "pyproject.toml",
                "scripts/summarize_action_performance.py",
                "uv.lock",
            ],
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "action-performance-${{ github.sha }}",
        "cancel-in-progress": False,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {"measure", "summarize"}
    measure = jobs["measure"]
    assert measure["name"] == "measure (${{ matrix.sample }})"
    assert measure["runs-on"] == "ubuntu-latest"
    assert measure["permissions"] == {"contents": "read", "id-token": "write"}
    assert measure["strategy"] == {
        "fail-fast": False,
        "max-parallel": 20,
        "matrix": {"sample": list(range(1, 21))},
    }
    assert measure["timeout-minutes"] == 10

    checkout = next(
        step for step in measure["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    measured = _step(measure, ACTION_STEP)
    assert measured["uses"] == ACTION_REFERENCE
    assert measured["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    assert measured["with"] == {
        "mode": "run",
        "policy": "action/performance/policy.yaml",
        "push-attestation": "false",
        "fail-on-violation": "true",
    }

    summarize = jobs["summarize"]
    assert summarize["needs"] == "measure"
    assert summarize["if"] == "${{ always() }}"
    assert summarize["permissions"] == {"actions": "read", "contents": "read"}
    assert summarize["runs-on"] == "ubuntu-latest"
    assert summarize["timeout-minutes"] == 10

    references = _uses(workflow)
    assert references == EXPECTED_ACTIONS
    assert all(
        reference == ACTION_REFERENCE or FULL_SHA.fullmatch(reference) for reference in references
    )
    rendered = PERFORMANCE_WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in rendered
    assert "pull_request_target:" not in rendered
    assert "workflow_dispatch:" not in rendered


@pytest.mark.ac("AC-F11-100")
def test_performance_fixture_is_frozen_to_staging_and_exact_identity() -> None:
    """REQ-F11-100: all observations use one closed staging fixture."""
    config = yaml.safe_load(PERFORMANCE_CONFIG.read_text(encoding="utf-8"))
    policy = yaml.safe_load(PERFORMANCE_POLICY.read_text(encoding="utf-8"))
    assert config == {
        "version": 1,
        "repository": {"path": ".", "backend": "auto"},
        "signing": {"environment": "staging", "timeoutSeconds": 120},
        "verification": {
            "identity": WORKFLOW_IDENTITY,
            "issuer": "https://token.actions.githubusercontent.com",
            "environment": "staging",
            "offline": True,
        },
        "policy": {"path": "action/performance/policy.yaml"},
        "storage": {
            "backend": "filesystem",
            "directory": ".attest/performance-bundles",
            "fallbackDirectory": ".attest/performance-fallback",
        },
    }
    assert policy == {
        "version": 1,
        "policies": [
            {
                "id": "ATTEST-PERFORMANCE-001",
                "description": "Require the exact hosted performance workflow identity",
                "match": {"branches": ["main"], "paths": ["**"]},
                "require": {
                    "attestation": True,
                    "environment": {"trusted": True},
                    "signer": {
                        "issuer": "https://token.actions.githubusercontent.com",
                        "identity": WORKFLOW_IDENTITY,
                    },
                    "transparencyLog": True,
                },
                "onViolation": "block",
            }
        ],
    }

    workflow = _workflow()
    commands = "\n".join(
        step.get("run", "")
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step, dict)
    )
    assert "cp action/performance/config.yaml .attest/config.yaml" in commands
    assert IMAGE_DIGEST in commands
    assert '--expected-action-sha "${GITHUB_SHA}"' in commands
    assert f'--expected-image-digest "{IMAGE_DIGEST}"' in commands
    assert "--expected-samples 20" in commands
    assert "--threshold-seconds 15" in commands
    assert "--require-run-attempt 1" in commands


def _timestamp(seconds: float) -> str:
    value = datetime(2026, 9, 24, 12, 0, tzinfo=UTC) + timedelta(seconds=seconds)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _jobs_payload(*, samples: int = 20, total_seconds: float = 12.0) -> dict[str, object]:
    jobs: list[dict[str, object]] = []
    for sample in range(1, samples + 1):
        pull_seconds = 4.0
        action_seconds = total_seconds - pull_seconds
        jobs.append(
            {
                "id": 10_000 + sample,
                "name": f"measure ({sample})",
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "success",
                "html_url": (
                    f"https://github.com/Parth2412/attest/actions/runs/42/job/{10_000 + sample}"
                ),
                "labels": ["ubuntu-latest"],
                "runner_name": f"GitHub Actions {sample}",
                "runner_group_name": "GitHub Actions",
                "steps": [
                    {
                        "name": PULL_STEP,
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": _timestamp(0),
                        "completed_at": _timestamp(pull_seconds),
                    },
                    {
                        "name": "Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": _timestamp(4),
                        "completed_at": _timestamp(6),
                    },
                    {
                        "name": ACTION_STEP,
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": _timestamp(6),
                        "completed_at": _timestamp(6 + action_seconds),
                    },
                ],
            }
        )
    return {"total_count": samples + 1, "jobs": jobs}


def _write_metadata(directory: Path, *, samples: int = 20) -> None:
    directory.mkdir()
    config_sha256 = hashlib.sha256(PERFORMANCE_CONFIG.read_bytes()).hexdigest()
    policy_sha256 = hashlib.sha256(PERFORMANCE_POLICY.read_bytes()).hexdigest()
    for sample in range(1, samples + 1):
        payload = {
            "schemaVersion": 1,
            "sample": sample,
            "runnerEnvironment": "github-hosted",
            "runnerArchitecture": "X64",
            "runnerName": f"GitHub Actions {sample}",
            "imageOS": "ubuntu24",
            "imageVersion": "20260921.1",
            "headSha": "a" * 40,
            "workflowRef": (
                "Parth2412/attest/.github/workflows/action-performance.yml@refs/heads/main"
            ),
            "actionSha": ACTION_SHA,
            "imageDigest": IMAGE_DIGEST,
            "configSha256": config_sha256,
            "policySha256": policy_sha256,
            "actionConclusion": "success",
        }
        (directory / f"sample-{sample:02}.json").write_text(json.dumps(payload), encoding="utf-8")


def _run_summarizer(
    tmp_path: Path,
    *,
    samples: int = 20,
    total_seconds: float = 12.0,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    jobs_path = tmp_path / "jobs.json"
    metadata = tmp_path / "metadata"
    output = tmp_path / "summary.json"
    jobs_path.write_text(
        json.dumps(_jobs_payload(samples=samples, total_seconds=total_seconds)),
        encoding="utf-8",
    )
    _write_metadata(metadata, samples=samples)
    result = subprocess.run(
        [
            sys.executable,
            str(SUMMARIZER),
            "--jobs",
            str(jobs_path),
            "--metadata-directory",
            str(metadata),
            "--config",
            str(PERFORMANCE_CONFIG),
            "--policy",
            str(PERFORMANCE_POLICY),
            "--output",
            str(output),
            "--repository",
            "Parth2412/attest",
            "--run-id",
            "42",
            "--run-attempt",
            "1",
            "--head-sha",
            "a" * 40,
            "--expected-action-sha",
            ACTION_SHA,
            "--expected-image-digest",
            IMAGE_DIGEST,
            "--expected-samples",
            "20",
            "--threshold-seconds",
            "15",
            "--require-run-attempt",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, output


@pytest.mark.ac("AC-F11-100")
def test_summarizer_adds_pull_and_action_time_but_excludes_checkout(tmp_path: Path) -> None:
    """REQ-F11-100: the retained metric includes pull/runtime but excludes checkout."""
    result, output = _run_summarizer(tmp_path)
    assert result.returncode == 0, result.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["schemaVersion"] == 1
    assert summary["requirement"] == "REQ-F11-100"
    assert summary["acceptanceCriterion"] == "AC-F11-100"
    assert summary["action"] == {"commit": ACTION_SHA, "imageDigest": IMAGE_DIGEST}
    assert summary["metric"] == {
        "definition": "image pull plus Action execution; checkout excluded",
        "sampleCount": 20,
        "thresholdSecondsExclusive": 15.0,
        "nearestRankP50Seconds": 12.0,
        "nearestRankP95Seconds": 12.0,
        "sortedSeconds": [12.0] * 20,
        "passed": True,
    }
    first = summary["measurements"][0]
    assert first["sample"] == 1
    assert first["imagePullSeconds"] == 4.0
    assert first["actionExecutionSeconds"] == 8.0
    assert first["measuredSeconds"] == 12.0
    assert first["runnerImage"] == {"os": "ubuntu24", "version": "20260921.1"}


@pytest.mark.ac("AC-F11-100")
@pytest.mark.parametrize(
    ("samples", "total_seconds", "message"),
    [(19, 12.0, "expected exactly 20 measurements"), (20, 15.0, "p95 must be below 15")],
)
def test_summarizer_fails_closed_on_incomplete_or_slow_evidence(
    tmp_path: Path, samples: int, total_seconds: float, message: str
) -> None:
    """REQ-F11-100: incomplete or threshold-equal evidence cannot pass the gate."""
    result, output = _run_summarizer(tmp_path, samples=samples, total_seconds=total_seconds)
    assert result.returncode != 0
    assert message in result.stderr
    assert output.exists()
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["metric"]["passed"] is False
