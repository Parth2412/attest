"""Acceptance tests for the strict policy configuration model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]  # AC-F09-170: PyYAML lacks typing metadata
from pydantic import ValidationError

from attest_policy import PolicyError, load_policy


def _encoded(value: object) -> bytes:
    return cast(str, yaml.safe_dump(value, sort_keys=False)).encode()


@pytest.mark.ac("AC-F09-170")
@pytest.mark.parametrize(
    ("case", "path", "replacement"),
    [
        ("unknown-root", (), {"unexpected": True}),
        ("unknown-policy", ("policies", 0), {"unexpected": True}),
        ("unknown-match", ("policies", 0, "match"), {"unexpected": True}),
        ("unknown-require", ("policies", 0, "require"), {"unexpected": True}),
        (
            "unknown-environment",
            ("policies", 0, "require", "environment"),
            {"unexpected": True},
        ),
        ("unknown-signer", ("policies", 0, "require", "signer"), {"unexpected": True}),
        ("unknown-review", ("policies", 0, "require", "review"), {"unexpected": True}),
        (
            "unknown-review-when",
            ("policies", 0, "require", "review", "when"),
            {"unexpected": True},
        ),
        (
            "unknown-authorship",
            ("policies", 0, "require", "authorship"),
            {"unexpected": True},
        ),
        ("unknown-checks", ("policies", 0, "require", "checks"), {"unexpected": True}),
        ("empty-id", ("policies", 0), {"id": ""}),
        ("empty-description", ("policies", 0), {"description": ""}),
        ("empty-branches", ("policies", 0, "match"), {"branches": []}),
        ("empty-paths", ("policies", 0, "match"), {"paths": []}),
        ("duplicate-branches", ("policies", 0, "match"), {"branches": ["main", "main"]}),
        ("duplicate-paths", ("policies", 0, "match"), {"paths": ["**", "**"]}),
        ("empty-require", ("policies", 0), {"require": {}}),
        ("empty-review", ("policies", 0, "require"), {"review": {}}),
        ("missing-attestation", ("policies", 0, "require"), {"attestation": None}),
        ("false-attestation", ("policies", 0, "require"), {"attestation": False}),
        ("string-attestation", ("policies", 0, "require"), {"attestation": "true"}),
        (
            "string-environment",
            ("policies", 0, "require", "environment"),
            {"trusted": "true"},
        ),
        ("bad-identity", ("policies", 0, "require", "signer"), {"identity": "*"}),
        ("empty-issuer", ("policies", 0, "require", "signer"), {"issuer": ""}),
        ("string-log", ("policies", 0, "require"), {"transparencyLog": "true"}),
        (
            "duplicate-modes",
            ("policies", 0, "require", "review", "when"),
            {"authorshipMode": ["ai-assisted", "ai-assisted"]},
        ),
        (
            "empty-modes",
            ("policies", 0, "require", "review", "when"),
            {"authorshipMode": []},
        ),
        (
            "negative-approvals",
            ("policies", 0, "require", "review"),
            {"minHumanApprovals": -1},
        ),
        (
            "boolean-approvals",
            ("policies", 0, "require", "review"),
            {"minHumanApprovals": True},
        ),
        (
            "separation-without-minimum",
            ("policies", 0, "require", "review"),
            {"minHumanApprovals": None},
        ),
        (
            "separation-zero-minimum",
            ("policies", 0, "require", "review"),
            {"minHumanApprovals": 0},
        ),
        (
            "string-separation",
            ("policies", 0, "require", "review"),
            {"approverMustNotBeAuthor": "true"},
        ),
        (
            "string-claims",
            ("policies", 0, "require", "authorship"),
            {"claimsRequired": "true"},
        ),
        (
            "duplicate-checks",
            ("policies", 0, "require", "checks"),
            {"mustPass": ["unit-tests", "unit-tests"]},
        ),
        ("empty-check", ("policies", 0, "require", "checks"), {"mustPass": [""]}),
        ("bad-violation", ("policies", 0), {"onViolation": "ignore"}),
    ],
)
def test_invalid_policy_matrix_covers_closed_and_cross_field_rules(
    case: str,
    path: tuple[str | int, ...],
    replacement: dict[str, object],
    policy_data: dict[str, Any],
) -> None:
    del case
    value = deepcopy(policy_data)
    target: Any = value
    for part in path:
        target = target[part]
    target.update(replacement)

    with pytest.raises(PolicyError) as captured:
        load_policy(_encoded(value))
    assert captured.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-170")
@pytest.mark.parametrize(
    "missing_path",
    [
        ("version",),
        ("policies",),
        ("policies", 0, "id"),
        ("policies", 0, "match"),
        ("policies", 0, "match", "branches"),
        ("policies", 0, "match", "paths"),
        ("policies", 0, "require"),
        ("policies", 0, "require", "attestation"),
        ("policies", 0, "onViolation"),
    ],
)
def test_required_policy_fields_cannot_be_omitted(
    missing_path: tuple[str | int, ...],
    policy_data: dict[str, Any],
) -> None:
    value = deepcopy(policy_data)
    target: Any = value
    for part in missing_path[:-1]:
        target = target[part]
    del target[missing_path[-1]]

    with pytest.raises(PolicyError) as captured:
        load_policy(_encoded(value))
    assert captured.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-020")
@pytest.mark.parametrize(
    ("path", "public_name", "internal_name"),
    [
        (("policies", 0), "onViolation", "on_violation"),
        (("policies", 0, "require"), "transparencyLog", "transparency_log"),
        (
            ("policies", 0, "require", "review", "when"),
            "authorshipMode",
            "authorship_mode",
        ),
        (
            ("policies", 0, "require", "review"),
            "minHumanApprovals",
            "min_human_approvals",
        ),
        (
            ("policies", 0, "require", "review"),
            "approverMustNotBeAuthor",
            "approver_must_not_be_author",
        ),
        (
            ("policies", 0, "require", "authorship"),
            "claimsRequired",
            "claims_required",
        ),
        (("policies", 0, "require", "checks"), "mustPass", "must_pass"),
    ],
)
def test_internal_field_names_are_not_public_policy_aliases(
    path: tuple[str | int, ...],
    public_name: str,
    internal_name: str,
    policy_data: dict[str, Any],
) -> None:
    value = deepcopy(policy_data)
    target: Any = value
    for part in path:
        target = target[part]
    target[internal_name] = target.pop(public_name)

    with pytest.raises(PolicyError) as captured:
        load_policy(_encoded(value))
    assert captured.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-170")
def test_policy_ids_and_nested_signer_fields_are_mandatory_and_unique(
    policy_data: dict[str, Any],
) -> None:
    duplicate = deepcopy(policy_data)
    duplicate["policies"].append(deepcopy(duplicate["policies"][0]))
    with pytest.raises(PolicyError) as duplicate_capture:
        load_policy(_encoded(duplicate))
    assert duplicate_capture.value.code == "ERR-POLICY-601"

    for missing in ("issuer", "identity"):
        value = deepcopy(policy_data)
        del value["policies"][0]["require"]["signer"][missing]
        with pytest.raises(PolicyError) as missing_capture:
            load_policy(_encoded(value))
        assert missing_capture.value.code == "ERR-POLICY-601"


@pytest.mark.ac("AC-F09-020")
def test_policy_models_are_frozen_and_unknown_fields_are_loader_errors(
    valid_policy_raw: bytes,
) -> None:
    loaded = load_policy(valid_policy_raw)
    assert loaded.document is not None
    document = cast(Any, loaded.document)
    with pytest.raises(ValidationError):
        document.version = 2
    with pytest.raises(PolicyError) as captured:
        load_policy(valid_policy_raw + b"unexpected: true\n")
    assert captured.value.code == "ERR-POLICY-601"
