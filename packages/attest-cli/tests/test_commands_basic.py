"""F-10 basic leaf-command behavior tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from attest_cli import commands
from attest_cli.app import app
from attest_cli.config import CONFIG_FIELDS

CHECKOUT = "actions/checkout@" + "1" * 40
ACTION = "parth2412/attest/action@" + "2" * 40
FIXTURES = Path(__file__).resolve().parents[2] / "attest-sign" / "tests" / "fixtures" / "f08"


@pytest.mark.ac("AC-F10-190")
def test_init_command_reports_exact_created_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--repository",
            str(tmp_path),
            "--github-repository",
            "example/repo",
            "--default-branch",
            "main",
            "--checkout-ref",
            CHECKOUT,
            "--action-ref",
            ACTION,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["data"]["createdPaths"] == [
        str(tmp_path / ".attest" / "config.yaml"),
        str(tmp_path / ".attest" / "policy.yaml"),
        str(tmp_path / ".github" / "workflows" / "attest.yml"),
    ]


@pytest.mark.ac("AC-F10-050")
@pytest.mark.ac("AC-F10-060")
def test_config_show_reports_ordered_provenance_without_secret_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for field in CONFIG_FIELDS:
        if field.environment is not None:
            monkeypatch.delenv(field.environment, raising=False)
    secret = "never-render-this-auth-path"
    monkeypatch.setenv("ATTEST_OCI_AUTH_CONFIG_FILE", secret)
    result = CliRunner().invoke(
        app,
        ["config", "show", "--resolved", "--signing-timeout-seconds", "9", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert secret not in result.stdout
    report = json.loads(result.stdout)
    entries = report["data"]["entries"]
    assert [entry["key"] for entry in entries] == [field.key for field in CONFIG_FIELDS]
    assert entries[4] == {"key": "signing.timeoutSeconds", "value": 9, "source": "flag"}
    assert entries[21] == {
        "key": "storage.oci.authConfigFile",
        "configured": True,
        "source": "environment:ATTEST_OCI_AUTH_CONFIG_FILE",
    }


@pytest.mark.ac("AC-F10-170")
def test_inspect_command_is_prominently_unverified_and_never_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError

    monkeypatch.setattr("attest_sign.verify", forbidden)
    monkeypatch.setattr("attest_policy.evaluate", forbidden)
    wire = json.loads((FIXTURES / "historical-v0.1-trusted.sigstore.json").read_bytes())
    wire["dsseEnvelope"]["signatures"][0]["sig"] = base64.b64encode(bytes(64)).decode()
    bundle = tmp_path / "signature-tampered.sigstore.json"
    bundle.write_text(json.dumps(wire, separators=(",", ":")), encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--input", str(bundle), "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["outcome"] == "unverified-identity"
    assert "verifiedIdentity" not in json.dumps(report["data"])


@pytest.mark.ac("AC-F10-170")
def test_malformed_inspection_is_a_typed_usage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "malformed.json"
    bundle.write_bytes(b"{}")
    result = CliRunner().invoke(app, ["inspect", "--input", str(bundle), "--json"])

    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["data"]["failureCode"] == "ERR-VERIFY-001"
    assert report["error"]["code"] == "ERR-VERIFY-001"


@pytest.mark.ac("AC-F10-220")
def test_unexpected_handler_failure_is_sanitised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    secret = "raw-secret-upstream-exception"

    def broken(_values: object) -> None:
        raise RuntimeError(secret)

    monkeypatch.setitem(commands._HANDLERS, "version", broken)
    result = CliRunner().invoke(app, ["version", "--json"])

    assert result.exit_code == 1
    assert secret not in result.stdout
    assert json.loads(result.stdout)["error"]["code"] == "ERR-INTERNAL-001"


@pytest.mark.ac("AC-F10-020")
@pytest.mark.parametrize(
    ("revision", "expected"),
    [("a" * 40, "a" * 40), ("A" * 40, None), ("not-a-revision", None)],
)
def test_version_reports_only_valid_immutable_build_revision(
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
    expected: str | None,
) -> None:
    monkeypatch.setenv("ATTEST_BUILD_REVISION", revision)
    result = CliRunner().invoke(app, ["version", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["buildRevision"] == expected
