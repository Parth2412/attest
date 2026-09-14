"""Purity and dependency-boundary tests for F-09."""

from __future__ import annotations

import inspect
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest_policy import PolicyContext, evaluate, load_policy

_UNEXPECTED_IO = "policy operation attempted I/O"


def _unexpected_io(*args: object, **kwargs: object) -> object:
    del args, kwargs
    raise AssertionError(_UNEXPECTED_IO)


@pytest.mark.ac("AC-F09-010")
def test_load_and_evaluate_are_pure_and_predicate_is_not_an_argument(
    monkeypatch: pytest.MonkeyPatch,
    valid_policy_raw: bytes,
    verified_view: Any,
    policy_context: PolicyContext,
) -> None:
    monkeypatch.setattr("builtins.open", _unexpected_io)
    monkeypatch.setattr(os, "getenv", _unexpected_io)
    monkeypatch.setattr(socket, "socket", _unexpected_io)
    monkeypatch.setattr(subprocess, "run", _unexpected_io)

    loaded = load_policy(valid_policy_raw, "display-only.yml")
    decision = evaluate(verified_view, loaded, policy_context)

    assert decision.exit_code == 0
    assert list(inspect.signature(evaluate).parameters) == ["verification", "policy", "context"]


@pytest.mark.ac("AC-F09-160")
def test_policy_package_has_no_peer_crypto_or_certificate_code() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "attest_policy"
    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source_root.glob("*.py"))
    )
    for forbidden in ("attest_sign", "sigstore", "cryptography", "x509", "certificate"):
        assert forbidden not in rendered.lower()
