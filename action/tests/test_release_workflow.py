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
    "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}
RELEASE_IDENTITY: Final[str] = (
    "https://github.com/Parth2412/attest/.github/workflows/release.yml@refs/heads/main"
)
OIDC_ISSUER: Final[str] = "https://token.actions.githubusercontent.com"
PYPI_BOOTSTRAP_WAVE_ONE: Final[list[dict[str, str]]] = [
    {
        "distribution": "attest-core",
        "artifact_prefix": "attest_core",
        "environment": "pypi",
    },
    {
        "distribution": "attest-collect",
        "artifact_prefix": "attest_collect",
        "environment": "pypi-attest-collect",
    },
    {
        "distribution": "attest-sign",
        "artifact_prefix": "attest_sign",
        "environment": "pypi-attest-sign",
    },
]
PYPI_BOOTSTRAP_WAVE_TWO: Final[list[dict[str, str]]] = [
    {
        "distribution": "attest-store",
        "artifact_prefix": "attest_store",
        "environment": "pypi-attest-store",
    },
    {
        "distribution": "attest-policy",
        "artifact_prefix": "attest_policy",
        "environment": "pypi-attest-policy",
    },
    {
        "distribution": "attest-cli",
        "artifact_prefix": "attest_cli",
        "environment": "pypi-attest-cli",
    },
]
PYPI_PUBLISHERS: Final[list[dict[str, str]]] = [
    *PYPI_BOOTSTRAP_WAVE_ONE,
    *PYPI_BOOTSTRAP_WAVE_TWO,
]


def _workflow() -> dict[Any, Any]:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
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


