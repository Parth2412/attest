"""Shared attest-cli contract fixtures."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest

from attest_core import Statement

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_UNDECLARED_OPERATION = "undeclared network or OIDC operation"


@pytest.fixture(autouse=True)
def deny_undeclared_network_and_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail every CLI test on real egress or ambient credential exchange."""

    # Tests opt into event discovery explicitly; never inherit the runner's own PR event.
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(_UNDECLARED_OPERATION)

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("sigstore.oidc.detect_credential", forbidden)


@pytest.fixture
def valid_statement_data() -> dict[str, Any]:
    """Return a fresh normative Statement mapping."""
    path = REPOSITORY_ROOT / "spec" / "testvectors" / "statement-valid" / "input.json"
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return value


@pytest.fixture
def statement(valid_statement_data: dict[str, Any]) -> Statement:
    """Return one semantically valid Statement."""
    return Statement.model_validate(valid_statement_data)
