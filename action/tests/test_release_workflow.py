"""F-11 bounded image-only security release workflow contracts."""

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
RELEASE_NOTES: Final[Path] = REPOSITORY_ROOT / "release/RELEASE_NOTES-v0.1.6.md"
VALIDATOR: Final[Path] = REPOSITORY_ROOT / "scripts/validate_release_candidate.py"
IMAGE_DIGEST: Final[str] = "sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe"
CONTEXT_DIGEST: Final[str] = (
    "sha256:646ac89af1aa583ce3780c8542d980559a6782b171131df017daf35293440df1"
)
CANDIDATE_SHA: Final[str] = "ae456176d0faefb732b9d8d8a4526365ad559278"
SOURCE_ARTIFACT_DIGEST: Final[str] = (
    "sha256:535fb5f393bc57d28383cd8f453eac87e196531d44d28e835e54efefcbb22e0a"
)
PRIOR_RELEASE_SHA: Final[str] = "203d2deb7dff946dc82c6efc6506bc34adbcd209"
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


@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
@pytest.mark.ac("AC-F11-260")
@pytest.mark.ac("AC-F11-290")
def test_release_is_closed_to_the_approved_image_only_artifact_set() -> None:
    """REQ-F11-290: v0.1.6 publishes no Python distributions."""
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
            }
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "release-v0.1.6",
        "cancel-in-progress": False,
    }
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.6",
        "PRODUCT_TAG": "v0.1.6",
        "ACTION_VERSION_TAG": "v1.0.6",
        "SIGN_VERSION": "0.1.1",
        "PUBLIC_CLI_VERSION": "0.1.4",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "PRIOR_RELEASE_SHA": PRIOR_RELEASE_SHA,
        "REVIEWED_CANDIDATE_RUN_ID": 39906806331,
        "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
        "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
        "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "verify-public-packages",
        "assemble-assets",
        "attest-artifacts",
        "promote-image",
        "dogfood",
        "publish-release",
    }
    assert jobs["verify-public-packages"]["needs"] == "preflight"
    assert jobs["assemble-assets"]["needs"] == ["preflight", "verify-public-packages"]
    assert jobs["attest-artifacts"]["needs"] == "assemble-assets"
    assert jobs["promote-image"]["needs"] == ["preflight", "verify-public-packages"]
    assert jobs["dogfood"]["needs"] == ["promote-image", "verify-public-packages"]
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "promote-image",
        "verify-public-packages",
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
        "packages-dir",
        "skip-existing",
        "uv build",
        "pypi-attest-",
        "publish-sign:",
        "publish-cli:",
        "verify-published:",
        "inspect-publication:",
        "prior_sign_publication_run_id",
        "prior_cli_publication_run_id",
    ):
        assert forbidden not in rendered
    assert "git diff --quiet" not in rendered
    assert '"${REVIEWED_CANDIDATE_SOURCE_SHA}:uv.lock"' in rendered
    assert '"$(git hash-object uv.lock)"' in rendered


@pytest.mark.ac("AC-F11-220")
@pytest.mark.ac("AC-F11-290")
def test_release_verifies_unchanged_public_packages_without_publication() -> None:
    """REQ-F11-290: public package health is proved without rebuilding or upload."""
    jobs = _workflow()["jobs"]
    verify = jobs["verify-public-packages"]
    assert verify["permissions"] == {"contents": "read"}
    assert verify["strategy"] == {
        "fail-fast": False,
        "matrix": {"python": ["3.12", "3.13"]},
    }
    commands = _commands(verify)
    for fragment in (
        "https://pypi.org/pypi/${distribution}/${version}/json",
        "pypi-${distribution}-${version}-python-${{ matrix.python }}.json",
        "attest-core:0.1.0",
        "attest-collect:0.1.0",
        "attest-sign:0.1.1",
        "attest-store:0.1.1",
        "attest-policy:0.1.0",
        "attest-cli:0.1.4",
        '"attest-sign==${SIGN_VERSION}"',
        '"attest-cli==${PUBLIC_CLI_VERSION}"',
        '"minimumSafeCertifi": "2026.10.19"',
        'for excluded in ("virtualenv", "python-discovery")',
        '"pythonDistributionsPublished": []',
        "build/public-package-smoke/bin/attest --help",
    ):
        assert fragment in commands
    assert "uv build" not in commands
    assert "id-token" not in verify["permissions"]


