"""F-11 bounded package and image release workflow contracts."""

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
RELEASE_NOTES: Final[Path] = REPOSITORY_ROOT / "release/RELEASE_NOTES-v0.1.5.md"
VALIDATOR: Final[Path] = REPOSITORY_ROOT / "scripts/validate_release_candidate.py"
IMAGE_DIGEST: Final[str] = "sha256:06581569a1382003b8537e016ce15b159066c275e186fbc27f8810da0105d5ab"
CONTEXT_DIGEST: Final[str] = (
    "sha256:58acc9a031c2d193f7160cffb16cd709ef7d1ce1dae6bb4cc92196b18a77b6bf"
)
CANDIDATE_SHA: Final[str] = "57ab2e08c297a2bf2131d2ea942d9e439d9c8faf"
PRIOR_RELEASE_SHA: Final[str] = "4e73dcaf888f15967da66826d48cca5ac6684fcb"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
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


@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
def test_release_is_closed_to_the_two_approved_python_patches() -> None:
    """REQ-F11-220: v0.1.5 may publish only signer 0.1.1 and CLI 0.1.4."""
    workflow = _workflow()
    assert workflow["name"] == "release"
    assert _triggers(workflow) == {
        "workflow_dispatch": {
            "inputs": {
                "performance_run_id_1": {
                    "description": (
                        "First consecutive attempt-1 performance run for this exact main commit"
                    ),
                    "required": True,
                    "type": "string",
                },
                "performance_run_id_2": {
                    "description": (
                        "Second consecutive attempt-1 performance run for this exact main commit"
                    ),
                    "required": True,
                    "type": "string",
                },
                "performance_run_id_3": {
                    "description": (
                        "Third consecutive attempt-1 performance run for this exact main commit"
                    ),
                    "required": True,
                    "type": "string",
                },
                "prior_sign_publication_run_id": {
                    "description": (
                        "Prior release run that published the exact attest-sign artifacts"
                    ),
                    "required": False,
                    "type": "string",
                },
                "prior_cli_publication_run_id": {
                    "description": (
                        "Prior release run that published the exact attest-cli artifacts"
                    ),
                    "required": False,
                    "type": "string",
                },
            }
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "release-v0.1.5",
        "cancel-in-progress": False,
    }
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.5",
        "PRODUCT_TAG": "v0.1.5",
        "ACTION_VERSION_TAG": "v1.0.5",
        "SIGN_VERSION": "0.1.1",
        "PUBLIC_CLI_VERSION": "0.1.4",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "PRIOR_RELEASE_SHA": PRIOR_RELEASE_SHA,
        "REVIEWED_CANDIDATE_RUN_ID": 38038325243,
        "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
        "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
        "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "build-patches",
        "smoke-patches",
        "assemble-assets",
        "attest-artifacts",
        "inspect-publication",
        "publish-sign",
        "publish-cli",
        "verify-published",
        "promote-image",
        "dogfood",
        "publish-release",
    }
    assert jobs["build-patches"]["needs"] == "preflight"
    assert jobs["smoke-patches"]["needs"] == "build-patches"
    assert jobs["assemble-assets"]["needs"] == ["preflight", "build-patches"]
    assert jobs["attest-artifacts"]["needs"] == ["assemble-assets", "smoke-patches"]
    assert jobs["inspect-publication"]["needs"] == ["build-patches", "smoke-patches"]
    assert jobs["promote-image"]["needs"] == ["preflight", "verify-published"]
    assert jobs["dogfood"]["needs"] == ["promote-image", "verify-published"]
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "promote-image",
        "verify-published",
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
    assert jobs["publish-sign"]["environment"] == {
        "name": "pypi-attest-sign",
        "url": "https://pypi.org/p/attest-sign",
    }
    assert jobs["publish-cli"]["environment"] == {
        "name": "pypi-attest-cli",
        "url": "https://pypi.org/p/attest-cli",
    }
    assert jobs["publish-sign"]["permissions"] == {"actions": "read", "id-token": "write"}
    assert jobs["publish-cli"]["permissions"] == {"actions": "read", "id-token": "write"}

    rendered = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("publish-store:", "pypi-attest-store", "attest-export", "twine"):
        assert forbidden not in rendered
    assert "pypa/gh-action-pypi-publish" in rendered
    assert "git diff --quiet" not in rendered
    assert '"${REVIEWED_CANDIDATE_SOURCE_SHA}:uv.lock"' in rendered
    assert '"$(git hash-object uv.lock)"' in rendered


