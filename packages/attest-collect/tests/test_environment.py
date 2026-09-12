"""Acceptance tests for F-05 collection-environment metadata."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from importlib import metadata
from typing import Any, cast

import pytest

from attest_collect import collect_environment
from attest_collect.environment import utc_now
from attest_core import EnvironmentKind
from attest_core.errors import BuildError

FIXED_TIME = datetime(2026, 9, 12, 12, 34, 56, 987654, tzinfo=UTC)
NAIVE_TIME = datetime(2026, 9, 12, 12, 34, 56)  # noqa: DTZ001 - deliberate invalid input
GITHUB_ENVIRONMENT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_RUN_ID": "123456",
    "GITHUB_RUN_ATTEMPT": "2",
    "GITHUB_WORKFLOW_REF": "example/repo/.github/workflows/attest.yml@refs/heads/main",
    "GITHUB_EVENT_NAME": "pull_request",
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.githubusercontent.test/request",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "never-serialize-this-secret",
}
GITHUB_TRUST_SIGNALS = (
    "GITHUB_SERVER_URL",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_EVENT_NAME",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)


def _clock() -> datetime:
    return FIXED_TIME


@pytest.mark.ac("AC-F05-050")
def test_environment_uses_the_runtime_attest_collect_distribution_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F05-050: collector identity comes from exact installed metadata."""
    installed = collect_environment({}, clock=_clock)
    assert installed.collector.version == metadata.version("attest-collect")

    requested: list[str] = []

    def version(distribution_name: str) -> str:
        requested.append(distribution_name)
        return "9.8.7"

    monkeypatch.setattr("attest_collect.environment.metadata.version", version)
    collection = collect_environment({}, clock=_clock)
    assert requested == ["attest-collect"]
    assert collection.collector.name == "attest"
    assert collection.collector.version == "9.8.7"

    def missing(_: str) -> str:
        raise metadata.PackageNotFoundError("attest-collect")

    monkeypatch.setattr("attest_collect.environment.metadata.version", missing)
    with pytest.raises(BuildError) as captured:
        collect_environment({}, clock=_clock)
    assert captured.value.code == "ERR-BUILD-211"
    assert "attest-collect" not in captured.value.message
    assert captured.value.__cause__ is not None


@pytest.mark.ac("AC-F05-060")
def test_complete_github_environment_is_trusted_without_retaining_oidc_credentials() -> None:
    """REQ-F05-060: exact GitHub signals produce non-secret trusted metadata."""
    collection = collect_environment(GITHUB_ENVIRONMENT, clock=_clock)
    environment = collection.environment

    assert environment.kind is EnvironmentKind.GITHUB_ACTIONS
    assert environment.trusted is True
    assert environment.run_id == "123456"
    assert environment.run_attempt == 2
    assert environment.workflow_ref == GITHUB_ENVIRONMENT["GITHUB_WORKFLOW_REF"]
    assert environment.event_name == "pull_request"
    assert environment.oidc_issuer == "https://token.actions.githubusercontent.com"

    rendered = json.dumps(collection.model_dump(), sort_keys=True)
    assert "ACTIONS_ID_TOKEN" not in rendered
    assert GITHUB_ENVIRONMENT["ACTIONS_ID_TOKEN_REQUEST_URL"] not in rendered
    assert GITHUB_ENVIRONMENT["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] not in rendered

    with pytest.raises(BuildError) as captured:
        collect_environment(GITHUB_ENVIRONMENT, clock=cast(Any, lambda: "invalid"))
    assert GITHUB_ENVIRONMENT["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] not in str(captured.value)
    assert GITHUB_ENVIRONMENT["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] not in str(captured.value.__cause__)


@pytest.mark.ac("AC-F05-060")
@pytest.mark.parametrize("missing_signal", GITHUB_TRUST_SIGNALS)
def test_each_missing_github_identity_signal_fails_closed(missing_signal: str) -> None:
    """REQ-F05-060: every trust prerequisite is independently mandatory."""
    incomplete = {key: value for key, value in GITHUB_ENVIRONMENT.items() if key != missing_signal}

    environment = collect_environment(incomplete, clock=_clock).environment

    assert environment.kind is EnvironmentKind.GITHUB_ACTIONS
    assert environment.trusted is False
    assert environment.oidc_issuer is None


@pytest.mark.ac("AC-F05-060")
@pytest.mark.parametrize(
    ("environ", "expected_kind"),
    [
        ({}, EnvironmentKind.LOCAL),
        ({"CI": "TRUE"}, EnvironmentKind.LOCAL),
        ({"CI": "true"}, EnvironmentKind.OTHER),
        ({"CI": "true", "GITLAB_CI": "true"}, EnvironmentKind.GITLAB_CI),
        (
            {**GITHUB_ENVIRONMENT, "GITLAB_CI": "true", "CI": "true"},
            EnvironmentKind.GITHUB_ACTIONS,
        ),
    ],
)
def test_environment_classification_has_exact_precedence_and_untrusted_fallbacks(
    environ: dict[str, str], expected_kind: EnvironmentKind
) -> None:
    """REQ-F05-060: platform detection is exact and ordered."""
    environment = collect_environment(environ, clock=_clock).environment

    assert environment.kind is expected_kind
    assert environment.trusted is (expected_kind is EnvironmentKind.GITHUB_ACTIONS)


@pytest.mark.ac("AC-F05-060")
def test_process_environment_is_read_only_when_no_mapping_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F05-060: None selects process environment at operation time."""
    for name in (
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CI",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITLAB_CI", "true")

    environment = collect_environment(clock=_clock).environment

    assert environment.kind is EnvironmentKind.GITLAB_CI
    assert environment.trusted is False


@pytest.mark.ac("AC-F05-060")
def test_invalid_explicit_environment_mapping_is_coded() -> None:
    """REQ-F05-060: invalid adapter inputs cannot escape as raw exceptions."""
    with pytest.raises(BuildError) as captured:
        collect_environment(cast(Any, []), clock=_clock)

    assert captured.value.code == "ERR-BUILD-211"
    assert str(captured.value.__cause__) == "environ must be a string mapping or None"


@pytest.mark.ac("AC-F05-070")
def test_injected_clock_is_called_once_and_normalised_to_utc_seconds() -> None:
    """REQ-F05-070: collection time is an injected aware instant."""
    calls = 0
    offset_time = datetime(
        2026,
        9,
        12,
        18,
        4,
        56,
        987654,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return offset_time

    collection = collect_environment({}, clock=clock)

    assert calls == 1
    assert collection.collected_at == FIXED_TIME.replace(microsecond=0)
    assert collection.model_dump()["collectedAt"] == "2026-09-12T12:34:56Z"


@pytest.mark.ac("AC-F05-070")
def test_default_clock_is_aware_utc() -> None:
    """REQ-F05-070: the production clock is aware UTC without time-sensitive assertions."""
    assert utc_now().tzinfo is UTC


@pytest.mark.ac("AC-F05-070")
@pytest.mark.parametrize("invalid_time", [NAIVE_TIME, "not-a-datetime"])
def test_invalid_injected_clock_result_is_coded(invalid_time: Any) -> None:
    """REQ-F05-070: naive and non-datetime clocks fail as ERR-BUILD-211."""
    with pytest.raises(BuildError) as captured:
        collect_environment({}, clock=lambda: invalid_time)

    assert captured.value.code == "ERR-BUILD-211"
    assert captured.value.__cause__ is not None
