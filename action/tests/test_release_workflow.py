"""F-11 bounded storage-correction release workflow contracts."""

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
RELEASE_NOTES: Final[Path] = REPOSITORY_ROOT / "release/RELEASE_NOTES-v0.1.7.md"
VALIDATOR: Final[Path] = REPOSITORY_ROOT / "scripts/validate_release_candidate.py"
IMAGE_DIGEST: Final[str] = "sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356"
CONTEXT_DIGEST: Final[str] = (
    "sha256:580c0b7881882817ae7ca65dfe1bbdcd06c5bea77556c8b77ff5b04e11cacc73"
)
CANDIDATE_SHA: Final[str] = "62b72c2537176c84bc232f727f223a9ea21ae80b"
SOURCE_ARTIFACT_DIGEST: Final[str] = (
    "sha256:7472c920350b428c850a6f18f2e17693431b0e89761ef52498b009b0ea447805"
)
PRIOR_RELEASE_SHA: Final[str] = "e693e6b60afdf9c667a913faa4f9652bfd6dc050"
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


@pytest.mark.ac("AC-F11-320")
def test_release_is_closed_to_the_approved_storage_correction() -> None:
    """REQ-F11-320: v0.1.7 publishes only the approved store and CLI patches."""
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
                "prior_store_publication_run_id": {
                    "description": (
                        "Prior release run that published the exact attest-store artifacts"
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
        "group": "release-v0.1.7",
        "cancel-in-progress": False,
    }
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.7",
        "STORE_VERSION": "0.1.2",
        "CLI_VERSION": "0.1.5",
        "PRODUCT_TAG": "v0.1.7",
        "ACTION_VERSION_TAG": "v1.0.7",
        "SIGN_VERSION": "0.1.1",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "PRIOR_RELEASE_SHA": PRIOR_RELEASE_SHA,
        "REVIEWED_CANDIDATE_RUN_ID": 40114789855,
        "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
        "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
        "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "build-patches",
        "smoke-patches",
        "attest-patches",
        "inspect-publication",
        "publish-store",
        "publish-cli",
        "verify-published",
        "assemble-assets",
        "attest-artifacts",
        "promote-image",
        "dogfood",
        "publish-release",
    }
    assert jobs["build-patches"]["needs"] == "preflight"
    assert jobs["smoke-patches"]["needs"] == "build-patches"
    assert jobs["attest-patches"]["needs"] == ["build-patches", "smoke-patches"]
    assert jobs["inspect-publication"]["needs"] == ["build-patches", "smoke-patches"]
    for job_name in ("publish-store", "publish-cli"):
        assert jobs[job_name]["needs"] == [
            "attest-patches",
            "inspect-publication",
            "smoke-patches",
        ]
    assert jobs["verify-published"]["needs"] == [
        "attest-patches",
        "inspect-publication",
        "publish-store",
        "publish-cli",
    ]
    assert jobs["assemble-assets"]["needs"] == [
        "build-patches",
        "preflight",
        "verify-published",
    ]
    assert jobs["attest-artifacts"]["needs"] == "assemble-assets"
    assert jobs["promote-image"]["needs"] == ["preflight", "verify-published"]
    assert jobs["dogfood"]["needs"] == ["promote-image", "verify-published"]
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "inspect-publication",
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
    for job_name, environment in (
        ("publish-store", "pypi-attest-store"),
        ("publish-cli", "pypi-attest-cli"),
    ):
        assert jobs[job_name]["permissions"] == {
            "actions": "read",
            "id-token": "write",
        }
        assert jobs[job_name]["environment"]["name"] == environment

    rendered = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("publish-sign:", "attest-sign==0.1.2"):
        assert forbidden not in rendered
    assert "secrets." not in rendered
    assert "pull_request_target" not in rendered
    assert "docker build " not in rendered
    assert rendered.count("docker buildx imagetools create") == 1
    assert "git diff --quiet" not in rendered
    assert '"${REVIEWED_CANDIDATE_SOURCE_SHA}:uv.lock"' in rendered
    assert '"$(git hash-object uv.lock)"' in rendered