@pytest.mark.ac("AC-F11-220")
def test_release_builds_smokes_and_publishes_exact_patch_artifacts() -> None:
    """REQ-F11-220: package bytes are built once, smoked twice, and OIDC-published."""
    jobs = _workflow()["jobs"]
    build = _commands(jobs["build-patches"])
    for fragment in (
        "uv build --package attest-sign",
        "--manifest release/patches/0.1.1-sign.toml",
        "uv build --package attest-cli",
        "--manifest release/patches/0.1.4.toml",
        "sign-distributions-v0.1.1",
        "cli-distributions-v0.1.4",
    ):
        assert fragment in build or fragment in str(jobs["build-patches"])

    assert jobs["smoke-patches"]["strategy"] == {
        "fail-fast": False,
        "matrix": {"python": ["3.12", "3.13"]},
    }
    smoke = _commands(jobs["smoke-patches"])
    for fragment in (
        "attest_sign-0.1.1-py3-none-any.whl",
        "attest_cli-0.1.4-py3-none-any.whl",
        'metadata.version("attest-sign") == "0.1.1"',
        'metadata.version("attest-cli") == "0.1.4"',
    ):
        assert fragment in smoke

    inspect = _commands(jobs["inspect-publication"])
    assert "https://pypi.org/pypi/${distribution}/${version}/json" in inspect
    assert "scripts/verify_published_release.py" in inspect
    assert "prior_sign_publication_run_id" in RELEASE_WORKFLOW.read_text(encoding="utf-8")

    for key, distribution, version in (
        ("publish-sign", "attest-sign", "0.1.1"),
        ("publish-cli", "attest-cli", "0.1.4"),
    ):
        job = jobs[key]
        publish = next(
            step for step in job["steps"] if str(step.get("uses", "")).startswith("pypa/")
        )
        assert publish["with"] == {
            "packages-dir": "dist/",
            "verify-metadata": True,
            "skip-existing": False,
            "print-hash": True,
            "attestations": True,
        }
        commands = _commands(job)
        assert f'"distribution": "{distribution}"' in commands
        assert f"distributions-v{version}" in str(job)


@pytest.mark.ac("AC-F11-220")
def test_release_verifies_publishers_and_public_bytes_before_promotion() -> None:
    """REQ-F11-220: protected publishers and exact PyPI bytes gate the image release."""
    jobs = _workflow()["jobs"]
    controls = _step(jobs["preflight"], "Validate source and immutable repository controls")["run"]
    for fragment in (
        "for distribution in attest-sign attest-cli",
        'environment="pypi-${distribution}"',
        ".can_admins_bypass == false",
        ".deployment_branch_policy.protected_branches == true",
        ".prevent_self_review",
    ):
        assert fragment in controls

    verify = jobs["verify-published"]
    assert verify["strategy"] == {
        "fail-fast": False,
        "matrix": {"python": ["3.12", "3.13"]},
    }
    commands = _commands(verify)
    for fragment in (
        "scripts/verify_published_release.py",
        "release/patches/0.1.1-sign.toml",
        "release/patches/0.1.4.toml",
        '"attest-sign==${SIGN_VERSION}"',
        '"attest-cli==${PUBLIC_CLI_VERSION}"',
        'metadata.version("attest-sign") == "0.1.1"',
        'metadata.version("attest-cli") == "0.1.4"',
    ):
        assert fragment in commands


@pytest.mark.ac("AC-F11-100")
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-250")
def test_release_recomputes_three_exact_attempt_one_performance_gates() -> None:
    """REQ-F11-210: publication requires three exact 20-job results and all 60 samples."""
    preflight = _workflow()["jobs"]["preflight"]
    validate = _step(preflight, "Validate the three consecutive performance runs")
    assert validate["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "PERFORMANCE_RUN_ID_1": "${{ inputs.performance_run_id_1 }}",
        "PERFORMANCE_RUN_ID_2": "${{ inputs.performance_run_id_2 }}",
        "PERFORMANCE_RUN_ID_3": "${{ inputs.performance_run_id_3 }}",
    }
    for fragment in (
        '.name == "measure Action cold start"',
        '.path == ".github/workflows/action-performance.yml"',
        '.head_branch == "main"',
        ".head_sha == $sha",
        ".run_attempt == 1",
        '.conclusion == "success"',
        'expected_events=("push" "workflow_dispatch" "workflow_dispatch")',
        "actions/workflows/action-performance.yml/runs?branch=main&per_page=100",
        "latest three exact-commit performance runs are not the supplied sequence",
    ):
        assert fragment in validate["run"]

    for index in range(1, 4):
        download = _step(preflight, f"Download performance evidence {index}")
        assert download["with"] == {
            "name": f"action-performance-v1.0.5-${{{{ inputs.performance_run_id_{index} }}}}",
            "path": f"${{{{ runner.temp }}}}/performance-evidence-{index}",
            "github-token": "${{ github.token }}",
            "repository": "Parth2412/attest",
            "run-id": f"${{{{ inputs.performance_run_id_{index} }}}}",
        }
    recompute = _step(preflight, "Recompute all performance results and the 60-sample gate")["run"]
    for fragment in (
        "scripts/summarize_action_performance.py",
        "scripts/combine_action_performance.py",
        '--head-sha "${GITHUB_SHA}"',
        '--expected-action-sha "${GITHUB_SHA}"',
        '--expected-image-digest "${REVIEWED_IMAGE_DIGEST}"',
        "--expected-samples 20",
        "--expected-runs 3",
        "--expected-samples-per-run 20",
        "--threshold-seconds 15",
        "--require-run-attempt 1",
        "recomputed-performance-summary-${index}.json",
        "combined-performance-summary.json",
        "cmp",
    ):
        assert fragment in recompute


