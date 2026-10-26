"""F-11 reviewed moving-major Action tag promotion contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML lacks typing metadata.

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PROMOTION_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/promote-action-major.yml"
FULL_SHA: Final[re.Pattern[str]] = re.compile(r"[^@\s]+@[0-9a-f]{40}\Z")
EXPECTED_ACTIONS: Final[set[str]] = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
}
EXPECTED_RELEASE_ARTIFACTS: Final[set[tuple[int, str, int]]] = {
    (12606524834, "release-preflight-evidence-v0.1.7", 329219),
    (12606554771, "public-package-evidence-python-3.12-v0.1.7", 1461),
    (12606629629, "release-assets-v0.1.7", 12290458),
    (12606669337, "release-corresponding-source-v0.1.7", 10968578),
    (12606689679, "publication-state-evidence-v0.1.7", 16066),
    (12606814250, "public-package-evidence-python-3.13-v0.1.7", 1463),
    (12606854283, "image-promotion-evidence-v0.1.7", 1130),
    (12606884252, "patch-attestation-evidence-v0.1.7", 58030),
    (12607128488, "release-dogfood-evidence-v0.1.7", 34401),
    (12607221367, "cli-distributions-v0.1.5", 94979),
    (12607236241, "python-release-assets-v0.1.7", 1207007),
    (12607281535, "release-asset-attestation-evidence-v0.1.7", 203698),
    (12607356042, "store-distributions-v0.1.2", 67189),
}
RELEASE_ARTIFACT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'id: (\d+),\s+name: "([^"]+)",\s+size_in_bytes: (\d+),\s+expired: false'
)


def _workflow() -> dict[Any, Any]:
    workflow = yaml.safe_load(PROMOTION_WORKFLOW.read_text(encoding="utf-8"))
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


def _commands(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"] if isinstance(step, dict))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


@pytest.mark.ac("AC-F11-080")
def test_major_tag_promotion_is_manual_reviewed_and_least_privileged() -> None:
    """REQ-F11-080: only the reviewed procedure can move the Action major tag."""
    workflow = _workflow()
    assert workflow["name"] == "promote Action major"
    assert _triggers(workflow) == {"workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "promote-action-major-v1",
        "cancel-in-progress": False,
    }

    jobs = workflow["jobs"]
    assert set(jobs) == {"preflight", "promote"}
    assert jobs["preflight"]["if"] == (
        "github.repository == 'Parth2412/attest' && "
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert jobs["preflight"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert jobs["promote"]["needs"] == "preflight"
    assert jobs["promote"]["if"] == "needs.preflight.result == 'success'"
    assert jobs["promote"]["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert jobs["promote"]["environment"] == {
        "name": "action-major",
        "url": "https://github.com/Parth2412/attest/releases/tag/v0.1.7",
    }

    action_references = _uses(workflow)
    assert action_references == EXPECTED_ACTIONS
    assert all(FULL_SHA.fullmatch(reference) for reference in action_references)
    rendered = PROMOTION_WORKFLOW.read_text(encoding="utf-8")
    assert rendered.count("secrets.") == 1
    assert rendered.count("secrets.ACTION_MAJOR_TOKEN") == 1
    assert "pull_request_target:" not in rendered

    promotion_step = _step(jobs["promote"], "Revalidate and move the Action major tag")
    assert promotion_step["env"] == {
        "GH_TOKEN": "${{ secrets.ACTION_MAJOR_TOKEN }}",
    }


@pytest.mark.ac("AC-F11-080")
def test_major_tag_preflight_locks_source_release_and_repository_controls() -> None:
    """REQ-F11-080: promotion binds immutable releases and protected controls."""
    workflow = _workflow()
    assert workflow["env"] == {
        "ACTION_MAJOR_TAG": "v1",
        "ACTION_VERSION_TAG": "v1.0.7",
        "PRODUCT_TAG": "v0.1.7",
        "CURRENT_MAJOR_SHA": "e693e6b60afdf9c667a913faa4f9652bfd6dc050",
        "TARGET_RELEASE_SHA": "c42e52d038f5ecdcc498679cb7648e5b0957d489",
        "RELEASE_RUN_ID": 40215131129,
        "PROOF_REPOSITORY": "Parth2412/attest-action-proof",
        "PROOF_PR": 13,
        "FORK_PROOF_PR": 14,
        "PROOF_BASE_SHA": "a13dbf8d29cd54ea6de59b1fdd56bf7f57496147",
        "PROOF_HEAD_SHA": "834636a149480ed72d0baf71daf086fe85700350",
        "PROOF_MERGE_SHA": "644082721a4d61ff42a51c685a0fc192f90b41ce",
        "FORK_PROOF_SHA": "fabf3bee8b2aba03288086bd69d20dfc8554596b",
        "CHANGESET_DIGEST": ("13a9767a393bd5a2ed23dfe734bfbe3d7f5e44e02e65407f40cf44ecc09e3987"),
        "DENIED_REF_OID": "dd12e17a8b805dc9fe61e63fe32ae9890eb3d79f",
        "DENIED_BLOB_OID": "f3b9c2f0452e387a81baee5d84f80660153c76a6",
        "DENIED_BUNDLE_SHA256": (
            "0ebe061a591016dc6935650250270e415a6a1f2bb0e2184ab13b486176c9b3fd"
        ),
        "APPROVED_REF_SUFFIX": "3463880835",
        "APPROVED_REF_OID": "1cc724a5a86872e4a6fe638975ec6261957580b9",
        "APPROVED_BLOB_OID": "8ac2562cce4035a430ea166e266dc121904b3514",
        "APPROVED_BUNDLE_SHA256": (
            "485071e6d7f3b5b346f0cccddf40cfccf522bbc4ef63a1e71ece168e07e7e0b0"
        ),
    }
    commands = _commands(workflow["jobs"]["preflight"])
    for fragment in (
        "repos/${GITHUB_REPOSITORY}/environments/action-major",
        ".can_admins_bypass == false",
        ".deployment_branch_policy.protected_branches == true",
        "repos/${GITHUB_REPOSITORY}/rulesets",
        '"refs/tags/v0.1.7"',
        '"refs/tags/v1.0.7"',
        "actions/workflows/ci.yml/runs?branch=main&event=push",
        "actions/runs/${RELEASE_RUN_ID}",
        '.path == ".github/workflows/release.yml"',
        "release-assets-v0.1.7",
        "release-preflight-evidence-v0.1.7",
        "release-corresponding-source-v0.1.7",
        "releases/tags/${PRODUCT_TAG}",
        ".immutable == true",
        'git show "${TARGET_RELEASE_SHA}:action/action.yml"',
        'test "${observed_image}" = "ghcr.io/parth2412/attest@sha256:',
    ):
        assert fragment in commands

    observed_artifacts = {
        (int(artifact_id), name, int(size))
        for artifact_id, name, size in RELEASE_ARTIFACT_PATTERN.findall(commands)
    }
    assert observed_artifacts == EXPECTED_RELEASE_ARTIFACTS


@pytest.mark.ac("AC-F11-110")
@pytest.mark.ac("AC-F11-120")
@pytest.mark.ac("AC-F11-190")
def test_major_tag_preflight_replays_the_complete_public_proof() -> None:
    """REQ-F11-190: promotion requires blocked, denied, approved, and fork evidence."""
    commands = _commands(_workflow()["jobs"]["preflight"])
    for fragment in (
        "pulls/${PROOF_PR}",
        "pulls/${PROOF_PR}/reviews",
        "actions/runs/40215971173/attempts/2/jobs",
        "actions/runs/40215971173/attempts/3/jobs",
        "actions/runs/40215956182/artifacts",
        "blocked-before-check-v0.1.7-evidence-40215956182",
        "check-runs/121237216992",
        "check-runs/121237541687",
        "pulls/${FORK_PROOF_PR}",
        "issues/${FORK_PROOF_PR}/comments",
        "actions/runs/40216255453",
        "check-runs/121237911907",
        "ERR-SIGN-301",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "refs/pull/${PROOF_PR}/head",
        "refs/attestations/${CHANGESET_DIGEST}",
        "refs/attestations/${CHANGESET_DIGEST}-${APPROVED_REF_SUFFIX}",
        'test "$(git -C proof cat-file -t "${DENIED_REF_OID}")" = "tag"',
        'test "$(git -C proof rev-parse "${DENIED_REF_OID}^{}")" = "${DENIED_BLOB_OID}"',
        'test "$(sha256sum promotion-evidence/proof/denied-bundle.sigstore.json',
        'test "$(sha256sum promotion-evidence/proof/approved-bundle.sigstore.json',
        "attest-cli==0.1.5",
        '"${cli}" verify',
        '"${cli}" gate',
        'test "${denied_exit}" = "3"',
        '.data.decision.outcome == "deny"',
        '.data.decision.outcome == "allow"',
        "sitecustomize.py",
        "version: [",
    ):
        assert fragment in commands

    retained = _step(_workflow()["jobs"]["preflight"], "Retain preflight promotion evidence")
    assert retained["with"] == {
        "name": "action-major-preflight-v1.0.7-${{ github.run_id }}",
        "path": "promotion-evidence",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }


@pytest.mark.ac("AC-F11-080")
@pytest.mark.ac("AC-F11-190")
def test_major_tag_is_moved_once_after_review_and_then_verified() -> None:
    """REQ-F11-080/190: the reviewed job alone performs one exact tag update."""
    workflow = _workflow()
    preflight_commands = _commands(workflow["jobs"]["preflight"])
    promote = workflow["jobs"]["promote"]
    commands = _commands(promote)

    assert "--method PATCH" not in preflight_commands
    assert commands.count("--method PATCH") == 1
    assert "git/refs/tags/${ACTION_MAJOR_TAG}" in commands
    assert '--field sha="${TARGET_RELEASE_SHA}"' in commands
    assert "--field force=true" in commands
    assert 'test -n "${GH_TOKEN}"' in commands
    assert 'test "${before}" = "${CURRENT_MAJOR_SHA}"' in commands
    assert 'test "${after}" = "${TARGET_RELEASE_SHA}"' in commands
    assert "v0.1.0 v1.0.0" in commands
    assert "v0.1.1 v1.0.1" in commands
    assert "v0.1.2 v1.0.2" in commands
    assert "v0.1.3 v1.0.3" in commands
    assert "v0.1.4 v1.0.4" in commands
    assert "v0.1.5 v1.0.5" in commands
    assert "v0.1.6 v1.0.6" in commands
    assert '"${PRODUCT_TAG}" "${ACTION_VERSION_TAG}"' in commands

    retained = _step(promote, "Retain final promotion evidence")
    assert retained["if"] == "always()"
    assert retained["with"] == {
        "name": "action-major-promotion-v1.0.7-${{ github.run_id }}",
        "path": "promotion-evidence",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }
