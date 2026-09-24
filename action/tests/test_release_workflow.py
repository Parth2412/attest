"""F-11 protected release workflow and candidate-promotion contracts."""

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
CI_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/ci.yml"
PATCH_RELEASE_MANIFEST: Final[Path] = REPOSITORY_ROOT / "release/patches/0.1.1.toml"
RELEASE_CONFIG: Final[Path] = REPOSITORY_ROOT / "release/attest-release-config.yaml"
RELEASE_POLICY: Final[Path] = REPOSITORY_ROOT / "release/attest-release-policy.yaml"
VALIDATOR: Final[Path] = REPOSITORY_ROOT / "scripts/validate_release_candidate.py"
PUBLISHED_VERIFIER: Final[Path] = REPOSITORY_ROOT / "scripts/verify_published_release.py"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}
RELEASE_IDENTITY: Final[str] = (
    "https://github.com/Parth2412/attest/.github/workflows/release.yml@refs/heads/main"
)
OIDC_ISSUER: Final[str] = "https://token.actions.githubusercontent.com"


def _workflow() -> dict[Any, Any]:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _ci_workflow() -> dict[Any, Any]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
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


@pytest.mark.ac("AC-F11-170")
def test_release_workflow_is_manual_main_only_and_has_separated_authority() -> None:
    """REQ-F11-170: patch publication is manual, ordered, and least privileged."""
    workflow = _workflow()
    assert _triggers(workflow) == {
        "workflow_dispatch": {
            "inputs": {
                "prior_publication_run_id": {
                    "description": "Prior release run that published the exact PyPI artifacts",
                    "required": False,
                    "type": "string",
                }
            }
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "release-v0.1.1",
        "cancel-in-progress": False,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "build-cli",
        "smoke-cli",
        "attest-artifacts",
        "inspect-publication",
        "publish-cli",
        "verify-published-cli",
        "dogfood",
        "publish-release",
    }
    assert jobs["build-cli"]["needs"] == "preflight"
    assert jobs["smoke-cli"]["needs"] == "build-cli"
    assert jobs["attest-artifacts"]["needs"] == ["build-cli", "smoke-cli"]
    assert jobs["inspect-publication"]["needs"] == ["build-cli", "smoke-cli"]
    assert jobs["publish-cli"]["needs"] == [
        "attest-artifacts",
        "inspect-publication",
        "smoke-cli",
    ]
    assert jobs["verify-published-cli"]["needs"] == [
        "attest-artifacts",
        "inspect-publication",
        "publish-cli",
    ]
    assert jobs["dogfood"]["needs"] == "verify-published-cli"
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "verify-published-cli",
    ]
    assert jobs["dogfood"]["if"] == ("always() && needs.verify-published-cli.result == 'success'")
    assert jobs["publish-release"]["if"] == (
        "always() && needs.attest-artifacts.result == 'success' && "
        "needs.dogfood.result == 'success' && "
        "needs.verify-published-cli.result == 'success'"
    )

    assert jobs["preflight"]["if"] == (
        "github.repository == 'Parth2412/attest' && "
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert jobs["preflight"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert jobs["build-cli"]["permissions"] == {"contents": "read"}
    assert jobs["inspect-publication"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert jobs["publish-cli"]["permissions"] == {
        "actions": "read",
        "id-token": "write",
    }
    assert jobs["publish-cli"]["environment"] == {
        "name": "pypi-attest-cli",
        "url": "https://pypi.org/p/attest-cli",
    }
    assert jobs["dogfood"]["permissions"] == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
    }
    assert jobs["publish-release"]["permissions"] == {
        "actions": "read",
        "contents": "write",
    }

    action_references = _uses(workflow)
    assert action_references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in action_references)
    rendered = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in rendered
    assert "pull_request_target" not in rendered
    assert "docker build " not in rendered
    assert "imagetools create" not in rendered


@pytest.mark.ac("AC-F11-170")
def test_release_preflight_revalidates_the_patch_scope_and_controls() -> None:
    """REQ-F11-170: the patch retains immutable first-release runtime artifacts."""
    workflow = _workflow()
    preflight = workflow["jobs"]["preflight"]
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.1",
        "PRODUCT_TAG": "v0.1.1",
        "ACTION_VERSION_TAG": "v1.0.1",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "REVIEWED_IMAGE_DIGEST": (
            "sha256:0e5073cb4f2a9cc484f15aded43b7f0b8ac432a0a8b31fc401b7e361cd0509f3"
        ),
        "FIRST_RELEASE_SHA": "a1c59cc67bf67aba22ffca876309f855ea8663af",
    }
    commands = "\n".join(
        step.get("run", "") for step in preflight["steps"] if isinstance(step, dict)
    )
    for fragment in (
        "repos/${GITHUB_REPOSITORY}/rulesets",
        "repos/${GITHUB_REPOSITORY}/environments/pypi-attest-cli",
        '"refs/tags/v0.1.0"',
        '"refs/tags/v1.0.0"',
        '"refs/tags/v0.1.1"',
        '"refs/tags/v1.0.1"',
        ".can_admins_bypass == false",
        "login: .reviewer.login",
        "actions/workflows/ci.yml/runs?branch=main&event=push",
        "releases/tags/v0.1.0",
        ".immutable == true",
        "https://pypi.org/pypi/attest-cli/0.1.0/json",
        'test "$(git tag --points-at "${FIRST_RELEASE_SHA}"',
        'test "${current_image}" = "${IMAGE_NAME}@${REVIEWED_IMAGE_DIGEST}"',
        'if grep -F "github." action/action.yml',
        "docker buildx imagetools inspect",
    ):
        assert fragment in commands


