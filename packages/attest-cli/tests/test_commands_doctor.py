"""F-10 bounded doctor diagnostic tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from httpx import Timeout
from sigstore.models import ClientTrustConfig
from typer.testing import CliRunner

from attest_cli import commands
from attest_cli.app import app
from attest_cli.errors import CliError

_SENSITIVE_UPSTREAM_DETAIL = "sensitive upstream detail"


@pytest.mark.ac("AC-F10-120")
@pytest.mark.ac("AC-F10-130")
@pytest.mark.ac("AC-F10-230")
def test_doctor_is_offline_without_explicit_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        commands,
        "_signing_endpoints",
        lambda _environment: ("https://fulcio.example", "https://rekor.example"),
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError

    monkeypatch.setattr("httpx.Client", forbidden)
    result = CliRunner().invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert [check["name"] for check in report["data"]["checks"]] == [
        "git-backend",
        "ambient-identity",
        "ci-environment",
        "policy",
        "signing-endpoints",
    ]
    assert report["data"]["checks"][-1]["message"] == (
        "Network reachability probe was not requested"
    )


@pytest.mark.ac("AC-F10-120")
@pytest.mark.ac("AC-F10-130")
def test_doctor_probe_uses_tls_no_redirects_no_environment_and_five_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    endpoints = ("https://fulcio.example", "https://rekor.example")
    monkeypatch.setattr(commands, "_signing_endpoints", lambda _environment: endpoints)
    seen: dict[str, object] = {"requests": []}

    class Response:
        status_code = 200

    class Client:
        def __init__(self, **kwargs: object) -> None:
            seen["configuration"] = kwargs

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def head(self, endpoint: str) -> Response:
            requests = seen["requests"]
            assert isinstance(requests, list)
            requests.append(endpoint)
            return Response()

    monkeypatch.setattr("httpx.Client", Client)
    result = CliRunner().invoke(app, ["doctor", "--probe-network", "--json"])

    assert result.exit_code == 0, result.output
    assert seen["requests"] == list(endpoints)
    configuration = seen["configuration"]
    assert isinstance(configuration, dict)
    assert configuration["follow_redirects"] is False
    assert configuration["verify"] is True
    assert configuration["trust_env"] is False
    timeout = configuration["timeout"]
    assert isinstance(timeout, Timeout)
    assert timeout.connect == 5.0


@pytest.mark.ac("AC-F10-120")
@pytest.mark.parametrize("environment", ["production", "staging"])
def test_doctor_derives_https_endpoints_from_selected_sigstore_configuration(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    signing = SimpleNamespace(
        get_fulcio=lambda: SimpleNamespace(url="https://fulcio.example"),
        get_tlogs=lambda: [SimpleNamespace(url="https://rekor.example")],
        get_tsas=lambda: [SimpleNamespace(url="https://tsa.example")],
    )

    def selected(*, offline: bool) -> SimpleNamespace:
        assert offline is True
        calls.append(environment)
        return SimpleNamespace(signing_config=signing)

    monkeypatch.setattr(ClientTrustConfig, environment, staticmethod(selected))

    assert commands._signing_endpoints(environment) == (
        "https://fulcio.example",
        "https://rekor.example",
        "https://tsa.example",
    )
    assert calls == [environment]


@pytest.mark.ac("AC-F10-120")
@pytest.mark.ac("AC-F10-130")
def test_failed_optional_doctor_probe_warns_without_leaking_transport_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    endpoint = "https://fulcio.example"
    monkeypatch.setattr(commands, "_signing_endpoints", lambda _environment: (endpoint,))

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def head(self, url: str) -> None:
            request = httpx.Request("HEAD", url)
            raise httpx.ConnectError(_SENSITIVE_UPSTREAM_DETAIL, request=request)

    monkeypatch.setattr("httpx.Client", Client)
    result = CliRunner().invoke(app, ["doctor", "--probe-network", "--json"])

    assert result.exit_code == 0, result.output
    assert _SENSITIVE_UPSTREAM_DETAIL not in result.stdout
    report = json.loads(result.stdout)
    assert report["outcome"] == "warning"
    check = report["data"]["checks"][-1]
    assert check["status"] == "warning"
    assert check["code"] == "WARN-DOCTOR-003"


@pytest.mark.ac("AC-F10-120")
def test_unavailable_selected_git_backend_is_a_usage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    class Unavailable:
        @staticmethod
        def is_available() -> bool:
            return False

    monkeypatch.setattr("attest_collect.Pygit2Backend", Unavailable)
    monkeypatch.setattr("attest_collect.SubprocessBackend", Unavailable)
    result = CliRunner().invoke(app, ["doctor", "--git-backend", "auto", "--json"])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "ERR-CONFIG-006"


@pytest.mark.ac("AC-F10-120")
def test_invalid_or_non_https_signing_endpoint_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        commands._signing_endpoints("development")

    signing = SimpleNamespace(
        get_fulcio=lambda: SimpleNamespace(url="http://insecure.example"),
        get_tlogs=lambda: [],
        get_tsas=lambda: [],
    )
    monkeypatch.setattr(
        ClientTrustConfig,
        "production",
        staticmethod(lambda *, offline: SimpleNamespace(signing_config=signing)),
    )
    with pytest.raises(CliError, match="ERR-CONFIG-006"):
        commands._signing_endpoints("production")
