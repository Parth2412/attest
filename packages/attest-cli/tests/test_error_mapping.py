"""F-10 stable domain-to-process error mapping tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from attest_cli.commands import _failure_from_exception, _mapped_exit
from attest_cli.errors import cli_error
from attest_cli.models import PushData


@pytest.mark.ac("AC-F10-070")
@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        ("ERR-CONFIG-001", 2),
        ("ERR-CONFIG-006", 2),
        ("ERR-COLLECT-101", 2),
        ("ERR-COLLECT-102", 2),
        ("ERR-COLLECT-103", 2),
        ("ERR-COLLECT-104", 2),
        ("ERR-COLLECT-105", 2),
        ("ERR-COLLECT-106", 1),
        ("ERR-COLLECT-115", 2),
        ("ERR-COLLECT-121", 2),
        ("ERR-COLLECT-122", 1),
        ("ERR-COLLECT-123", 6),
        ("ERR-COLLECT-124", 2),
        ("ERR-COLLECT-125", 6),
        ("ERR-COLLECT-126", 2),
        ("ERR-COLLECT-127", 2),
        ("ERR-BUILD-210", 1),
        ("ERR-BUILD-211", 2),
        ("ERR-SIGN-301", 2),
        ("ERR-SIGN-302", 6),
        ("ERR-SIGN-303", 6),
        ("ERR-SIGN-304", 6),
        ("ERR-SIGN-305", 1),
        ("ERR-SIGN-306", 2),
        ("ERR-VERIFY-001", 4),
        ("ERR-VERIFY-011", 2),
        ("ERR-VERIFY-013", 4),
        ("ERR-STORE-401", 6),
        ("ERR-STORE-402", 6),
        ("ERR-STORE-403", 5),
        ("ERR-STORE-404", 1),
        ("ERR-STORE-405", 2),
        ("ERR-STORE-406", 1),
        ("ERR-POLICY-601", 2),
        ("ERR-POLICY-604", 2),
    ],
)
def test_every_domain_error_code_has_one_exact_exit(code: str, exit_code: int) -> None:
    assert _mapped_exit(code) == exit_code


@dataclass(frozen=True, slots=True)
class CodedError:
    code: str
    message: str
    remediation: str
    fallback_path: str | None = None


@pytest.mark.ac("AC-F10-070")
def test_domain_text_is_preserved_but_never_controls_mapping() -> None:
    first = _failure_from_exception(
        "sign",
        CodedError("ERR-SIGN-302", "first stable message", "first stable remediation"),
    )
    second = _failure_from_exception(
        "sign",
        CodedError("ERR-SIGN-302", "completely different text", "different remediation"),
    )

    assert first.exit_code == second.exit_code == 6
    assert first.error is not None
    assert first.error.model_dump() == {
        "code": "ERR-SIGN-302",
        "message": "first stable message",
        "remediation": "first stable remediation",
    }


@pytest.mark.ac("AC-F10-070")
@pytest.mark.ac("AC-F10-210")
def test_primary_store_failure_retains_credential_free_fallback_path() -> None:
    result = _failure_from_exception(
        "push",
        CodedError(
            "ERR-STORE-402",
            "stable transport failure",
            "retry explicit storage",
            fallback_path=".attest/fallback/sha256/example.sigstore.json",
        ),
    )

    assert result.exit_code == 6
    assert result.error is not None
    assert result.error.code == "ERR-STORE-402"
    assert isinstance(result.data, PushData)
    assert result.data.store_ref is None
    assert result.data.fallback_path == ".attest/fallback/sha256/example.sigstore.json"


@pytest.mark.ac("AC-F10-070")
def test_cli_error_and_unknown_exception_use_only_stable_boundary_diagnostics() -> None:
    usage = _failure_from_exception("build", cli_error("ERR-CONFIG-003"))
    unknown = _failure_from_exception("build", RuntimeError("never expose this"))

    assert usage.exit_code == 2
    assert usage.error is not None
    assert usage.error.code == "ERR-CONFIG-003"
    assert unknown.exit_code == 1
    assert unknown.error is not None
    assert unknown.error.code == "ERR-INTERNAL-001"
    assert "never expose this" not in repr(unknown)