@pytest.mark.ac("AC-F11-170")
def test_release_builds_once_and_publishes_only_the_cli_patch() -> None:
    """REQ-F11-170: PyPI authority receives only one validated CLI patch artifact."""
    workflow = _workflow()
    jobs = workflow["jobs"]
    build_commands = "\n".join(
        step.get("run", "") for step in jobs["build-cli"]["steps"] if isinstance(step, dict)
    )
    assert build_commands.count("uv build --package attest-cli") == 1
    for distribution in (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-export",
    ):
        assert f"uv build --package {distribution}" not in build_commands
    assert "scripts/validate_release_artifacts.py" in build_commands
    assert "--manifest release/patches/0.1.1.toml" in build_commands
    assert "sort --key=2 --output=SHA256SUMS SHA256SUMS" in build_commands

    smoke = jobs["smoke-cli"]
    assert smoke["strategy"]["matrix"] == {"python": ["3.12", "3.13"]}
    smoke_commands = "\n".join(
        step.get("run", "") for step in smoke["steps"] if isinstance(step, dict)
    )
    for fragment in (
        "dist/attest_cli-0.1.1-py3-none-any.whl",
        'metadata.version("attest-cli") == "0.1.1"',
        'metadata.version(distribution) == "0.1.0"',
        "attest --help",
    ):
        assert fragment in smoke_commands

    publish = jobs["publish-cli"]
    assert publish["if"] == ("needs.inspect-publication.outputs.publication-required == 'true'")
    publication = _step(publish, "Publish the CLI patch with Trusted Publishing")
    assert publication["uses"] == (
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
    )
    assert publication["with"] == {
        "packages-dir": "dist/",
        "verify-metadata": True,
        "skip-existing": False,
        "print-hash": True,
        "attestations": True,
    }
    assert publish["steps"][-1] == publication

    verify = jobs["verify-published-cli"]
    assert verify["if"] == (
        "always() && needs.attest-artifacts.result == 'success' && "
        "needs.inspect-publication.result == 'success' && "
        "(needs.publish-cli.result == 'success' || "
        "needs.publish-cli.result == 'skipped')"
    )
    assert verify["strategy"]["matrix"] == {"python": ["3.12", "3.13"]}
    verify_commands = _step(verify, "Verify public CLI bytes and clean installation")["run"]
    for fragment in (
        "scripts/verify_published_release.py",
        "--manifest release/patches/0.1.1.toml",
        '--version "${PRODUCT_VERSION}"',
        '"attest-cli==${PRODUCT_VERSION}"',
        'metadata.version("attest-cli") == "0.1.1"',
        'metadata.version(distribution) == "0.1.0"',
    ):
        assert fragment in verify_commands


