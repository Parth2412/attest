"""F-11 exact v0.1.4 release-recovery workflow contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML lacks typing metadata.

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RECOVERY_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/recover-release-v0.1.4.yml"
RELEASE_SHA: Final[str] = "4e73dcaf888f15967da66826d48cca5ac6684fcb"
PRIOR_RELEASE_SHA: Final[str] = "8dcfdaf4b16a0547222e3f174bc0c0e13e3549c8"
CANDIDATE_SHA: Final[str] = "a4c47f13a0963b30f02f7bc2ef9d4d81d88cac3f"
CONTEXT_DIGEST: Final[str] = (
    "sha256:ef05578f882f1a55364bc14c260898cb4c656161446d04b1343e43aaabf2cb8b"
)
IMAGE_DIGEST: Final[str] = "sha256:7415834d673915cf7935d43f867fd4b49f032984f4733f411eb88a787fe1f4df"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
SHA256_DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
}


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(RECOVERY_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    if "on" not in workflow and True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


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


def _commands(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"] if isinstance(step, dict))


@pytest.mark.ac("AC-F11-200")
def test_recovery_is_closed_to_the_exact_failed_release_transaction() -> None:
    """REQ-F11-200: recovery cannot select a different run, draft, or release target."""
    workflow = _workflow()
    assert workflow["name"] == "recover release v0.1.4"
    assert workflow["on"] == {"workflow_dispatch": {}}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "release-v0.1.4",
        "cancel-in-progress": False,
    }
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.4",
        "PRODUCT_TAG": "v0.1.4",
        "ACTION_VERSION_TAG": "v1.0.4",
        "PUBLIC_CLI_VERSION": "0.1.3",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "RELEASE_SHA": RELEASE_SHA,
        "PRIOR_RELEASE_SHA": PRIOR_RELEASE_SHA,
        "SOURCE_RELEASE_RUN_ID": 36762051962,
        "SOURCE_DRAFT_RELEASE_ID": 400347468,
        "PERFORMANCE_RUN_ID": 36761068084,
        "PERFORMANCE_ARTIFACT_ID": 11118342353,
        "REVIEWED_CANDIDATE_RUN_ID": 36758760939,
        "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
        "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
        "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {"preflight", "publish"}
    assert jobs["preflight"]["permissions"] == {
        "actions": "read",
        "attestations": "read",
        "contents": "read",
        "packages": "read",
    }
    assert jobs["publish"]["needs"] == "preflight"
    assert jobs["publish"]["environment"] == "release-recovery-v0.1.4"
    assert jobs["publish"]["permissions"] == {
        "actions": "read",
        "contents": "write",
    }

    source = _step(jobs["preflight"], "Validate the source release transaction")["run"]
    for fragment in (
        '.name == "release"',
        '.path == ".github/workflows/release.yml"',
        '.event == "workflow_dispatch"',
        ".head_sha == $sha",
        ".run_attempt == 1",
        '.conclusion == "failure"',
        "110046816716",
        "110047069536",
        "110047069673",
        "110047155348",
        "110047176832",
        "110047383859",
        "release-assets-v0.1.4",
        "release-preflight-evidence-v0.1.4",
        "release-asset-attestation-evidence-v0.1.4",
        "image-promotion-evidence-v0.1.4",
        "release-dogfood-evidence-v0.1.4",
    ):
        assert fragment in source
    for digest in (
        "sha256:dcab2f9bcf958e27207f004a6c16ab42497250a585c6babfad4696153e7838d5",
        "sha256:c1758e5b22206526233071457a0c9e262c449c228efda1d0fd6f9a306f77e258",
        "sha256:46e8e0b5eef6be8c5ff0a55143d765b6726ceb9e36146b8b69fdc6f28892cee3",
        "sha256:98cda2452c8e2e5a63e5678b59e41a32c1a323e3cc3ba2037b8468bb5421819f",
        "sha256:7f55e5220c611427273bb8c989a407987d3f776ac83b28204bc4a545854a5fac",
    ):
        assert digest in source

    digest_literals = re.findall(
        r"sha256:[0-9a-f]+", RECOVERY_WORKFLOW.read_text(encoding="utf-8")
    )
    assert digest_literals
    assert all(SHA256_DIGEST.fullmatch(digest) for digest in digest_literals)


@pytest.mark.ac("AC-F11-100")
@pytest.mark.ac("AC-F11-200")
def test_recovery_recomputes_the_retained_attempt_one_performance_result() -> None:
    """REQ-F11-100: only the retained successful 20-job result may be recovered."""
    preflight = _workflow()["jobs"]["preflight"]
    validate = _step(preflight, "Validate and recompute the performance evidence")["run"]
    for fragment in (
        "action-performance-v1.0.4-${PERFORMANCE_RUN_ID}",
        "sha256:7a039d3a71d421a27127a2a814bd915650bbca41f487933b8119cbaada8efb9a",
        '.name == "measure Action cold start"',
        '.path == ".github/workflows/action-performance.yml"',
        ".head_sha == $sha",
        ".run_attempt == 1",
        '.conclusion == "success"',
        'git show "${RELEASE_SHA}:.github/workflows/action-performance.yml"',
        "scripts/summarize_action_performance.py",
        '--run-id "${PERFORMANCE_RUN_ID}"',
        '--head-sha "${RELEASE_SHA}"',
        "--expected-samples 20",
        "--threshold-seconds 15",
        "--require-run-attempt 1",
        ".metric.nearestRankP95Seconds == 14",
        ".metric.passed == true",
        "cmp",
    ):
        assert fragment in validate


@pytest.mark.ac("AC-F11-090")
@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-200")
def test_recovery_reverifies_supply_chain_and_exact_draft_assets() -> None:
    """REQ-F11-200: recovery rechecks image, scans, attestations, dogfood, and bytes."""
    preflight = _workflow()["jobs"]["preflight"]
    commands = _commands(preflight)
    for fragment in (
        "scripts/check_action_scan.py",
        '"${IMAGE_NAME}:${PRODUCT_VERSION}"',
        'test "${observed}" = "${REVIEWED_IMAGE_DIGEST}"',
        "cmp recovery-evidence/public-image-manifest.json",
        "gh attestation verify",
        '--signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/action-candidate.yml"',
        '--source-digest "${REVIEWED_CANDIDATE_SOURCE_SHA}"',
        "--source-ref refs/heads/dev",
        '--signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/release.yml"',
        '--source-digest "${RELEASE_SHA}"',
        "--source-ref refs/heads/main",
        '"attest-cli==${PUBLIC_CLI_VERSION}"',
        '/bin/attest" verify',
        '--base "${PRIOR_RELEASE_SHA}"',
        '--head "${RELEASE_SHA}"',
        '"releaseRunId": int(os.environ["SOURCE_RELEASE_RUN_ID"])',
        '"releaseCommit": os.environ["RELEASE_SHA"]',
        "release-evidence-index.json",
        "remote != local",
        "release assets differ from the exact source transaction",
    ):
        assert fragment in commands
    assert commands.count("python3 scripts/check_action_scan.py") == 2

    draft = _step(preflight, "Validate the exact draft release")["run"]
    for fragment in (
        '"repos/${GITHUB_REPOSITORY}/releases/${SOURCE_DRAFT_RELEASE_ID}"',
        ".id == $releaseId",
        '.tag_name == "v0.1.4"',
        ".target_commitish == $sha",
        '.name == "attest 0.1.4 / Action v1.0.4"',
        '.author.login == "github-actions[bot]"',
        ".author.id == 41898282",
        ".draft == true and .immutable == false",
        ".draft == false and .immutable == true",
    ):
        assert fragment in draft


@pytest.mark.ac("AC-F11-080")
@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-200")
def test_recovery_only_publishes_the_bound_draft_and_immutable_action_tag() -> None:
    """REQ-F11-200: publication resumes by ID and never moves the major tag."""
    workflow = _workflow()
    publish = _commands(workflow["jobs"]["publish"])
    for fragment in (
        '"repos/${GITHUB_REPOSITORY}/releases/${SOURCE_DRAFT_RELEASE_ID}"',
        "remote != expected",
        "jq -n '{draft: false, make_latest: \"true\"}'",
        "--method PATCH",
        '"repos/${GITHUB_REPOSITORY}/releases/tags/${PRODUCT_TAG}"',
        ".immutable == true",
        '--field ref="refs/tags/${ACTION_VERSION_TAG}"',
        '--field sha="${RELEASE_SHA}"',
        'git/ref/tags/v1"',
        '= "${PRIOR_RELEASE_SHA}"',
    ):
        assert fragment in publish
    for forbidden in (
        "gh release create",
        "gh release upload",
        "gh release delete",
        "gh release edit",
        'git/refs/tags/v1"',
        "pypa/gh-action-pypi-publish",
        "twine",
        "secrets.",
    ):
        assert forbidden not in RECOVERY_WORKFLOW.read_text(encoding="utf-8")
    assert publish.count("--method POST") == 1
    assert publish.count("--method PATCH") == 1

    references = _uses(workflow)
    assert references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in references)