@pytest.mark.ac("AC-F11-150")
def test_release_workflow_is_manual_main_only_and_has_separated_authority() -> None:
    """REQ-F11-150: release publication is manual, ordered, and least privileged."""
    workflow = _workflow()
    assert _triggers(workflow) == {"workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "release-v0.1.0",
        "cancel-in-progress": False,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {
        "preflight",
        "build-distributions",
        "smoke-distributions",
        "attest-artifacts",
        "publish-pypi-bootstrap-wave-1",
        "verify-pypi-bootstrap-wave-1",
        "publish-pypi-bootstrap-wave-2",
        "promote-image",
        "verify-published",
        "dogfood",
        "publish-release",
    }
    assert jobs["build-distributions"]["needs"] == "preflight"
    assert jobs["smoke-distributions"]["needs"] == "build-distributions"
    assert jobs["attest-artifacts"]["needs"] == ["build-distributions", "smoke-distributions"]
    assert jobs["publish-pypi-bootstrap-wave-1"]["needs"] == [
        "attest-artifacts",
        "smoke-distributions",
    ]
    assert jobs["verify-pypi-bootstrap-wave-1"]["needs"] == ("publish-pypi-bootstrap-wave-1")
    assert jobs["publish-pypi-bootstrap-wave-2"]["needs"] == ("verify-pypi-bootstrap-wave-1")
    assert jobs["promote-image"]["needs"] == "publish-pypi-bootstrap-wave-2"
    assert jobs["verify-published"]["needs"] == [
        "publish-pypi-bootstrap-wave-2",
        "promote-image",
    ]
    assert jobs["dogfood"]["needs"] == "verify-published"
    assert jobs["publish-release"]["needs"] == [
        "attest-artifacts",
        "dogfood",
        "verify-published",
    ]

    assert jobs["preflight"]["if"] == (
        "github.repository == 'Parth2412/attest' && "
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert jobs["preflight"]["permissions"] == {
        "actions": "read",
        "attestations": "read",
        "contents": "read",
        "packages": "read",
    }
    assert jobs["build-distributions"]["permissions"] == {"contents": "read"}
    for publish_job in (
        "publish-pypi-bootstrap-wave-1",
        "publish-pypi-bootstrap-wave-2",
    ):
        assert jobs[publish_job]["permissions"] == {
            "actions": "read",
            "id-token": "write",
        }
    assert jobs["verify-pypi-bootstrap-wave-1"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert jobs["promote-image"]["permissions"] == {
        "contents": "read",
        "packages": "write",
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


@pytest.mark.ac("AC-F11-150")
def test_release_preflight_revalidates_the_reviewed_candidate_and_controls() -> None:
    """REQ-F11-150: release consumes the attested candidate and never a rebuild."""
    workflow = _workflow()
    preflight = workflow["jobs"]["preflight"]
    assert workflow["env"] == {
        "PRODUCT_VERSION": "0.1.0",
        "PRODUCT_TAG": "v0.1.0",
        "ACTION_VERSION_TAG": "v1.0.0",
        "ACTION_MAJOR_TAG": "v1",
        "IMAGE_NAME": "ghcr.io/parth2412/attest",
        "REVIEWED_CANDIDATE_RUN_ID": 35699845779,
        "REVIEWED_CANDIDATE_SOURCE_SHA": "22839b23597f741cb091cf10289739c7787841e7",
        "REVIEWED_IMAGE_DIGEST": (
            "sha256:0e5073cb4f2a9cc484f15aded43b7f0b8ac432a0a8b31fc401b7e361cd0509f3"
        ),
        "REVIEWED_CONTEXT_DIGEST": (
            "sha256:272e91a6ac5eb29b0646017d8e2a54ed782a69ab07ccf12467c5195bc665e914"
        ),
    }
    download = _step(preflight, "Download the reviewed candidate evidence")
    assert download["with"] == {
        "name": "action-candidate-build-${{ env.REVIEWED_CANDIDATE_SOURCE_SHA }}",
        "path": "${{ runner.temp }}/candidate-evidence",
        "github-token": "${{ github.token }}",
        "repository": "Parth2412/attest",
        "run-id": "${{ env.REVIEWED_CANDIDATE_RUN_ID }}",
    }
    commands = "\n".join(
        step.get("run", "") for step in preflight["steps"] if isinstance(step, dict)
    )
    for fragment in (
        "repos/${GITHUB_REPOSITORY}/actions/runs/${REVIEWED_CANDIDATE_RUN_ID}",
        "repos/${GITHUB_REPOSITORY}/rulesets",
        "repos/${GITHUB_REPOSITORY}/environments/${environment}",
        "pypi-attest-collect",
        "pypi-attest-sign",
        "pypi-attest-store",
        "pypi-attest-policy",
        "pypi-attest-cli",
        ".can_admins_bypass == false",
        "login: .reviewer.login",
        "scripts/prepare_action_context.py",
        "scripts/validate_release_candidate.py",
        "gh attestation verify",
        '--source-digest "${REVIEWED_CANDIDATE_SOURCE_SHA}"',
        "--source-ref refs/heads/dev",
    ):
        assert fragment in commands
    assert "repos/${GITHUB_REPOSITORY}/immutable-releases" not in commands


@pytest.mark.ac("AC-F11-140")
def test_release_builds_once_and_publishes_only_the_six_closed_distributions() -> None:
    """REQ-F11-140: PyPI authority receives one validated six-package artifact."""
    workflow = _workflow()
    jobs = workflow["jobs"]
    build_commands = "\n".join(
        step.get("run", "")
        for step in jobs["build-distributions"]["steps"]
        if isinstance(step, dict)
    )
    for distribution in (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-cli",
    ):
        assert build_commands.count(f"uv build --package {distribution}") == 1
    assert "attest-export" not in build_commands
    assert "scripts/validate_release_artifacts.py" in build_commands
    assert "sort --key=2 --output=SHA256SUMS SHA256SUMS" in build_commands
    assert build_commands.index("sort --key=2 --output=SHA256SUMS SHA256SUMS") < (
        build_commands.index("sort --check=quiet --key=2 SHA256SUMS")
    )

    smoke = jobs["smoke-distributions"]
    assert smoke["strategy"]["matrix"] == {"python": ["3.12", "3.13"]}
    smoke_commands = "\n".join(
        step.get("run", "") for step in smoke["steps"] if isinstance(step, dict)
    )
    assert "scripts/smoke_release_install.py" in smoke_commands
    assert len(PYPI_PUBLISHERS) == 6
    assert {publisher["distribution"] for publisher in PYPI_PUBLISHERS} == {
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-cli",
    }

    for job_name, wave, expected_publishers in (
        ("publish-pypi-bootstrap-wave-1", "1", PYPI_BOOTSTRAP_WAVE_ONE),
        ("publish-pypi-bootstrap-wave-2", "2", PYPI_BOOTSTRAP_WAVE_TWO),
    ):
        publish = jobs[job_name]
        assert publish["strategy"] == {
            "fail-fast": False,
            "matrix": {"include": expected_publishers},
        }
        assert publish["environment"] == {
            "name": "${{ matrix.environment }}",
            "url": "https://pypi.org/p/${{ matrix.distribution }}",
        }
        selection = _step(publish, "Select one validated distribution for bounded publication")
        assert selection["env"] == {
            "ARTIFACT_PREFIX": "${{ matrix.artifact_prefix }}",
            "BOOTSTRAP_WAVE": wave,
            "DISTRIBUTION": "${{ matrix.distribution }}",
            "PUBLISH_ENVIRONMENT": "${{ matrix.environment }}",
        }
        for fragment in (
            '"dist/${ARTIFACT_PREFIX}-${PRODUCT_VERSION}-py3-none-any.whl"',
            '"dist/${ARTIFACT_PREFIX}-${PRODUCT_VERSION}.tar.gz"',
            '"bootstrapWave": int(os.environ["BOOTSTRAP_WAVE"])',
            '"distributions": [os.environ["DISTRIBUTION"]]',
            '"environment": os.environ["PUBLISH_ENVIRONMENT"]',
        ):
            assert fragment in selection["run"]

        publication = _step(publish, "Publish one distribution with Trusted Publishing")
        assert publication["uses"] == (
            "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
        )
        assert publication["with"] == {
            "packages-dir": "publish-dist/",
            "verify-metadata": True,
            "skip-existing": False,
            "print-hash": True,
            "attestations": True,
        }
        assert publish["steps"][-1] == publication
        trusted_context = _step(publish, "Retain the Trusted Publishing context")
        assert trusted_context["with"] == {
            "name": "trusted-publisher-evidence-${{ matrix.distribution }}-v0.1.0",
            "path": "trusted-publisher-evidence",
            "if-no-files-found": "error",
            "retention-days": 90,
        }

    bootstrap_verification = jobs["verify-pypi-bootstrap-wave-1"]
    bootstrap_commands = _step(
        bootstrap_verification,
        "Verify wave one and expose the second-wave checkpoint",
    )["run"]
    for fragment in (
        "--distribution attest-core",
        "--distribution attest-collect",
        "--distribution attest-sign",
        "attest-store attest-policy attest-cli",
        "second-wave-name-status.tsv",
        'test "${status}" != "404"',
        "Register the second PyPI publisher wave",
        "Do not approve the waiting GitHub environments",
    ):
        assert fragment in bootstrap_commands
    bootstrap_evidence = _step(
        bootstrap_verification,
        "Retain first-wave public verification evidence",
    )
    assert bootstrap_evidence["with"] == {
        "name": "pypi-bootstrap-wave-one-evidence-v0.1.0",
        "path": "pypi-bootstrap-wave-one-evidence",
        "if-no-files-found": "error",
        "retention-days": 90,
    }

    verify = jobs["verify-published"]
    verify_commands = _step(verify, "Verify the public six-package release and clean installation")[
        "run"
    ]
    assert "set -euo pipefail" in verify_commands
    assert "pypi-verification-python-${{ matrix.python }}.txt" in verify_commands
    assert "clean-install-python-${{ matrix.python }}.txt" in verify_commands
    assert "installed-python-${{ matrix.python }}.txt" in verify_commands
    public_evidence = _step(verify, "Retain public package and installation evidence")
    assert public_evidence["with"] == {
        "name": "public-release-evidence-python-${{ matrix.python }}",
        "path": "public-release-evidence",
        "if-no-files-found": "error",
        "retention-days": 90,
    }


@pytest.mark.ac("AC-F11-090")
def test_release_attests_artifacts_and_dogfoods_production_identity() -> None:
    """REQ-F11-090: GitHub attestations and attest's own Bundle are publicly verified."""
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
        "name": "attest-release-evidence-v0.1.0",
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


@pytest.mark.ac("AC-F11-080")
def test_release_tags_and_release_are_created_only_after_public_verification() -> None:
    """REQ-F11-080: product and Action tags share one verified release commit."""
    workflow = _workflow()
    publish = workflow["jobs"]["publish-release"]
    commands = "\n".join(step.get("run", "") for step in publish["steps"] if isinstance(step, dict))
    assert "refs/tags/${ACTION_VERSION_TAG}" in commands
    assert "refs/tags/${ACTION_MAJOR_TAG}" in commands
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
    artifacts.mkdir()
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
            urls.append(
                {
                    "filename": filename,
                    "packagetype": package_type,
                    "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                    "yanked": False,
                }
            )
        document = {
            "info": {"name": distribution, "version": "0.1.0"},
            "releases": {"0.1.0": urls},
            "urls": urls,
        }
        endpoint = index / distribution
        endpoint.mkdir(parents=True)
        (endpoint / "json").write_text(json.dumps(document), encoding="utf-8")
    return artifacts, root / "index"


def _verify_published(
    artifacts: Path,
    index: Path,
    *distributions: str,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(PUBLISHED_VERIFIER),
        str(artifacts),
        "--version",
        "0.1.0",
        "--index-base-url",
        index.as_uri(),
        "--attempts",
        "1",
        "--delay-seconds",
        "0",
    ]
    for distribution in distributions:
        arguments.extend(("--distribution", distribution))
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


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
    document_path = index / "pypi/attest-cli/json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["urls"][0]["digests"]["sha256"] = "0" * 64
    document["releases"]["0.1.0"][0]["digests"]["sha256"] = "0" * 64
    document_path.write_text(json.dumps(document), encoding="utf-8")
    result = _verify_published(artifacts, index)
    assert result.returncode == 1
    assert "public artifact hash mismatch" in result.stderr


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