@pytest.mark.ac("AC-F11-220")
@pytest.mark.ac("AC-F11-290")
def test_release_progresses_only_after_public_package_verification() -> None:
    """REQ-F11-290: promotion and dogfood require both read-only package probes."""
    jobs = _workflow()["jobs"]
    expected_conditions = {
        "promote-image": (
            "always() && "
            "needs.preflight.result == 'success' && "
            "needs.verify-public-packages.result == 'success'"
        ),
        "dogfood": (
            "always() && "
            "needs.promote-image.result == 'success' && "
            "needs.verify-public-packages.result == 'success'"
        ),
    }
    for job_name, expected in expected_conditions.items():
        observed = " ".join(jobs[job_name]["if"].split())
        assert observed == expected


@pytest.mark.ac("AC-F11-100")
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-250")
@pytest.mark.ac("AC-F11-260")
@pytest.mark.ac("AC-F11-280")
def test_release_recomputes_three_exact_attempt_one_performance_gates() -> None:
    """REQ-F11-280: publication requires three exact 20-job results and all 60 samples."""
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
            "name": f"action-performance-v1.0.6-${{{{ inputs.performance_run_id_{index} }}}}",
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
        "--engineering-target-seconds 15",
        "--slo-threshold-seconds 18",
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
@pytest.mark.ac("AC-F11-270")
@pytest.mark.ac("AC-F11-310")
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
        "scripts/check_action_component_scan.py",
        '--source-evidence-directory "${RUNNER_TEMP}/candidate-source"',
        '--runtime-sources "${RUNNER_TEMP}/reviewed-runtime-sources"',
        '--component-scan "${RUNNER_TEMP}/candidate-component-scan/grype-runtime-components.json"',
        'docker pull "${source_reference}"',
        '"io.github.parth2412.attest.source-artifact": source_reference',
        "candidate-source-attestation-verification.json",
        '"org.opencontainers.image.version": "0.1.6-candidate"',
        "--signer-workflow",
        "--source-ref refs/heads/dev",
        "--deny-self-hosted-runners",
        "candidate-image-sbom.spdx.json",
        "candidate-image-provenance.slsa.json",
        "candidate-image-manifest-linux-amd64.json",
        "candidate-image-manifest-linux-arm64.json",
    ):
        assert fragment in commands
    assert "action-candidate-source-${{ env.REVIEWED_CANDIDATE_SOURCE_SHA }}" in str(preflight)
    assert "action-candidate-component-scan-${{ env.REVIEWED_CANDIDATE_SOURCE_SHA }}" in str(
        preflight
    )
    assert "action-candidate-container-linux-amd64-${{ env.REVIEWED_CANDIDATE_SOURCE_SHA }}" in str(
        preflight
    )
    assert "action-candidate-container-linux-arm64-${{ env.REVIEWED_CANDIDATE_SOURCE_SHA }}" in str(
        preflight
    )
    assert "reviewed-runtime-sources" in str(preflight)
    assert commands.count("scripts/check_action_scan.py") == 2
    assert commands.count("scripts/check_action_component_scan.py") == 1
    assert "linux/amd64" in commands
    assert "linux/arm64" in commands
    for fragment in (
        "gitVersion",
        "git version 2.52.0",
        "libcurl/8.23.0 OpenSSL/3.5.9 zlib/1.3.2",
        "loader-dependencies.txt",
        "candidate-image-layers-linux-amd64.json",
        "candidate-image-layers-linux-arm64.json",
    ):
        assert fragment in commands

    source_upload = _step(preflight, "Retain the exact corresponding source for release")
    assert source_upload["with"] == {
        "name": "release-corresponding-source-v0.1.6",
        "path": "${{ runner.temp }}/reviewed-runtime-sources",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }

    assemble = _workflow()["jobs"]["assemble-assets"]
    source_download = next(
        step
        for step in assemble["steps"]
        if step.get("uses", "").startswith("actions/download-artifact")
        and step.get("with", {}).get("name") == "release-corresponding-source-v0.1.6"
    )
    assert source_download["with"]["path"] == "corresponding-source"
    assert "action-corresponding-source-v1.0.6.tar.gz" in _commands(assemble)