@pytest.mark.ac("AC-F11-150")
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-230")
@pytest.mark.ac("AC-F11-240")
@pytest.mark.ac("AC-F11-250")
def test_release_revalidates_the_exact_candidate_supply_chain() -> None:
    """REQ-F11-210: the reviewed context, scans, labels, and identity are rechecked."""
    preflight = _workflow()["jobs"]["preflight"]
    candidate_run = _step(preflight, "Validate the reviewed candidate run")["run"]
    assert '.event == "push"' in candidate_run
    assert ".run_attempt == 1" in candidate_run
    commands = _commands(preflight)
    for fragment in (
        "scripts/prepare_action_context.py",
        "scripts/validate_release_candidate.py",
        "scripts/check_action_scan.py",
        '"org.opencontainers.image.version": "0.1.5-candidate"',
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
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
def test_release_promotes_without_rebuild_and_dogfoods_the_public_cli() -> None:
    """REQ-F11-210/220: exact promotion uses the newly published CLI for dogfood."""
    jobs = _workflow()["jobs"]
    promotion = _commands(jobs["promote-image"])
    assert "docker buildx imagetools create" in promotion
    assert '"${IMAGE_NAME}@${REVIEWED_IMAGE_DIGEST}"' in promotion
    assert "docker build " not in promotion
    assert "build-push-action" not in promotion

    dogfood = _commands(jobs["dogfood"])
    for fragment in (
        '"attest-cli==${PUBLIC_CLI_VERSION}"',
        'metadata.version("attest-cli") != "0.1.4"',
        'metadata.version("attest-sign") != "0.1.1"',
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
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
def test_release_attests_assets_and_keeps_v1_on_v1_0_4() -> None:
    """REQ-F11-210: immutable v0.1.5/v1.0.5 publish before any major-tag movement."""
    jobs = _workflow()["jobs"]
    repository_controls = _step(
        jobs["preflight"], "Validate source and immutable repository controls"
    )["run"]
    for fragment in (
        "gh api --paginate --slurp",
        '"repos/${GITHUB_REPOSITORY}/releases?per_page=100"',
        "[.[][] | select(.tag_name == $tag)] as $matches",
        "$matches[0].draft == true and $matches[0].immutable == false",
        "$matches[0].draft == false and $matches[0].immutable == true",
    ):
        assert fragment in repository_controls

    attestation = _step(jobs["attest-artifacts"], "Attest the bounded release assets")
    assert attestation["with"] == {"subject-path": "release-assets/*"}
    publish = _commands(jobs["publish-release"])
    for fragment in (
        "--notes-file release/RELEASE_NOTES-v0.1.5.md",
        '"repos/${GITHUB_REPOSITORY}/releases?per_page=100"',
        '"repos/${GITHUB_REPOSITORY}/releases/${release_id}"',
        "jq -n '{draft: false, make_latest: \"true\"}'",
        '--field ref="refs/tags/${ACTION_VERSION_TAG}"',
        ".immutable == true",
        '"majorTagMoved": False',
        '"pythonDistributionsPublished": [',
        '"attest-sign==0.1.1"',
        '"attest-cli==0.1.4"',
        '"performanceRunIds": [',
        'int(os.environ["PERFORMANCE_RUN_ID_1"])',
        'int(os.environ["PERFORMANCE_RUN_ID_2"])',
        'int(os.environ["PERFORMANCE_RUN_ID_3"])',
        '"candidateRunId": int(os.environ["REVIEWED_CANDIDATE_RUN_ID"])',
        "release-evidence-index.json",
    ):
        assert fragment in publish
    assert "releases/tags/${PRODUCT_TAG}" in publish
    assert publish.index("> release-publish-request.json") < publish.index(
        "releases/tags/${PRODUCT_TAG}"
    )
    assert 'gh release edit "${PRODUCT_TAG}"' not in publish
    assert "git/ref/tags/v1" in publish
    assert '= "${PRIOR_RELEASE_SHA}"' in publish
    assert 'git/refs/tags/v1"' not in publish

    references = _uses(_workflow())
    assert references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in references)


@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
def test_release_notes_state_the_bounded_artifact_set() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    for fragment in (
        "# attest 0.1.5 / GitHub Action v1.0.5",
        IMAGE_DIGEST,
        "python:3.12.14-alpine3.23",
        "cryptography==50.0.1",
        "maturin==1.15.0",
        "setuptools==84.0.0",
        "libcrypto3=3.5.9-r0",
        "libssl3=3.5.9-r0",
        "git=2.52.0-r0",
        "three consecutive",
        "60-sample",
        "attest-sign==0.1.1",
        "attest-cli==0.1.4",
        "No other Python distribution",
        "v1",
        "v1.0.4",
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
