"""F-11 image-only release workflow and candidate-promotion contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML lacks typing metadata.

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/release.yml"
RELEASE_NOTES: Final[Path] = REPOSITORY_ROOT / "release/RELEASE_NOTES-v0.1.4.md"
VALIDATOR: Final[Path] = REPOSITORY_ROOT / "scripts/validate_release_candidate.py"
IMAGE_DIGEST: Final[str] = "sha256:d25c6d00db13c34423b38e2c948bde8f41d2856a25bcf251bca2213872a15fbd"
CONTEXT_DIGEST: Final[str] = (
    "sha256:e07c5cf399548155ffeb2acfd25ba7afb2ab4883eb648ac0ff90d8e859ad3321"
)
CANDIDATE_SHA: Final[str] = "de7113e3659cc2224d2f3ffb1b12f16628807616"
PRIOR_RELEASE_SHA: Final[str] = "8dcfdaf4b16a0547222e3f174bc0c0e13e3549c8"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
}


def _workflow() -> dict[str, Any]:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    if "on" not in workflow and True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    triggers = workflow.get("on")
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


def _commands(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"] if isinstance(step, dict))


@pytest.mark.ac("AC-F11-200")
def test_release_is_a_closed_image_only_workflow() -> None:
    """REQ-F11-200: v0.1.4 has no Python build or publication authority."""
    workflow = _workflow()
    assert workflow["name"] == "release"
    assert _triggers(workflow) == {
        "workflow_dispatch": {
            "inputs": {
                "performance_run_id": {
                    "description": (
                        "Successful attempt-1 Action performance run for this exact main commit"
                    ),
                    "required": True,
                    "type": "string",
                }
            }
        }
    }
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
        "PRIOR_RELEASE_SHA": PRIOR_RELEASE_SHA,
        "REVIEWED_CANDIDATE_RUN_ID": 36258748890,
        "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
        "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
        "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "assemble-assets",
        "attest-artifacts",
        "promote-image",
        "dogfood",
        "publish-release",
    }
    assert jobs["assemble-assets"]["needs"] == "preflight"
    assert jobs["attest-artifacts"]["needs"] == "assemble-assets"
    assert jobs["promote-image"]["needs"] == "preflight"
    assert jobs["dogfood"]["needs"] == "promote-image"
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "promote-image",
    ]
    assert jobs["promote-image"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }
    assert jobs["publish-release"]["permissions"] == {
        "actions": "read",
        "contents": "write",
    }
    assert jobs["dogfood"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }

    rendered = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "pypa/gh-action-pypi-publish",
        "publish-store:",
        "publish-cli:",
        "build-patches:",
        "smoke-patches:",
        "twine",
    ):
        assert forbidden not in rendered
    assert "git diff --quiet" in rendered
    assert "pyproject.toml uv.lock packages release/packages.toml release/patches" in rendered


@pytest.mark.ac("AC-F11-100")
@pytest.mark.ac("AC-F11-200")
def test_release_recomputes_the_exact_attempt_one_performance_gate() -> None:
    """REQ-F11-200: publication requires the same merged commit's retained 20-job result."""
    preflight = _workflow()["jobs"]["preflight"]
    validate = _step(preflight, "Validate the exact performance run")
    assert validate["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "PERFORMANCE_RUN_ID": "${{ inputs.performance_run_id }}",
    }
    for fragment in (
        '.name == "measure Action cold start"',
        '.path == ".github/workflows/action-performance.yml"',
        '.head_branch == "main"',
        ".head_sha == $sha",
        ".run_attempt == 1",
        '.conclusion == "success"',
    ):
        assert fragment in validate["run"]

    download = _step(preflight, "Download the exact performance evidence")
    assert download["with"] == {
        "name": "action-performance-v1.0.4-${{ inputs.performance_run_id }}",
        "path": "${{ runner.temp }}/performance-evidence",
        "github-token": "${{ github.token }}",
        "repository": "Parth2412/attest",
        "run-id": "${{ inputs.performance_run_id }}",
    }
    recompute = _step(preflight, "Recompute and retain the performance result")["run"]
    for fragment in (
        "scripts/summarize_action_performance.py",
        '--head-sha "${GITHUB_SHA}"',
        '--expected-action-sha "${GITHUB_SHA}"',
        '--expected-image-digest "${REVIEWED_IMAGE_DIGEST}"',
        "--expected-samples 20",
        "--threshold-seconds 15",
        "--require-run-attempt 1",
        "recomputed-performance-summary.json",
        "cmp",
    ):
        assert fragment in recompute