@pytest.mark.ac("AC-F11-320")
def test_release_builds_and_publishes_only_store_and_cli() -> None:
    """REQ-F11-320: artifacts are built once and published by isolated authorities."""
    jobs = _workflow()["jobs"]
    build = _commands(jobs["build-patches"])
    assert build.count("uv build --package attest-store") == 1
    assert build.count("uv build --package attest-cli") == 1
    for distribution in (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-policy",
        "attest-export",
    ):
        assert f"uv build --package {distribution}" not in build
    for fragment in (
        "release/patches/0.1.2-store.toml",
        "release/patches/0.1.5.toml",
        "store-distributions-v0.1.2",
        "cli-distributions-v0.1.5",
    ):
        assert fragment in str(jobs["build-patches"])

    smoke = jobs["smoke-patches"]
    assert smoke["strategy"] == {
        "fail-fast": False,
        "matrix": {"python": ["3.12", "3.13"]},
    }
    for fragment in (
        "attest_store-0.1.2-py3-none-any.whl",
        "attest_cli-0.1.5-py3-none-any.whl",
        'metadata.version("attest-store") == "0.1.2"',
        'metadata.version("attest-cli") == "0.1.5"',
    ):
        assert fragment in _commands(smoke)

    patch_attestation = _step(jobs["attest-patches"], "Attest the exact Python release assets")
    assert patch_attestation["with"] == {"subject-path": "python-release-assets/*"}

    for job_name, output_name, step_name in (
        (
            "publish-store",
            "store-publication-required",
            "Publish the store patch with Trusted Publishing",
        ),
        (
            "publish-cli",
            "cli-publication-required",
            "Publish the CLI patch with Trusted Publishing",
        ),
    ):
        publish = jobs[job_name]
        assert publish["if"] == f"needs.inspect-publication.outputs.{output_name} == 'true'"
        step = _step(publish, step_name)
        assert step["uses"] == (
            "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
        )
        assert step["with"]["skip-existing"] is False
        assert publish["steps"][-1] == step

    verify = jobs["verify-published"]
    assert verify["strategy"] == {
        "fail-fast": False,
        "matrix": {"python": ["3.12", "3.13"]},
    }
    commands = _commands(verify)
    for fragment in (
        "scripts/verify_published_release.py",
        "release/patches/0.1.2-store.toml",
        "release/patches/0.1.5.toml",
        '"attest-store==${STORE_VERSION}"',
        '"attest-cli==${CLI_VERSION}"',
        'metadata.version("attest-store") == "0.1.2"',
        'metadata.version("attest-cli") == "0.1.5"',
        '"minimumSafeCertifi": "2026.10.19"',
        'for excluded in ("virtualenv", "python-discovery")',
        '"pythonDistributionsPublished": [',
        "build/public-package-smoke/bin/attest --help",
    ):
        assert fragment in commands


@pytest.mark.ac("AC-F11-320")
def test_release_recovery_requires_exact_bytes_and_original_oidc_authority() -> None:
    """REQ-F11-320: a partial publication resumes only from proven prior authority."""
    inspection = _workflow()["jobs"]["inspect-publication"]
    commands = _commands(inspection)
    for fragment in (
        '"https://pypi.org/pypi/${distribution}/${version}/json"',
        'attest-store "${STORE_VERSION}" store-dist',
        'attest-cli "${CLI_VERSION}" cli-dist',
        "scripts/verify_published_release.py",
        "existing ${distribution} requires its prior run ID",
        "prior run ID supplied for absent ${distribution}",
        "actions/runs/${run_id}",
        'git merge-base --is-ancestor "${prior_sha}" "${GITHUB_SHA}"',
        '.name == $job_name and .conclusion == "success"',
        '"authentication": "oidc-trusted-publishing"',
        '"pypi-attest-store"',
        '"pypi-attest-cli"',
        "prior Trusted Publishing evidence mismatch",
    ):
        assert fragment in commands

    for step_name, output_name, distribution, input_name in (
        (
            "Retrieve prior store Trusted Publishing evidence",
            "store-publication-required",
            "attest-store",
            "prior_store_publication_run_id",
        ),
        (
            "Retrieve prior CLI Trusted Publishing evidence",
            "cli-publication-required",
            "attest-cli",
            "prior_cli_publication_run_id",
        ),
    ):
        retrieval = _step(inspection, step_name)
        assert retrieval["if"] == f"steps.inspect.outputs.{output_name} == 'false'"
        assert retrieval["with"] == {
            "name": f"trusted-publisher-evidence-{distribution}-v0.1.7",
            "path": f"prior-trusted-publisher-{distribution.removeprefix('attest-')}",
            "run-id": f"${{{{ inputs.{input_name} }}}}",
            "github-token": "${{ github.token }}",
        }


