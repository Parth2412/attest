"""Shared fixtures for the F-09 policy conformance suite."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pytest
import yaml  # type: ignore[import-untyped]  # AC-F09-090: PyYAML lacks typing metadata

from attest_core import Statement
from attest_policy import PolicyContext

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STATEMENT_VECTOR = REPOSITORY_ROOT / "spec" / "testvectors" / "statement-valid" / "input.json"
IDENTITY = "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"


@dataclass(frozen=True, slots=True)
class StaticVerificationView:
    status: Literal["verified", "verified-untrusted-environment", "failed"]
    statement: Statement | None
    failure_code: str | None
    verified_identity: str | None
    verified_issuer: str | None
    transparency_log_verified: bool


@pytest.fixture
def policy_data() -> dict[str, Any]:
    return {
        "version": 1,
        "policies": [
            {
                "id": "POL-MAIN-001",
                "description": "Protect AI-assisted changes",
                "match": {"branches": ["main"], "paths": ["**"]},
                "require": {
                    "attestation": True,
                    "environment": {"trusted": True},
                    "signer": {"issuer": ISSUER, "identity": IDENTITY},
                    "transparencyLog": True,
                    "review": {
                        "when": {"authorshipMode": ["ai-assisted"]},
                        "minHumanApprovals": 1,
                        "approverMustNotBeAuthor": True,
                    },
                    "authorship": {"claimsRequired": True},
                    "checks": {"mustPass": ["unit-tests"]},
                },
                "onViolation": "block",
            }
        ],
    }


@pytest.fixture
def valid_policy_raw(policy_data: dict[str, Any]) -> bytes:
    return cast(str, yaml.safe_dump(policy_data, sort_keys=False)).encode()


@pytest.fixture
def statement() -> Statement:
    value = json.loads(STATEMENT_VECTOR.read_text(encoding="utf-8"))
    return Statement.model_validate(value)


@pytest.fixture
def verified_view(statement: Statement) -> StaticVerificationView:
    return StaticVerificationView(
        status="verified",
        statement=statement,
        failure_code=None,
        verified_identity=IDENTITY,
        verified_issuer=ISSUER,
        transparency_log_verified=True,
    )


@pytest.fixture
def policy_context() -> PolicyContext:
    return PolicyContext(target_branch="main", changed_paths=("src/a.py",))