@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-200")
def test_release_revalidates_the_exact_candidate_supply_chain() -> None:
    """REQ-F11-200: the reviewed context, scans, labels, and identity are rechecked."""
    commands = _commands(_workflow()["jobs"]["preflight"])
    for fragment in (
        "scripts/prepare_action_context.py",
        "scripts/validate_release_candidate.py",
        "scripts/check_action_scan.py",
        '"org.opencontainers.image.version": "0.1.4-candidate"',
        "--signer-workflow",
        "--source-ref refs/heads/dev",
        "--deny-self-hosted-runners",
        "candidate-image-sbom.spdx.json",
        "candidate-image-provenance.slsa.json",
        "candidate-image-manifest-linux-amd64.json",
        "candidate-image-manifest-linux-arm64.json",
    ):
        assert fragment in commands
    assert commands.count("scripts/check_action_scan.py") == 2
    assert "linux/amd64" in commands
    assert "linux/arm64" in commands


@pytest.mark.ac("AC-F11-090")
@pytest.mark.ac("AC-F11-200")
def test_release_promotes_without_rebuild_and_dogfoods_the_public_cli() -> None:
    """REQ-F11-200: only the exact manifest is promoted and public 0.1.3 signs source."""
    jobs = _workflow()["jobs"]
    promotion = _commands(jobs["promote-image"])
    assert "docker buildx imagetools create" in promotion
    assert '"${IMAGE_NAME}@${REVIEWED_IMAGE_DIGEST}"' in promotion
    assert "docker build " not in promotion
    assert "build-push-action" not in promotion

    dogfood = _commands(jobs["dogfood"])
    for fragment in (
        '"attest-cli==${PUBLIC_CLI_VERSION}"',
        'metadata.version("attest-cli") != "0.1.3"',
        "attest run",
        "attest verify",
        "--signing-environment production",
        "--verify-environment production",
        '--base "${PRIOR_RELEASE_SHA}"',
        '--head "${GITHUB_SHA}"',
    ):
        assert fragment in dogfood
    assert "uv build" not in dogfood


@pytest.mark.ac("AC-F11-080")
@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-200")
def test_release_attests_assets_and_keeps_v1_on_v1_0_3() -> None:
    """REQ-F11-200: immutable v0.1.4/v1.0.4 publish before any major-tag movement."""
    jobs = _workflow()["jobs"]
    attestation = _step(jobs["attest-artifacts"], "Attest the image-only release assets")
    assert attestation["with"] == {"subject-path": "release-assets/*"}
    publish = _commands(jobs["publish-release"])
    for fragment in (
        "--notes-file release/RELEASE_NOTES-v0.1.4.md",
        '--field ref="refs/tags/${ACTION_VERSION_TAG}"',
        ".immutable == true",
        '"majorTagMoved": False',
        '"pythonDistributionsPublished": False',
        '"performanceRunId": int(os.environ["PERFORMANCE_RUN_ID"])',
        '"candidateRunId": int(os.environ["REVIEWED_CANDIDATE_RUN_ID"])',
        "release-evidence-index.json",
    ):
        assert fragment in publish
    assert "git/ref/tags/v1" in publish
    assert '= "${PRIOR_RELEASE_SHA}"' in publish
    assert 'git/refs/tags/v1"' not in publish

    references = _uses(_workflow())
    assert references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in references)


@pytest.mark.ac("AC-F11-200")
def test_release_notes_state_the_bounded_artifact_set() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    for fragment in (
        "# attest 0.1.4 / GitHub Action v1.0.4",
        IMAGE_DIGEST,
        "python:3.12.14-alpine3.23",
        "git=2.52.0-r0",
        "No Python distribution is rebuilt or uploaded.",
        "v1",
        "v1.0.3",
    ):
        assert fragment in notes


