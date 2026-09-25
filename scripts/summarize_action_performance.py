"""Validate and summarize the retained F-11 hosted Action measurements."""

# ruff: noqa: TRY003  # Evidence-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NoReturn

IMAGE_DIGEST: Final[str] = "sha256:7a38031c42fdb83398ed267937e8642f48964b169554e6792a5acbc4bcbcc745"
ACTION_STEP: Final[str] = "Measure exact merged Action"
PULL_STEP: Final[str] = f"Pull ghcr.io/parth2412/attest@{IMAGE_DIGEST}"
WORKFLOW_REF: Final[str] = (
    "Parth2412/attest/.github/workflows/action-performance.yml@refs/heads/main"
)
OID: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}\Z")
DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
JOB_NAME: Final[re.Pattern[str]] = re.compile(r"measure \(([1-9]|1[0-9]|20)\)\Z")
METADATA_NAME: Final[re.Pattern[str]] = re.compile(r"sample-([0-9]{2})\.json\Z")


class PerformanceEvidenceError(ValueError):
    """The hosted-runner evidence does not satisfy the frozen contract."""


def _fail(message: str) -> NoReturn:
    raise PerformanceEvidenceError(message)


def _json(path: Path) -> object:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 16 * 1024 * 1024:
            _fail(f"invalid evidence size: {path.name}")
        return json.loads(raw.decode("utf-8", errors="strict"))
    except PerformanceEvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PerformanceEvidenceError(f"invalid JSON evidence: {path.name}") from error


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(f"{label} must be a JSON object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"{label} must be a JSON array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    return value


def _timestamp(value: object, label: str) -> datetime:
    rendered = _string(value, label)
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as error:
        raise PerformanceEvidenceError(f"{label} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _fail(f"{label} must be UTC")
    return parsed


def _duration(step: dict[str, object], label: str) -> tuple[float, str, str]:
    if step.get("status") != "completed" or step.get("conclusion") != "success":
        _fail(f"{label} did not complete successfully")
    started_raw = _string(step.get("started_at"), f"{label} started_at")
    completed_raw = _string(step.get("completed_at"), f"{label} completed_at")
    started = _timestamp(started_raw, f"{label} started_at")
    completed = _timestamp(completed_raw, f"{label} completed_at")
    seconds = round((completed - started).total_seconds(), 3)
    if seconds < 0:
        _fail(f"{label} has a negative duration")
    return seconds, started_raw, completed_raw


def _sha256(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise PerformanceEvidenceError(f"cannot read frozen fixture: {path}") from error
    if not raw:
        _fail(f"frozen fixture is empty: {path}")
    return hashlib.sha256(raw).hexdigest()


def _metadata(
    directory: Path,
    *,
    expected_samples: int,
    head_sha: str,
    action_sha: str,
    image_digest: str,
    config_sha256: str,
    policy_sha256: str,
) -> dict[int, dict[str, object]]:
    try:
        paths = sorted(directory.iterdir())
    except OSError as error:
        raise PerformanceEvidenceError("cannot enumerate runner metadata") from error
    if not paths or len(paths) > expected_samples:
        _fail("runner metadata count is outside the frozen contract")

    records: dict[int, dict[str, object]] = {}
    for path in paths:
        match = METADATA_NAME.fullmatch(path.name)
        if match is None or not path.is_file() or path.is_symlink():
            _fail("runner metadata directory contains an unexpected entry")
        record = _object(_json(path), f"runner metadata {path.name}")
        sample = _integer(record.get("sample"), f"{path.name} sample")
        if sample != int(match.group(1)) or sample in records:
            _fail("runner metadata sample is inconsistent or duplicated")
        expected = {
            "schemaVersion": 1,
            "sample": sample,
            "runnerEnvironment": "github-hosted",
            "headSha": head_sha,
            "workflowRef": WORKFLOW_REF,
            "actionSha": action_sha,
            "imageDigest": image_digest,
            "configSha256": config_sha256,
            "policySha256": policy_sha256,
            "actionConclusion": "success",
        }
        for key, value in expected.items():
            if record.get(key) != value:
                _fail(f"runner metadata {path.name} has an invalid {key}")
        allowed = set(expected) | {
            "runnerArchitecture",
            "runnerName",
            "imageOS",
            "imageVersion",
        }
        if set(record) != allowed:
            _fail(f"runner metadata {path.name} has unexpected fields")
        for key in ("runnerArchitecture", "runnerName", "imageOS", "imageVersion"):
            _string(record.get(key), f"{path.name} {key}")
        records[sample] = record

    if not set(records).issubset(set(range(1, expected_samples + 1))):
        _fail("runner metadata sample is outside the frozen contract")
    return records


def _steps(job: dict[str, object]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for raw_step in _list(job.get("steps"), "job steps"):
        step = _object(raw_step, "job step")
        name = _string(step.get("name"), "job step name")
        if name in indexed:
            _fail(f"duplicate job step: {name}")
        indexed[name] = step
    return indexed


def _measurement(
    job: dict[str, object],
    metadata: dict[int, dict[str, object]],
    *,
    head_sha: str,
) -> dict[str, object] | None:
    name = job.get("name")
    if not isinstance(name, str):
        return None
    match = JOB_NAME.fullmatch(name)
    if match is None:
        return None
    sample = int(match.group(1))
    if (
        job.get("status") != "completed"
        or job.get("conclusion") != "success"
        or job.get("head_sha") != head_sha
        or job.get("labels") != ["ubuntu-latest"]
        or job.get("runner_group_name") != "GitHub Actions"
    ):
        _fail(f"measurement job {sample} has an invalid hosted-runner result")
    job_id = _integer(job.get("id"), f"measurement job {sample} id")
    url = _string(job.get("html_url"), f"measurement job {sample} URL")
    runner_name = _string(job.get("runner_name"), f"measurement job {sample} runner")
    record = metadata.get(sample)
    if record is None or record.get("runnerName") != runner_name:
        _fail(f"measurement job {sample} runner metadata does not match")
    steps = _steps(job)
    pull = steps.get(PULL_STEP)
    action = steps.get(ACTION_STEP)
    if pull is None or action is None:
        _fail(f"measurement job {sample} is missing the exact pull or Action step")
    pull_seconds, pull_started, pull_completed = _duration(pull, f"measurement {sample} pull")
    action_seconds, action_started, action_completed = _duration(
        action, f"measurement {sample} Action"
    )
    measured = round(pull_seconds + action_seconds, 3)
    return {
        "sample": sample,
        "jobId": job_id,
        "jobUrl": url,
        "runnerName": runner_name,
        "runnerArchitecture": record["runnerArchitecture"],
        "runnerImage": {"os": record["imageOS"], "version": record["imageVersion"]},
        "imagePull": {"startedAt": pull_started, "completedAt": pull_completed},
        "actionExecution": {"startedAt": action_started, "completedAt": action_completed},
        "imagePullSeconds": pull_seconds,
        "actionExecutionSeconds": action_seconds,
        "measuredSeconds": measured,
    }


def _nearest_rank(sorted_values: list[float], percentile: float) -> float:
    index = math.ceil(percentile * len(sorted_values)) - 1
    return sorted_values[index]


def _write(path: Path, document: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise PerformanceEvidenceError("cannot write performance summary") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--metadata-directory", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--expected-action-sha", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    parser.add_argument("--expected-samples", type=int, required=True)
    parser.add_argument("--threshold-seconds", type=float, required=True)
    parser.add_argument("--require-run-attempt", type=int, required=True)
    return parser


def _run(arguments: argparse.Namespace) -> None:
    if arguments.repository != "Parth2412/attest":
        _fail("unexpected repository")
    if OID.fullmatch(arguments.head_sha) is None:
        _fail("head SHA must be a full lowercase Git object ID")
    if arguments.expected_action_sha != arguments.head_sha:
        _fail("the measured Action must be the exact workflow head SHA")
    if DIGEST.fullmatch(arguments.expected_image_digest) is None:
        _fail("image digest must be a full lowercase SHA-256 digest")
    if arguments.expected_image_digest != IMAGE_DIGEST:
        _fail("image digest does not match the reviewed candidate")
    if arguments.run_id <= 0 or arguments.expected_samples != 20:
        _fail("run ID and expected sample count must match the frozen contract")
    if arguments.run_attempt != arguments.require_run_attempt or arguments.run_attempt != 1:
        _fail("only the first workflow attempt is valid performance evidence")
    if arguments.threshold_seconds != 15:
        _fail("performance threshold must be exactly 15 seconds")

    config_sha256 = _sha256(arguments.config)
    policy_sha256 = _sha256(arguments.policy)
    metadata = _metadata(
        arguments.metadata_directory,
        expected_samples=arguments.expected_samples,
        head_sha=arguments.head_sha,
        action_sha=arguments.expected_action_sha,
        image_digest=arguments.expected_image_digest,
        config_sha256=config_sha256,
        policy_sha256=policy_sha256,
    )
    jobs_document = _object(_json(arguments.jobs), "workflow jobs response")
    measurements = [
        measurement
        for raw_job in _list(jobs_document.get("jobs"), "workflow jobs")
        if (
            measurement := _measurement(
                _object(raw_job, "workflow job"), metadata, head_sha=arguments.head_sha
            )
        )
        is not None
    ]
    measurements.sort(key=lambda item: _integer(item.get("sample"), "measurement sample"))
    values = [float(item["measuredSeconds"]) for item in measurements]
    complete = len(measurements) == arguments.expected_samples and [
        item["sample"] for item in measurements
    ] == list(range(1, arguments.expected_samples + 1))
    sorted_values = sorted(values)
    p50 = _nearest_rank(sorted_values, 0.50) if sorted_values else None
    p95 = _nearest_rank(sorted_values, 0.95) if sorted_values else None
    passed = complete and p95 is not None and p95 < arguments.threshold_seconds
    summary: dict[str, object] = {
        "schemaVersion": 1,
        "requirement": "REQ-F11-100",
        "acceptanceCriterion": "AC-F11-100",
        "repository": arguments.repository,
        "workflowRun": {
            "id": arguments.run_id,
            "attempt": arguments.run_attempt,
            "url": (f"https://github.com/{arguments.repository}/actions/runs/{arguments.run_id}"),
            "headSha": arguments.head_sha,
        },
        "action": {
            "commit": arguments.expected_action_sha,
            "imageDigest": arguments.expected_image_digest,
        },
        "fixture": {
            "signingEnvironment": "staging",
            "verificationEnvironment": "staging",
            "workflowIdentity": f"https://github.com/{WORKFLOW_REF}",
            "configSha256": config_sha256,
            "policySha256": policy_sha256,
        },
        "metric": {
            "definition": "image pull plus Action execution; checkout excluded",
            "sampleCount": len(measurements),
            "thresholdSecondsExclusive": arguments.threshold_seconds,
            "nearestRankP50Seconds": p50,
            "nearestRankP95Seconds": p95,
            "sortedSeconds": sorted_values,
            "passed": passed,
        },
        "measurements": measurements,
    }
    _write(arguments.output, summary)
    if not complete:
        _fail(f"expected exactly {arguments.expected_samples} measurements")
    if not passed:
        _fail(f"p95 must be below {arguments.threshold_seconds:g}")


def main(argv: Sequence[str] | None = None) -> int:
    """Validate all observations, retain a deterministic summary, and enforce the p95 gate."""
    arguments = _parser().parse_args(argv)
    try:
        _run(arguments)
    except PerformanceEvidenceError as error:
        print(f"action-performance: {error}", file=sys.stderr)
        return 1
    print("action-performance: evidence is complete and the p95 gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