@pytest.mark.ac("AC-F11-090")
@pytest.mark.ac("AC-F11-210")
@pytest.mark.ac("AC-F11-220")
def test_release_promotes_without_rebuild_and_dogfoods_the_public_cli() -> None:
    """REQ-F11-210/290: exact promotion uses the unchanged public CLI for dogfood."""
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
@pytest.mark.ac("AC-F11-290")
def test_release_attests_assets_and_keeps_v1_on_v1_0_5() -> None:
    """REQ-F11-290: immutable v0.1.6/v1.0.6 publish before major-tag movement."""
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

    attestation = _step(jobs["attest-artifacts"], "Attest the image-only release assets")
    assert attestation["with"] == {"subject-path": "release-assets/*"}
    publish = _commands(jobs["publish-release"])
    for fragment in (
        "--notes-file release/RELEASE_NOTES-v0.1.6.md",
        '"repos/${GITHUB_REPOSITORY}/releases?per_page=100"',
        '"repos/${GITHUB_REPOSITORY}/releases/${release_id}"',
        "jq -n '{draft: false, make_latest: \"true\"}'",
        '--field ref="refs/tags/${ACTION_VERSION_TAG}"',
        ".immutable == true",
        '"majorTagMoved": False',
        '"pythonDistributionsPublished": []',
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
@pytest.mark.ac("AC-F11-260")
def test_release_notes_state_the_bounded_artifact_set() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    for fragment in (
        "# attest 0.1.6 / GitHub Action v1.0.6",
        IMAGE_DIGEST,
        CONTEXT_DIGEST,
        CANDIDATE_SHA,
        "39906806331",
        SOURCE_ARTIFACT_DIGEST,
        "Git `2.52.0`",
        "curl `8.23.0`",
        "certifi `2026.10.19`",
        "musl `1.2.5-r24`",
        "virtualenv `21.14.12`",
        "python-discovery `1.6.4`",
        "three consecutive",
        "60-sample",
        "attest-sign==0.1.1",
        "attest-cli==0.1.4",
        "No Python distribution",
        "39829765757",
        "v1",
        "v1.0.5",
    ):
        assert fragment in notes
    assert "pythonDistributionsPublished" in notes


def _candidate_fixture(
    root: Path,
    *,
    layer_media_type: str = "application/vnd.oci.image.layer.v1.tar+zstd",
) -> tuple[Path, Path, Path, Path, Path, Path, str, str]:
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

    layers = [
        {
            "mediaType": layer_media_type,
            "digest": "sha256:" + str(index) * 64,
            "size": index,
        }
        for index in range(1, 5)
    ]
    platform_manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "layers": layers,
    }
    platform_manifest_bytes = json.dumps(platform_manifest, separators=(",", ":")).encode()
    platform_manifest_digest = f"sha256:{hashlib.sha256(platform_manifest_bytes).hexdigest()}"
    for architecture in ("amd64", "arm64"):
        (evidence / f"manifest-linux-{architecture}.json").write_bytes(platform_manifest_bytes)
        (evidence / f"layers-linux-{architecture}.json").write_text(
            json.dumps(
                {
                    "platform": f"linux/{architecture}",
                    "primaryLayers": layers[:3],
                    "entrypointLayer": layers[3],
                }
            ),
            encoding="utf-8",
        )
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

    runtime_sources = root / "runtime-sources"
    runtime_sources.mkdir()
    source_files = {
        "Dockerfile": b"FROM source-build\n",
        "curl-8.23.0.tar.xz": b"exact curl source",
        "curl-COPYING": b"curl licence",
        "git-2.52.0.tar.xz": b"exact git source",
        "git-COPYING": b"git licence",
        "runtime-components.openvex.json": (
            REPOSITORY_ROOT / "action/runtime-components.openvex.json"
        ).read_bytes(),
        "runtime-sources.json": (REPOSITORY_ROOT / "action/runtime-sources.json").read_bytes(),
    }
    component_sbom = {
        "spdxVersion": "SPDX-2.3",
        "packages": [
            {
                "name": "curl",
                "versionInfo": "8.23.0",
                "licenseDeclared": "curl",
                "externalRefs": [
                    {
                        "referenceType": "purl",
                        "referenceLocator": "pkg:generic/curl@8.23.0",
                    },
                    {
                        "referenceType": "cpe23Type",
                        "referenceLocator": "cpe:2.3:a:haxx:curl:8.23.0:*:*:*:*:*:*:*",
                    },
                ],
            },
            {
                "name": "git",
                "versionInfo": "2.52.0",
                "licenseDeclared": "GPL-2.0-only",
                "externalRefs": [
                    {
                        "referenceType": "purl",
                        "referenceLocator": "pkg:generic/git@2.52.0",
                    },
                    {
                        "referenceType": "cpe23Type",
                        "referenceLocator": "cpe:2.3:a:git-scm:git:2.52.0:*:*:*:*:*:*:*",
                    },
                ],
            },
        ],
    }
    source_files["runtime-components.spdx.json"] = (
        json.dumps(component_sbom, sort_keys=True) + "\n"
    ).encode()
    for name, content in source_files.items():
        (runtime_sources / name).write_bytes(content)
    source_manifest = {
        "schemaVersion": 1,
        "digestAlgorithm": "sha256",
        "files": [
            {
                "path": name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(source_files.items())
        ],
    }
    source_manifest_bytes = (json.dumps(source_manifest, sort_keys=True) + "\n").encode()
    (runtime_sources / "SOURCE-MANIFEST.json").write_bytes(source_manifest_bytes)

    source_evidence = root / "source-evidence"
    source_evidence.mkdir()
    source_artifact_manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"digest": "sha256:" + "7" * 64, "size": 1},
        "layers": [{"digest": "sha256:" + "8" * 64, "size": 1}],
    }
    source_artifact_bytes = json.dumps(source_artifact_manifest, separators=(",", ":")).encode()
    source_digest = f"sha256:{hashlib.sha256(source_artifact_bytes).hexdigest()}"
    source_reference = f"ghcr.io/parth2412/attest@{source_digest}"
    source_evidence_files = {
        "runtime-components.openvex.json": source_files["runtime-components.openvex.json"],
        "runtime-components.spdx.json": source_files["runtime-components.spdx.json"],
        "source-artifact-digest.txt": f"{source_digest}\n".encode(),
        "source-artifact-manifest.json": source_artifact_bytes,
        "source-artifact-reference.txt": f"{source_reference}\n".encode(),
        "source-attestation-verification.json": b'{"verified":true}\n',
        "source-attestation.jsonl": b'{"bundle":"present"}\n',
        "source-manifest.json": source_manifest_bytes,
    }
    for name, content in source_evidence_files.items():
        (source_evidence / name).write_bytes(content)

    component_scan = root / "grype-runtime-components.json"
    component_scan.write_text(
        json.dumps(
            {
                "matches": [],
                "source": {
                    "type": "sbom-file",
                    "target": "/source/runtime-components.spdx.json",
                },
                "descriptor": {
                    "name": "grype",
                    "version": "0.107.0",
                    "configuration": {"match": {"stock": {"using-cpes": True}}},
                    "db": {
                        "status": {
                            "valid": True,
                            "built": "2026-10-13T06:35:20Z",
                            "from": "https://grype.anchore.io/databases/example",
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    current_context = root / "current-context.json"
    current_context.write_text(json.dumps(context_manifest), encoding="utf-8")
    action_manifest = root / "action.yml"
    action_manifest.write_text(
        f"runs:\n  using: docker\n  image: docker://ghcr.io/parth2412/attest@{image_digest}\n",
        encoding="utf-8",
    )
    return (
        evidence,
        source_evidence,
        runtime_sources,
        component_scan,
        current_context,
        action_manifest,
        context_digest,
        image_digest,
    )


def _validate_candidate(
    evidence: Path,
    source_evidence: Path,
    runtime_sources: Path,
    component_scan: Path,
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
            "--source-evidence-directory",
            str(source_evidence),
            "--runtime-sources",
            str(runtime_sources),
            "--component-scan",
            str(component_scan),
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
@pytest.mark.ac("AC-F11-310")
def test_release_candidate_validator_accepts_exact_reviewed_evidence(tmp_path: Path) -> None:
    result = _validate_candidate(*_candidate_fixture(tmp_path))
    assert result.returncode == 0, result.stderr
    assert (
        "candidate evidence: validated exact reviewed context, source, and image" in result.stdout
    )


@pytest.mark.ac("AC-F11-150")
@pytest.mark.parametrize(
    ("target", "replacement", "message"),
    [
        ("context-digest.txt", "sha256:" + "1" * 64 + "\n", "context digest mismatch"),
        ("image-digest.txt", "sha256:" + "2" * 64 + "\n", "image digest mismatch"),
        ("sbom.spdx.json", "{}", "invalid SBOM platform evidence"),
        ("provenance.slsa.json", "{}", "invalid provenance platform evidence"),
        ("layers-linux-amd64.json", "{}", "invalid candidate linux/amd64 layer evidence"),
    ],
)
def test_release_candidate_validator_rejects_mismatched_evidence(
    tmp_path: Path, target: str, replacement: str, message: str
) -> None:
    fixture = _candidate_fixture(tmp_path)
    evidence = fixture[0]
    (evidence / target).write_text(replacement, encoding="utf-8")
    result = _validate_candidate(*fixture)
    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.ac("AC-F11-270")
@pytest.mark.ac("AC-F11-310")
@pytest.mark.parametrize(
    ("target", "replacement", "message"),
    [
        ("git-2.52.0.tar.xz", b"changed", "source manifest mismatch"),
        (
            "runtime-components.spdx.json",
            b'{"spdxVersion":"SPDX-2.3","packages":[]}\n',
            "source manifest mismatch",
        ),
        (
            "runtime-components.openvex.json",
            b'{"statements":[]}\n',
            "source manifest mismatch",
        ),
    ],
)
def test_release_candidate_validator_rejects_source_drift(
    tmp_path: Path, target: str, replacement: bytes, message: str
) -> None:
    fixture = _candidate_fixture(tmp_path)
    runtime_sources = fixture[2]
    (runtime_sources / target).write_bytes(replacement)

    result = _validate_candidate(*fixture)

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