def _candidate_fixture(
    root: Path,
    *,
    layer_media_type: str = "application/vnd.oci.image.layer.v1.tar+zstd",
) -> tuple[Path, Path, Path, str, str]:
    evidence = root / "candidate"
    evidence.mkdir()
    context = {
        "schemaVersion": 1,
        "digestAlgorithm": "sha256",
        "files": [{"path": "locked", "mode": "0644", "size": 1, "sha256": "0" * 64}],
    }
    encoded_context = json.dumps(
        context, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    context_digest = f"sha256:{hashlib.sha256(encoded_context).hexdigest()}"
    context_manifest = {**context, "contextDigest": context_digest}
    (evidence / "context-manifest.json").write_text(json.dumps(context_manifest), encoding="utf-8")
    (evidence / "context-digest.txt").write_text(f"{context_digest}\n", encoding="utf-8")

    platform_manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "layers": [
            {
                "mediaType": layer_media_type,
                "digest": "sha256:" + "3" * 64,
                "size": 1,
            }
        ],
    }
    platform_manifest_bytes = json.dumps(platform_manifest, separators=(",", ":")).encode()
    platform_manifest_digest = f"sha256:{hashlib.sha256(platform_manifest_bytes).hexdigest()}"
    for architecture in ("amd64", "arm64"):
        (evidence / f"manifest-linux-{architecture}.json").write_bytes(platform_manifest_bytes)
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "digest": platform_manifest_digest,
                "size": len(platform_manifest_bytes),
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "digest": platform_manifest_digest,
                "size": len(platform_manifest_bytes),
                "platform": {"os": "linux", "architecture": "arm64"},
            },
            {
                "digest": "sha256:" + "5" * 64,
                "size": 1,
                "platform": {"os": "unknown", "architecture": "unknown"},
            },
        ],
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
    (evidence / "manifest.json").write_bytes(manifest_bytes)
    image_digest = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
    (evidence / "image-digest.txt").write_text(f"{image_digest}\n", encoding="utf-8")
    (evidence / "build-metadata.json").write_text(
        json.dumps(
            {
                "containerimage.digest": image_digest,
                "containerimage.descriptor": {
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "digest": image_digest,
                    "size": len(manifest_bytes),
                },
            }
        ),
        encoding="utf-8",
    )
    platform_evidence = {"linux/amd64": {"present": True}, "linux/arm64": {"present": True}}
    for name in ("sbom.spdx.json", "provenance.slsa.json"):
        (evidence / name).write_text(json.dumps(platform_evidence), encoding="utf-8")

    current_context = root / "current-context.json"
    current_context.write_text(json.dumps(context_manifest), encoding="utf-8")
    action_manifest = root / "action.yml"
    action_manifest.write_text(
        f"runs:\n  using: docker\n  image: docker://ghcr.io/parth2412/attest@{image_digest}\n",
        encoding="utf-8",
    )
    return evidence, current_context, action_manifest, context_digest, image_digest


def _validate_candidate(
    evidence: Path,
    current_context: Path,
    action_manifest: Path,
    context_digest: str,
    image_digest: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--evidence-directory",
            str(evidence),
            "--current-context-manifest",
            str(current_context),
            "--action-manifest",
            str(action_manifest),
            "--expected-context-digest",
            context_digest,
            "--expected-image-digest",
            image_digest,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-150")
def test_release_candidate_validator_accepts_exact_reviewed_evidence(tmp_path: Path) -> None:
    result = _validate_candidate(*_candidate_fixture(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "candidate evidence: validated exact reviewed context and image" in result.stdout


@pytest.mark.ac("AC-F11-150")
@pytest.mark.parametrize(
    ("target", "replacement", "message"),
    [
        ("context-digest.txt", "sha256:" + "1" * 64 + "\n", "context digest mismatch"),
        ("image-digest.txt", "sha256:" + "2" * 64 + "\n", "image digest mismatch"),
        ("sbom.spdx.json", "{}", "invalid SBOM platform evidence"),
        ("provenance.slsa.json", "{}", "invalid provenance platform evidence"),
    ],
)
def test_release_candidate_validator_rejects_mismatched_evidence(
    tmp_path: Path, target: str, replacement: str, message: str
) -> None:
    evidence, current_context, action_manifest, context_digest, image_digest = _candidate_fixture(
        tmp_path
    )
    (evidence / target).write_text(replacement, encoding="utf-8")
    result = _validate_candidate(
        evidence, current_context, action_manifest, context_digest, image_digest
    )
    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.ac("AC-F11-100")
@pytest.mark.ac("AC-F11-200")
def test_release_candidate_validator_rejects_non_zstd_layers(tmp_path: Path) -> None:
    fixture = _candidate_fixture(
        tmp_path,
        layer_media_type="application/vnd.oci.image.layer.v1.tar+gzip",
    )
    result = _validate_candidate(*fixture)
    assert result.returncode == 1
    assert "candidate linux/amd64 image layers are not all zstd" in result.stderr
