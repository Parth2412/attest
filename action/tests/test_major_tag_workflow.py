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
        "url": "https://github.com/Parth2412/attest/releases/tag/v0.1.4",
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
        "ACTION_VERSION_TAG": "v1.0.4",
        "PRODUCT_TAG": "v0.1.4",
        "CURRENT_MAJOR_SHA": "8dcfdaf4b16a0547222e3f174bc0c0e13e3549c8",
        "TARGET_RELEASE_SHA": "4e73dcaf888f15967da66826d48cca5ac6684fcb",
        "RELEASE_RUN_ID": 36849857414,
        "PROOF_REPOSITORY": "Parth2412/attest-action-proof",
        "PROOF_PR": 6,
        "FORK_PROOF_PR": 7,
        "PROOF_BASE_SHA": "2e584273c7d096ea021dfcc839f712a3596d4657",
        "PROOF_HEAD_SHA": "3fb1b74eec74f621fa2670cc584ee07cea2631c1",
        "PROOF_MERGE_SHA": "6916ab93ec63f59e222acc730e86699a68d59662",
        "FORK_PROOF_SHA": "15d99e162a64f5e047c995f6f31a99facce85fbf",
        "CHANGESET_DIGEST": ("fff2a2fb95c00780d2ea40341195a369fa72c084aa4a2dd7c9539ae2ae9c1c44"),
        "DENIED_REF_OID": "82556c69b09fea969b9bd5a2706a199ba8a56642",
        "DENIED_BLOB_OID": "31e7867da77993fd45252e4d04ec8deec34e5171",
        "DENIED_BUNDLE_SHA256": (
            "73d5ce8dd2f127fc5f1373ee42d199135d698a7b48dacc3883f2a2b2cebb8985"
        ),
        "APPROVED_REF_SUFFIX": "3035912549",
        "APPROVED_REF_OID": "dbdb0acbeba8657b5792020b779ba2cd19b356a7",
        "APPROVED_BLOB_OID": "24fb74ec131a2bc5f9c572c5abc70fb626211e49",
        "APPROVED_BUNDLE_SHA256": (
            "3cd1abae8072b1d8b6027120ef0741fa657e80445b2b63d7b5fdc078438a4829"
        ),
    }
    commands = _commands(workflow["jobs"]["preflight"])
    for fragment in (
        "repos/${GITHUB_REPOSITORY}/environments/action-major",
        ".can_admins_bypass == false",
        ".deployment_branch_policy.protected_branches == true",
        "repos/${GITHUB_REPOSITORY}/rulesets",
        '"refs/tags/v0.1.4"',
        '"refs/tags/v1.0.4"',
        "actions/workflows/ci.yml/runs?branch=main&event=push",
        "actions/runs/${RELEASE_RUN_ID}",
        '.path == ".github/workflows/recover-release-v0.1.4.yml"',
        "release-recovery-publication-v0.1.4-1",
        "release-recovery-preflight-v0.1.4-1",
        "release-recovery-assets-v0.1.4-1",
        "releases/tags/${PRODUCT_TAG}",
        ".immutable == true",
        'git show "${TARGET_RELEASE_SHA}:action/action.yml"',
        'test "${observed_image}" = "ghcr.io/parth2412/attest@sha256:',
    ):
        assert fragment in commands


@pytest.mark.ac("AC-F11-110")
@pytest.mark.ac("AC-F11-120")
@pytest.mark.ac("AC-F11-190")
def test_major_tag_preflight_replays_the_complete_public_proof() -> None:
    """REQ-F11-190: promotion requires blocked, denied, approved, and fork evidence."""
    commands = _commands(_workflow()["jobs"]["preflight"])
    for fragment in (
        "pulls/${PROOF_PR}",
        "pulls/${PROOF_PR}/reviews",
        "actions/runs/36868174765/attempts/2/jobs",
        "actions/runs/36868174765/attempts/3/jobs",
        "actions/runs/36868149895/artifacts",
        "blocked-before-check-v0.1.4-evidence-36868149895",
        "check-runs/110389240862",
        "check-runs/110395705968",
        "pulls/${FORK_PROOF_PR}",
        "issues/${FORK_PROOF_PR}/comments",
        "actions/runs/36870771570",
        "check-runs/110397642782",
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
        "attest-cli==0.1.3",
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
        "name": "action-major-preflight-v1.0.4-${{ github.run_id }}",
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
    assert '"${PRODUCT_TAG}" "${ACTION_VERSION_TAG}"' in commands

    retained = _step(promote, "Retain final promotion evidence")
    assert retained["if"] == "always()"
    assert retained["with"] == {
        "name": "action-major-promotion-v1.0.4-${{ github.run_id }}",
        "path": "promotion-evidence",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }
