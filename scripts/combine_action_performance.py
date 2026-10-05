"""Validate three retained Action performance summaries and enforce their combined p95."""

# ruff: noqa: TRY003  # Evidence-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NoReturn

IMAGE_DIGEST: Final[str] = "sha256:91deb4d8b29ad72b6f580060f950538a9ff04ef7c2d4161a9ef2babdbd4e7cf8"
OID: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}\Z")
DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
METRIC_DEFINITION: Final[str] = (
    "Action step including image pull and wrapper/CLI work; checkout excluded"
)


class CombinedPerformanceEvidenceError(ValueError):
    """The retained performance summaries do not satisfy the release contract."""


def _fail(message: str) -> NoReturn:
    raise CombinedPerformanceEvidenceError(message)


def _json(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 16 * 1024 * 1024:
            _fail(f"invalid summary size: {path.name}")
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except CombinedPerformanceEvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CombinedPerformanceEvidenceError(f"invalid JSON summary: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(f"summary must be an object: {path.name}")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be numeric")
    rendered = float(value)
    if not math.isfinite(rendered) or rendered < 0:
        _fail(f"{label} must be finite and non-negative")
    return rendered


def _nearest_rank(sorted_values: list[float], percentile: float) -> float:
    return sorted_values[math.ceil(percentile * len(sorted_values)) - 1]


def _measurements(
    summary: dict[str, object],
    *,
    expected_samples: int,
    run_id: int,
) -> tuple[list[float], set[int]]:
    records = _list(summary.get("measurements"), f"run {run_id} measurements")
    if len(records) != expected_samples:
        _fail(f"run {run_id} must contain exactly {expected_samples} measurements")
    durations: list[float] = []
    job_ids: set[int] = set()
    for expected_sample, raw in enumerate(records, start=1):
        record = _object(raw, f"run {run_id} measurement {expected_sample}")
        if _integer(record.get("sample"), "measurement sample") != expected_sample:
            _fail(f"run {run_id} measurement samples are not complete and ordered")
        job_id = _integer(record.get("jobId"), "measurement job ID")
        if job_id <= 0 or job_id in job_ids:
            _fail(f"run {run_id} measurement job IDs are invalid or duplicated")
        job_ids.add(job_id)
        durations.append(_number(record.get("measuredSeconds"), "measurement duration"))
    return durations, job_ids


def _validate_summary(
    path: Path,
    *,
    repository: str,
    head_sha: str,
    image_digest: str,
    run_id: int,
    expected_samples: int,
    threshold: float,
) -> tuple[list[float], dict[str, object], set[int]]:
    summary = _json(path)
    if (
        summary.get("schemaVersion") != 1
        or summary.get("requirement") != "REQ-F11-100"
        or summary.get("acceptanceCriterion") != "AC-F11-100"
        or summary.get("repository") != repository
    ):
        _fail(f"run {run_id} summary identity is invalid")
    workflow_run = _object(summary.get("workflowRun"), f"run {run_id} workflowRun")
    if workflow_run != {
        "id": run_id,
        "attempt": 1,
        "url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "headSha": head_sha,
    }:
        _fail(f"run {run_id} workflow identity is invalid")
    if _object(summary.get("action"), f"run {run_id} action") != {
        "commit": head_sha,
        "imageDigest": image_digest,
    }:
        _fail(f"run {run_id} Action identity is invalid")

    durations, job_ids = _measurements(summary, expected_samples=expected_samples, run_id=run_id)
    ordered = sorted(durations)
    metric = _object(summary.get("metric"), f"run {run_id} metric")
    expected_p50 = _nearest_rank(ordered, 0.50)
    expected_p95 = _nearest_rank(ordered, 0.95)
    if (
        metric.get("definition") != METRIC_DEFINITION
        or metric.get("sampleCount") != expected_samples
        or _number(metric.get("thresholdSecondsExclusive"), "metric threshold") != threshold
        or _number(metric.get("nearestRankP50Seconds"), "metric p50") != expected_p50
        or _number(metric.get("nearestRankP95Seconds"), "metric p95") != expected_p95
        or [
            _number(value, "sorted duration")
            for value in _list(metric.get("sortedSeconds"), "sorted durations")
        ]
        != ordered
    ):
        _fail(f"run {run_id} metric does not match its measurements")
    if metric.get("passed") is not True or expected_p95 >= threshold:
        _fail("every individual run must pass below the threshold")
    fixture = _object(summary.get("fixture"), f"run {run_id} fixture")
    return durations, fixture, job_ids


def _write(path: Path, document: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise CombinedPerformanceEvidenceError("cannot write combined summary") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="append", type=Path, required=True)
    parser.add_argument("--expected-run-id", action="append", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    parser.add_argument("--expected-runs", type=int, required=True)
    parser.add_argument("--expected-samples-per-run", type=int, required=True)
    parser.add_argument("--threshold-seconds", type=float, required=True)
    return parser


def _run(arguments: argparse.Namespace) -> None:
    if arguments.repository != "Parth2412/attest":
        _fail("unexpected repository")
    if OID.fullmatch(arguments.head_sha) is None:
        _fail("head SHA must be a full lowercase Git object ID")
    if DIGEST.fullmatch(arguments.expected_image_digest) is None:
        _fail("image digest must be a full lowercase SHA-256 digest")
    if arguments.expected_image_digest != IMAGE_DIGEST:
        _fail("image digest does not match the reviewed candidate")
    if (
        arguments.expected_runs != 3
        or arguments.expected_samples_per_run != 20
        or arguments.threshold_seconds != 15
    ):
        _fail("combined performance dimensions do not match the frozen contract")
    summaries = list(arguments.summary)
    run_ids = list(arguments.expected_run_id)
    if len(summaries) != arguments.expected_runs or len(run_ids) != arguments.expected_runs:
        _fail("exactly three summaries and run IDs are required")
    if any(run_id <= 0 for run_id in run_ids) or run_ids != sorted(set(run_ids)):
        _fail("run IDs must be unique and strictly increasing")

    all_durations: list[float] = []
    all_job_ids: set[int] = set()
    fixtures: list[dict[str, object]] = []
    individual_p95: list[float] = []
    for path, run_id in zip(summaries, run_ids, strict=True):
        durations, fixture, job_ids = _validate_summary(
            path,
            repository=arguments.repository,
            head_sha=arguments.head_sha,
            image_digest=arguments.expected_image_digest,
            run_id=run_id,
            expected_samples=arguments.expected_samples_per_run,
            threshold=arguments.threshold_seconds,
        )
        if all_job_ids & job_ids:
            _fail("measurement job IDs overlap across runs")
        all_job_ids.update(job_ids)
        all_durations.extend(durations)
        fixtures.append(fixture)
        individual_p95.append(_nearest_rank(sorted(durations), 0.95))
    if any(fixture != fixtures[0] for fixture in fixtures[1:]):
        _fail("performance fixtures differ across runs")

    ordered = sorted(all_durations)
    expected_total = arguments.expected_runs * arguments.expected_samples_per_run
    if len(ordered) != expected_total:
        _fail(f"combined evidence must contain exactly {expected_total} measurements")
    p50 = _nearest_rank(ordered, 0.50)
    p95 = _nearest_rank(ordered, 0.95)
    passed = p95 < arguments.threshold_seconds
    document: dict[str, object] = {
        "schemaVersion": 1,
        "requirement": "REQ-F11-210",
        "acceptanceCriterion": "AC-F11-210",
        "repository": arguments.repository,
        "headSha": arguments.head_sha,
        "imageDigest": arguments.expected_image_digest,
        "performanceRunIds": run_ids,
        "individualNearestRankP95Seconds": individual_p95,
        "fixture": fixtures[0],
        "metric": {
            "definition": "Combined Action step durations from three consecutive hosted runs",
            "sampleCount": len(ordered),
            "thresholdSecondsExclusive": arguments.threshold_seconds,
            "nearestRankP50Seconds": p50,
            "nearestRankP95Seconds": p95,
            "sortedSeconds": ordered,
            "passed": passed,
        },
    }
    _write(arguments.output, document)
    if not passed:
        _fail(f"combined p95 must be below {arguments.threshold_seconds:g}")


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the three summaries, retain one deterministic summary, and enforce p95."""
    arguments = _parser().parse_args(argv)
    try:
        _run(arguments)
    except CombinedPerformanceEvidenceError as error:
        print(f"action-performance-combined: {error}", file=sys.stderr)
        return 1
    print("action-performance-combined: all three runs and the 60-sample p95 passed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
