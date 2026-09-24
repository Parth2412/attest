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
        "url": "https://github.com/Parth2412/attest/releases/tag/v0.1.3",
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
        "ACTION_VERSION_TAG": "v1.0.3",
        "PRODUCT_TAG": "v0.1.3",
        "CURRENT_MAJOR_SHA": "a1c59cc67bf67aba22ffca876309f855ea8663af",
        "TARGET_RELEASE_SHA": "8dcfdaf4b16a0547222e3f174bc0c0e13e3549c8",
        "RELEASE_RUN_ID": 35991944542,
        "PROOF_REPOSITORY": "Parth2412/attest-action-proof",
        "PROOF_PR": 4,
        "FORK_PROOF_PR": 5,
        "PROOF_BASE_SHA": "f05ab8830df8605c9b23f54721a092dbd0f08068",
        "PROOF_HEAD_SHA": "e61bbc34e5539d09302e9f9d60b62656ed7103d8",
        "PROOF_MERGE_SHA": "2e584273c7d096ea021dfcc839f712a3596d4657",
        "FORK_PROOF_SHA": "a386c6f908a5d556be5588da9b9403e047624b51",
        "CHANGESET_DIGEST": ("7356fbb663dcf6edcd7f40aae67dd4dce34d4004f85037c0057bb62a22df0ac2"),
        "DENIED_REF_OID": "2f84619df782264724558446f320add54bf7850e",
        "DENIED_BLOB_OID": "155ce9bd68f5dc5fee12976322c7b653fcd0d8a0",
        "DENIED_BUNDLE_SHA256": (
            "e39d6cb916ca81bb5beaf07048e3f28c74b9142b5e34d9bc91d4aafc6d988533"
        ),
        "APPROVED_REF_SUFFIX": "2938073514",
        "APPROVED_REF_OID": "d35d3223fcfbb7e943afa2a56afb6bd2729d9a64",
        "APPROVED_BLOB_OID": "8bc2f89751c52382a628602b8e1ebfbb1856dcc1",
        "APPROVED_BUNDLE_SHA256": (
            "e60df59e1a27fbe7c42b4d7ad484acadbbd8a0ff96937faeb9a371d7d7bde843"
        ),
    }
    commands = _commands(workflow["jobs"]["preflight"])
    for fragment in (
        "repos/${GITHUB_REPOSITORY}/environments/action-major",
        ".can_admins_bypass == false",
        ".deployment_branch_policy.protected_branches == true",
        "repos/${GITHUB_REPOSITORY}/rulesets",
        '"refs/tags/v0.1.3"',
        '"refs/tags/v1.0.3"',
        "actions/workflows/ci.yml/runs?branch=main&event=push",
        "actions/runs/${RELEASE_RUN_ID}/attempts/2",
        "releases/tags/${PRODUCT_TAG}",
        ".immutable == true",
        'git show "${TARGET_RELEASE_SHA}:action/action.yml"',
        'test "${observed_image}" = "ghcr.io/parth2412/attest@sha256:',
    ):
        assert fragment in commands


@pytest.mark.ac("AC-F11-190")
def test_major_tag_preflight_replays_the_complete_public_proof() -> None:
    """REQ-F11-190: promotion requires blocked, denied, approved, and fork evidence."""
    commands = _commands(_workflow()["jobs"]["preflight"])
    for fragment in (
        "pulls/${PROOF_PR}",
        "pulls/${PROOF_PR}/reviews",
        "actions/runs/35996154567/attempts/2/jobs",
        "actions/runs/35996154567/attempts/3/jobs",
        "actions/runs/35996139827/artifacts",
        "blocked-before-check-evidence-35996139827",
        "check-runs/107621975743",
        "check-runs/107627293997",
        "pulls/${FORK_PROOF_PR}",
        "issues/${FORK_PROOF_PR}/comments",
        "actions/runs/35998481445",
        "check-runs/107629036816",
        "ERR-SIGN-301",
        "no OIDC request variables",
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
        "name": "action-major-preflight-v1.0.3-${{ github.run_id }}",
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
    assert '"${PRODUCT_TAG}" "${ACTION_VERSION_TAG}"' in commands

    retained = _step(promote, "Retain final promotion evidence")
    assert retained["if"] == "always()"
    assert retained["with"] == {
        "name": "action-major-promotion-v1.0.3-${{ github.run_id }}",
        "path": "promotion-evidence",
        "if-no-files-found": "error",
        "include-hidden-files": False,
        "retention-days": 90,
    }