@pytest.mark.ac("AC-F11-170")
def test_release_recovery_proves_exact_public_bytes_and_prior_oidc_authority() -> None:
    """REQ-F11-170: an accepted patch resumes without acquiring upload authority again."""
    workflow = _workflow()
    inspection = workflow["jobs"]["inspect-publication"]
    commands = "\n".join(
        step.get("run", "") for step in inspection["steps"] if isinstance(step, dict)
    )
    for fragment in (
        "https://pypi.org/pypi/attest-cli/0.1.1/json",
        "scripts/verify_published_release.py",
        "publication_required=false",
        "publication_required=true",
        "an existing patch requires its prior run ID",
        "prior run ID supplied for an absent patch",
        "actions/runs/${PRIOR_PUBLICATION_RUN_ID}",
        'git merge-base --is-ancestor "${prior_sha}" "${GITHUB_SHA}"',
        '.name == "publish-cli" and .conclusion == "success"',
        '"authentication": "oidc-trusted-publishing"',
        '"environment": "pypi-attest-cli"',
        "prior Trusted Publishing evidence mismatch",
    ):
        assert fragment in commands

    retrieval = _step(inspection, "Retrieve the prior Trusted Publishing evidence")
    assert retrieval["if"] == "steps.inspect.outputs.publication-required == 'false'"
    assert retrieval["with"] == {
        "name": "trusted-publisher-evidence-attest-cli-v0.1.1",
        "path": "prior-trusted-publisher",
        "run-id": "${{ inputs.prior_publication_run_id }}",
        "github-token": "${{ github.token }}",
    }


@pytest.mark.ac("AC-F11-170")
def test_ci_validates_the_split_library_store_and_cli_versions() -> None:
    """REQ-F11-170/190: CI validates unchanged libraries and both patch packages."""
    package_job = _ci_workflow()["jobs"]["package-contract"]
    build_commands = _step(package_job, "Build and validate the exact package artifacts")["run"]
    for fragment in (
        "build/library-dist",
        "--manifest release/patches/0.1.3-unchanged-libraries.toml",
        "build/store-dist",
        "--manifest release/patches/0.1.1-store.toml",
        "build/cli-dist",
        "--manifest release/patches/0.1.3.toml",
    ):
        assert fragment in build_commands
    smoke_step = _step(package_job, "Install and smoke-test the wheels in a clean environment")
    install_commands = smoke_step["run"]
    assert "build/library-dist/*.whl" in install_commands
    assert "build/store-dist/*.whl" in install_commands
    assert "build/cli-dist/*.whl" in install_commands


@pytest.mark.ac("AC-F11-170")
def test_release_attests_artifacts_and_dogfoods_production_identity() -> None:
    """REQ-F11-170: the patch artifacts and source correction are publicly attributable."""
    workflow = _workflow()
    jobs = workflow["jobs"]
    attestation = _step(jobs["attest-artifacts"], "Attest the source and release artifacts")
    assert attestation["with"] == {"subject-path": "release-assets/*"}

    dogfood_commands = "\n".join(
        step.get("run", "") for step in jobs["dogfood"]["steps"] if isinstance(step, dict)
    )
    for fragment in (
        "attest-cli==${PRODUCT_VERSION}",
        "attest run",
        "--signing-environment production",
        "--verify-environment production",
        '--identity "${RELEASE_IDENTITY}"',
        '--issuer "${OIDC_ISSUER}"',
        "attest verify",
        "release/attest-release-config.yaml",
        "release/attest-release-policy.yaml",
    ):
        assert fragment in dogfood_commands

    dogfood_evidence = _step(jobs["dogfood"], "Retain attest dogfood evidence")
    assert dogfood_evidence["with"] == {
        "name": "attest-release-evidence-v0.1.1",
        "path": "build/release-evidence",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }

    retained_index = _step(
        jobs["publish-release"],
        "Assemble the retained release evidence index",
    )["run"]
    assert 'any(part.startswith(".") for part in relative.parts)' in retained_index
    assert "hidden retained evidence is forbidden" in retained_index
    assert '"imageDigest": os.environ["REVIEWED_IMAGE_DIGEST"]' in retained_index
    assert '"majorTagMoved": False' in retained_index

    config = yaml.safe_load(RELEASE_CONFIG.read_text(encoding="utf-8"))
    assert config == {
        "version": 1,
        "repository": {"path": ".", "backend": "subprocess"},
        "signing": {"environment": "production", "timeoutSeconds": 120},
        "verification": {
            "identity": RELEASE_IDENTITY,
            "issuer": OIDC_ISSUER,
            "environment": "production",
            "offline": False,
        },
        "policy": {"path": "release/attest-release-policy.yaml"},
        "storage": {
            "backend": "filesystem",
            "directory": "build/release-evidence/store",
            "fallbackDirectory": "build/release-evidence/fallback",
        },
    }
    policy = yaml.safe_load(RELEASE_POLICY.read_text(encoding="utf-8"))
    assert policy == {
        "version": 1,
        "policies": [
            {
                "id": "ATTEST-RELEASE-001",
                "description": "Require trusted, identity-bound release provenance",
                "match": {"branches": ["main"], "paths": ["**"]},
                "require": {
                    "attestation": True,
                    "environment": {"trusted": True},
                    "signer": {"issuer": OIDC_ISSUER, "identity": RELEASE_IDENTITY},
                    "transparencyLog": True,
                },
                "onViolation": "block",
            }
        ],
    }


@pytest.mark.ac("AC-F11-170")
def test_release_tags_and_release_are_created_only_after_public_verification() -> None:
    """REQ-F11-170: immutable patch tags precede the separately proven major move."""
    workflow = _workflow()
    publish = workflow["jobs"]["publish-release"]
    commands = "\n".join(step.get("run", "") for step in publish["steps"] if isinstance(step, dict))
    assert "refs/tags/${ACTION_VERSION_TAG}" in commands
    assert 'refs/tags/v1"' not in commands
    assert 'gh release create "${PRODUCT_TAG}"' in commands
    assert '--target "${GITHUB_SHA}"' in commands
    assert "--draft" in commands
    assert 'gh release edit "${PRODUCT_TAG}" --draft=false --latest' in commands
    assert ".immutable == true" in commands
    assert "${GITHUB_SHA}" in commands
    publish_product = commands.index('gh release edit "${PRODUCT_TAG}" --draft=false --latest')
    create_action_tag = commands.index('"refs/tags/${ACTION_VERSION_TAG}"')
    assert publish_product < create_action_tag


def _candidate_fixture(root: Path) -> tuple[Path, Path, Path, str, str]:
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

    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
            {"platform": {"os": "unknown", "architecture": "unknown"}},
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
    fixture = _candidate_fixture(tmp_path)
    result = _validate_candidate(*fixture)
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


def _published_fixture(root: Path) -> tuple[Path, Path]:
    artifacts = root / "release-assets"
    index = root / "index" / "pypi"
    public_files = root / "public-files"
    artifacts.mkdir()
    public_files.mkdir()
    distributions = (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-cli",
    )
    for distribution in distributions:
        normalized = distribution.replace("-", "_")
        files = (
            (f"{normalized}-0.1.0-py3-none-any.whl", "bdist_wheel"),
            (f"{normalized}-0.1.0.tar.gz", "sdist"),
        )
        urls: list[dict[str, object]] = []
        for filename, package_type in files:
            content = filename.encode()
            (artifacts / filename).write_bytes(content)
            public_file = public_files / filename
            public_file.write_bytes(content)
            urls.append(
                {
                    "filename": filename,
                    "packagetype": package_type,
                    "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                    "size": len(content),
                    "url": public_file.as_uri(),
                    "yanked": False,
                }
            )
        document = {
            "info": {"name": distribution, "version": "0.1.0"},
            "urls": urls,
        }
        endpoint = index / distribution / "0.1.0"
        endpoint.mkdir(parents=True)
        (endpoint / "json").write_text(json.dumps(document), encoding="utf-8")
    return artifacts, root / "index"