@pytest.mark.ac("AC-F11-320")
def test_release_recovery_continues_after_publication_jobs_are_skipped() -> None:
    """REQ-F11-320: proven prior publications must not skip release completion."""
    assemble = _workflow()["jobs"]["assemble-assets"]
    observed = " ".join(assemble["if"].split())
    assert observed == (
        "always() && "
        "needs.build-patches.result == 'success' && "
        "needs.preflight.result == 'success' && "
        "needs.verify-published.result == 'success'"
    )

    attest = _workflow()["jobs"]["attest-artifacts"]
    assert " ".join(attest["if"].split()) == (
        "always() && needs.assemble-assets.result == 'success'"
    )


@pytest.mark.ac("AC-F11-320")
def test_release_progresses_only_after_exact_publication_verification() -> None:
    """REQ-F11-320: promotion and dogfood require exact public package bytes."""
    jobs = _workflow()["jobs"]
    expected_conditions = {
        "promote-image": (
            "always() && "
            "needs.preflight.result == 'success' && "
            "needs.verify-published.result == 'success'"
        ),
        "dogfood": (
            "always() && "
            "needs.promote-image.result == 'success' && "
            "needs.verify-published.result == 'success'"
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
        "performance run ${index} ID must be a positive decimal integer",
        "performance run IDs must be strictly increasing",
        "performance run ${index} does not match the required event, exact main commit, "
        "and successful attempt-1 contract",
        "actions/workflows/action-performance.yml/runs?branch=main&per_page=100",
        "latest three exact-commit performance runs are not the supplied sequence",
    ):
        assert fragment in validate["run"]

    for index in range(1, 4):
        download = _step(preflight, f"Download performance evidence {index}")
        assert download["with"] == {
            "name": f"action-performance-v1.0.7-${{{{ inputs.performance_run_id_{index} }}}}",
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
        '"org.opencontainers.image.version": "0.1.7-candidate"',
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
        "name": "release-corresponding-source-v0.1.7",
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
        and step.get("with", {}).get("name") == "release-corresponding-source-v0.1.7"
    )
    assert source_download["with"]["path"] == "corresponding-source"
    assert "action-corresponding-source-v1.0.7.tar.gz" in _commands(assemble)


@pytest.mark.ac("AC-F11-320")
def test_release_promotes_without_rebuild_and_dogfoods_the_public_cli() -> None:
    """REQ-F11-320: exact promotion dogfoods the newly verified public CLI."""
    jobs = _workflow()["jobs"]
    promotion = _commands(jobs["promote-image"])
    assert "docker buildx imagetools create" in promotion
    assert '"${IMAGE_NAME}@${REVIEWED_IMAGE_DIGEST}"' in promotion
    assert "docker build " not in promotion
    assert "build-push-action" not in promotion

    dogfood = _commands(jobs["dogfood"])
    for fragment in (
        '"attest-cli==${CLI_VERSION}"',
        'metadata.version("attest-cli") != "0.1.5"',
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


@pytest.mark.ac("AC-F11-320")
def test_release_attests_assets_and_keeps_v1_on_v1_0_6() -> None:
    """REQ-F11-320: immutable v0.1.7/v1.0.7 publish before major-tag movement."""
    jobs = _workflow()["jobs"]
    repository_controls = _step(
        jobs["preflight"], "Validate source and immutable repository controls"
    )["run"]
    for fragment in (
        "for distribution in attest-store attest-cli; do",
        ".can_admins_bypass == false",
        '"refs/tags/v0.1.7"',
        '"refs/tags/v1.0.7"',
        "gh api --paginate --slurp",
        '"repos/${GITHUB_REPOSITORY}/releases?per_page=100"',
        "[.[][] | select(.tag_name == $tag)] as $matches",
        "$matches[0].draft == true and $matches[0].immutable == false",
        "$matches[0].draft == false and $matches[0].immutable == true",
    ):
        assert fragment in repository_controls

    attestation = _step(jobs["attest-artifacts"], "Attest the complete release assets")
    assert attestation["with"] == {"subject-path": "release-assets/*"}
    publish = _commands(jobs["publish-release"])
    for fragment in (
        "--notes-file release/RELEASE_NOTES-v0.1.7.md",
        '"repos/${GITHUB_REPOSITORY}/releases?per_page=100"',
        '"repos/${GITHUB_REPOSITORY}/releases/${release_id}"',
        "jq -n '{draft: false, make_latest: \"true\"}'",
        '--field ref="refs/tags/${ACTION_VERSION_TAG}"',
        ".immutable == true",
        '"majorTagMoved": False',
        '"pythonDistributionsPublished": ["attest-store==0.1.2", "attest-cli==0.1.5"]',
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


@pytest.mark.ac("AC-F11-320")
def test_release_evidence_namespaces_duplicate_supporting_asset_names(
    tmp_path: Path,
) -> None:
    """REQ-F11-320: distinct retained evidence cannot overwrite by basename."""
    publish = _step(
        _workflow()["jobs"]["publish-release"],
        "Assemble the immutable release evidence index",
    )["run"]
    marker = "python3 - <<'PY'\n"
    assert publish.count(marker) == 1
    script = publish.split(marker, maxsplit=1)[1].rsplit("\nPY", maxsplit=1)[0]

    retained = tmp_path / "retained"
    (retained / "release-assets").mkdir(parents=True)
    (retained / "patch-attestations").mkdir()
    (retained / "attestations").mkdir()
    (retained / "preflight" / "nested").mkdir(parents=True)
    (retained / "release-assets" / "SHA256SUMS").write_bytes(b"primary")
    (retained / "patch-attestations" / "SHA256SUMS.verification.json").write_bytes(b"patch")
    (retained / "attestations" / "SHA256SUMS.verification.json").write_bytes(b"release")
    (retained / "preflight" / "nested" / "evidence.json").write_bytes(b"nested")
    (tmp_path / "final-release-assets").mkdir()

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={
            "GITHUB_REPOSITORY": "Parth2412/attest",
            "GITHUB_RUN_ID": "40170754320",
            "GITHUB_SHA": "2b73af21f59d2088aa1991d18012fa5bf16ab601",
            "PERFORMANCE_RUN_ID_1": "40170342988",
            "PERFORMANCE_RUN_ID_2": "40170455864",
            "PERFORMANCE_RUN_ID_3": "40170533853",
            "REVIEWED_CANDIDATE_RUN_ID": "40114789855",
            "REVIEWED_CANDIDATE_SOURCE_SHA": CANDIDATE_SHA,
            "REVIEWED_CONTEXT_DIGEST": CONTEXT_DIGEST,
            "REVIEWED_IMAGE_DIGEST": IMAGE_DIGEST,
            "STORE_VERSION": "0.1.2",
            "CLI_VERSION": "0.1.5",
            "PRODUCT_TAG": "v0.1.7",
            "ACTION_VERSION_TAG": "v1.0.7",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assets = tmp_path / "final-release-assets"
    assert {path.name for path in assets.iterdir()} == {
        "SHA256SUMS",
        "attestations--SHA256SUMS.verification.json",
        "patch-attestations--SHA256SUMS.verification.json",
        "preflight--nested--evidence.json",
        "release-evidence-index.json",
    }
    assert (assets / "attestations--SHA256SUMS.verification.json").read_bytes() == b"release"
    assert (assets / "patch-attestations--SHA256SUMS.verification.json").read_bytes() == b"patch"
    index = json.loads((assets / "release-evidence-index.json").read_text(encoding="utf-8"))
    assert {asset["name"] for asset in index["assets"]} == {
        "SHA256SUMS",
        "attestations--SHA256SUMS.verification.json",
        "patch-attestations--SHA256SUMS.verification.json",
        "preflight--nested--evidence.json",
    }


@pytest.mark.ac("AC-F11-320")
def test_release_notes_state_the_bounded_artifact_set() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    for fragment in (
        "# attest 0.1.7 / GitHub Action v1.0.7",
        IMAGE_DIGEST,
        CONTEXT_DIGEST,
        CANDIDATE_SHA,
        "40114789855",
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
        "attest-store==0.1.2",
        "attest-cli==0.1.5",
        "Only these two Python distributions",
        "40086747745",
        "v1",
        "v1.0.6",
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