def _verify_published(
    artifacts: Path,
    index: Path,
    *distributions: str,
    version: str = "0.1.0",
    manifest: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(PUBLISHED_VERIFIER),
        str(artifacts),
        "--version",
        version,
        "--index-base-url",
        index.as_uri(),
        "--attempts",
        "1",
        "--delay-seconds",
        "0",
    ]
    if manifest is not None:
        arguments.extend(("--manifest", str(manifest)))
    for distribution in distributions:
        arguments.extend(("--distribution", distribution))
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-170")
def test_published_release_verifier_accepts_exact_cli_patch(tmp_path: Path) -> None:
    artifacts = tmp_path / "release-assets"
    index = tmp_path / "index" / "pypi" / "attest-cli" / "0.1.1"
    public_files = tmp_path / "public-files"
    artifacts.mkdir()
    index.mkdir(parents=True)
    public_files.mkdir()
    records: list[dict[str, object]] = []
    for filename, package_type in (
        ("attest_cli-0.1.1-py3-none-any.whl", "bdist_wheel"),
        ("attest_cli-0.1.1.tar.gz", "sdist"),
    ):
        content = filename.encode()
        (artifacts / filename).write_bytes(content)
        public_file = public_files / filename
        public_file.write_bytes(content)
        records.append(
            {
                "filename": filename,
                "packagetype": package_type,
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                "size": len(content),
                "url": public_file.as_uri(),
                "yanked": False,
            }
        )
    (index / "json").write_text(
        json.dumps(
            {
                "info": {"name": "attest-cli", "version": "0.1.1"},
                "urls": records,
            }
        ),
        encoding="utf-8",
    )

    result = _verify_published(
        artifacts,
        tmp_path / "index",
        version="0.1.1",
        manifest=PATCH_RELEASE_MANIFEST,
    )

    assert result.returncode == 0, result.stderr
    assert "published release: verified 1 distributions and 2 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-170")
def test_published_release_verifier_rejects_an_unsafe_patch_manifest(tmp_path: Path) -> None:
    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    manifest = tmp_path / "unsafe.toml"
    manifest.write_text(
        '[release]\nversion = "0.1.1"\ndistributions = ["../attest-cli"]\n',
        encoding="utf-8",
    )

    result = _verify_published(
        artifacts,
        tmp_path / "index",
        version="0.1.1",
        manifest=manifest,
    )

    assert result.returncode == 1
    assert "release package manifest contains an invalid distribution name" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_accepts_exact_public_artifacts(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(artifacts, index)
    assert result.returncode == 0, result.stderr
    assert "published release: verified 6 distributions and 12 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_accepts_strict_bootstrap_subset(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(
        artifacts,
        index,
        "attest-core",
        "attest-collect",
        "attest-sign",
    )
    assert result.returncode == 0, result.stderr
    assert "published release: verified 3 distributions and 6 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-140")
@pytest.mark.parametrize(
    "distributions",
    [("attest-core", "attest-core"), ("attest-export",)],
)
def test_published_release_verifier_rejects_invalid_bootstrap_subset(
    tmp_path: Path,
    distributions: tuple[str, ...],
) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(artifacts, index, *distributions)
    assert result.returncode == 1
    assert "requested distributions are not a unique release-package subset" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_rejects_a_public_hash_mismatch(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    document_path = index / "pypi/attest-cli/0.1.0/json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["urls"][0]["digests"]["sha256"] = "0" * 64
    document_path.write_text(json.dumps(document), encoding="utf-8")
    result = _verify_published(artifacts, index)
    assert result.returncode == 1
    assert "public artifact hash mismatch" in result.stderr


@pytest.mark.ac("AC-F11-170")
def test_published_release_verifier_rejects_tampered_downloaded_bytes(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    document = json.loads((index / "pypi/attest-cli/0.1.0/json").read_text(encoding="utf-8"))
    public_file = Path(document["urls"][0]["url"].removeprefix("file://"))
    public_file.write_bytes(b"tampered")

    result = _verify_published(artifacts, index)

    assert result.returncode == 1
    assert "downloaded public artifact mismatch" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_rejects_published_export(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    endpoint = index / "pypi/attest-export"
    endpoint.mkdir(parents=True)
    (endpoint / "json").write_text(
        json.dumps({"info": {"name": "attest-export", "version": "0.1.0"}}),
        encoding="utf-8",
    )
    result = _verify_published(artifacts, index)
    assert result.returncode == 1
    assert "attest-export must remain unpublished" in result.stderr
