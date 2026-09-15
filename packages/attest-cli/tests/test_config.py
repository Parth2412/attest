"""F-10 strict configuration and provenance contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attest_cli.config import (
    CONFIG_FIELDS,
    ConfigField,
    generate_config_schema,
    load_config,
    parse_config,
    render_config_schema,
)
from attest_cli.errors import CliError

ENVIRONMENT_VALUES = {
    "repository.path": "repository",
    "repository.backend": "subprocess",
    "github.eventPath": "event.json",
    "signing.environment": "staging",
    "signing.timeoutSeconds": "30",
    "verification.identity": "identity",
    "verification.issuer": "issuer",
    "verification.environment": "staging",
    "verification.offline": "TRUE",
    "verification.trustConfigFile": "trust.json",
    "policy.path": "policy.yaml",
    "storage.backend": "filesystem",
    "storage.directory": "bundles",
    "storage.fallbackDirectory": "fallback",
    "storage.git.remote": "upstream",
    "storage.git.timeoutSeconds": "45",
    "storage.oci.repository": "ghcr.io/example/repository",
    "storage.oci.subject.mediaType": "application/vnd.example",
    "storage.oci.subject.digest": "sha256:" + "a" * 64,
    "storage.oci.subject.size": "0",
    "storage.oci.stagingDirectory": "staging",
    "storage.oci.authConfigFile": "auth.json",
    "storage.oci.insecure": "FALSE",
    "storage.oci.tlsVerify": "TRUE",
    "storage.oci.timeoutSeconds": "60",
}
EXPECTED_ENVIRONMENT_VALUES = {
    **ENVIRONMENT_VALUES,
    "signing.timeoutSeconds": 30,
    "verification.offline": True,
    "storage.git.timeoutSeconds": 45,
    "storage.oci.subject.size": 0,
    "storage.oci.insecure": False,
    "storage.oci.tlsVerify": True,
    "storage.oci.timeoutSeconds": 60,
}


@pytest.mark.ac("AC-F10-050")
def test_flag_environment_config_builtin_precedence(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".attest").mkdir(parents=True)
    config_path = repository / ".attest" / "config.yaml"
    config_path.write_text(
        """version: 1
repository:
  backend: subprocess
signing:
  timeoutSeconds: 45
""",
        encoding="utf-8",
    )

    resolved = load_config(
        repository=repository,
        flags={"signing.timeoutSeconds": 15},
        environ={
            "ATTEST_GIT_BACKEND": "pygit2",
            "ATTEST_SIGNING_TIMEOUT_SECONDS": "30",
        },
    )

    assert resolved.value("signing.timeoutSeconds") == 15
    assert resolved.source("signing.timeoutSeconds") == "flag"
    assert resolved.value("repository.backend") == "pygit2"
    assert resolved.source("repository.backend") == "environment:ATTEST_GIT_BACKEND"
    assert resolved.value("signing.environment") == "production"
    assert resolved.source("signing.environment") == "builtin"


@pytest.mark.ac("AC-F10-050")
@pytest.mark.parametrize(
    "raw",
    [
        b"version: 1\nunknown: true\n",
        b"version: null\n",
        b"version: true\n",
        b"version: 01\n",
        b"version: 1\nversion: 1\n",
        b"---\nversion: 1\n---\nversion: 1\n",
        b"version: &version 1\nrepository: {backend: *version}\n",
        b"version: !!int 1\n",
        b"version: 1\nrepository: {backend: auto, <<: {path: .}}\n",
        b"\xef\xbb\xbfversion: 1\n",
        b"version: 1\nrepository: [auto]\n",
        b"version: 1\nrepository:\n  backend: AUTO\n",
    ],
)
def test_unsafe_or_non_strict_yaml_is_rejected(raw: bytes) -> None:
    with pytest.raises(CliError) as raised:
        parse_config(raw, "config.yaml")

    assert raised.value.code == "ERR-CONFIG-002"
    assert "config.yaml" not in raised.value.message


@pytest.mark.ac("AC-F10-050")
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATTEST_VERIFY_OFFLINE", "1"),
        ("ATTEST_VERIFY_OFFLINE", " true"),
        ("ATTEST_OCI_INSECURE", "yes"),
        ("ATTEST_SIGNING_TIMEOUT_SECONDS", "+1"),
        ("ATTEST_SIGNING_TIMEOUT_SECONDS", "01"),
        ("ATTEST_SIGNING_TIMEOUT_SECONDS", "0"),
        ("ATTEST_GIT_TIMEOUT_SECONDS", "1 "),
    ],
)
def test_environment_scalars_are_exact(name: str, value: str, tmp_path: Path) -> None:
    with pytest.raises(CliError) as raised:
        load_config(repository=tmp_path, environ={name: value})

    assert raised.value.code == "ERR-CONFIG-001"


@pytest.mark.ac("AC-F10-050")
def test_explicit_config_replaces_repository_config_and_must_exist(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("version: 1\nrepository:\n  backend: subprocess\n", encoding="utf-8")

    resolved = load_config(repository=repository, explicit_path=explicit, environ={})

    assert resolved.source("repository.backend") == f"config:{explicit}"
    with pytest.raises(CliError) as raised:
        load_config(repository=repository, explicit_path=tmp_path / "missing.yaml", environ={})
    assert raised.value.code == "ERR-CONFIG-002"


@pytest.mark.ac("AC-F10-050")
@pytest.mark.ac("AC-F10-160")
def test_dangling_repository_config_symlink_is_not_treated_as_absent(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    configuration = repository / ".attest" / "config.yaml"
    configuration.parent.mkdir(parents=True)
    configuration.symlink_to(tmp_path / "missing.yaml")

    with pytest.raises(CliError, match="ERR-CONFIG-002"):
        load_config(repository=repository, environ={})


@pytest.mark.ac("AC-F10-050")
def test_trusted_ambient_github_event_has_lowest_non_builtin_precedence(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    resolved = load_config(
        repository=tmp_path,
        environ={"GITHUB_EVENT_PATH": str(event)},
        trusted_github=True,
    )
    assert resolved.value("github.eventPath") == str(event)
    assert resolved.source("github.eventPath") == "ambient:GITHUB_EVENT_PATH"

    untrusted = load_config(
        repository=tmp_path,
        environ={"GITHUB_EVENT_PATH": str(event)},
        trusted_github=False,
    )
    assert untrusted.value("github.eventPath") is None
    assert untrusted.source("github.eventPath") == "builtin"


@pytest.mark.ac("AC-F10-050")
def test_trust_source_and_oci_configuration_conflicts_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        load_config(
            repository=tmp_path,
            flags={
                "verification.trustConfigFile": "trust.json",
                "verification.environment": "staging",
            },
            environ={},
        )

    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        load_config(
            repository=tmp_path,
            flags={"storage.backend": "oci", "storage.oci.repository": "ghcr.io/a/b"},
            environ={},
        )


@pytest.mark.ac("AC-F10-060")
def test_resolved_config_never_represents_secret_values(tmp_path: Path) -> None:
    secret = "ghp_never_render_this_value"
    resolved = load_config(
        repository=tmp_path,
        environ={"GITHUB_TOKEN": secret, "ATTEST_OCI_AUTH_CONFIG_FILE": "auth.json"},
    )

    rendered = repr(resolved)
    assert secret not in rendered
    assert all(
        "token" not in field.key.lower() and "password" not in field.key.lower()
        for field in CONFIG_FIELDS
    )
    auth_entry = resolved.entry("storage.oci.authConfigFile")
    assert auth_entry.value is None
    assert auth_entry.configured is True
    assert auth_entry.source == "environment:ATTEST_OCI_AUTH_CONFIG_FILE"


@pytest.mark.ac("AC-F10-050")
@pytest.mark.parametrize("definition", CONFIG_FIELDS, ids=lambda item: item.key)
def test_every_named_environment_source_is_typed_and_has_exact_provenance(
    tmp_path: Path,
    definition: ConfigField,
) -> None:
    key = definition.key
    environment = definition.environment
    assert isinstance(environment, str)
    raw = ENVIRONMENT_VALUES[key]
    resolved = load_config(repository=tmp_path, environ={environment: raw})
    entry = resolved.entry(key)

    assert resolved.value(key) == EXPECTED_ENVIRONMENT_VALUES[key]
    assert entry.source == f"environment:{environment}"
    if key == "storage.oci.authConfigFile":
        assert entry.value is None
        assert entry.configured is True
    else:
        assert entry.value == EXPECTED_ENVIRONMENT_VALUES[key]


@pytest.mark.ac("AC-F10-050")
@pytest.mark.ac("AC-F10-060")
def test_secret_bearing_and_unknown_fields_cannot_enter_through_flags(tmp_path: Path) -> None:
    for flags in (
        {"storage.oci.authConfigFile": "secret.json"},
        {"unknown.field": "value"},
    ):
        with pytest.raises(CliError, match="ERR-CONFIG-001"):
            load_config(repository=tmp_path, flags=flags, environ={})


@pytest.mark.ac("AC-F10-200")
def test_config_model_is_closed_and_versioned() -> None:
    document = parse_config(b"version: 1\nrepository:\n  path: .\n", "config.yaml")
    assert document.version == 1
    assert document.repository is not None
    assert document.repository.path == "."


@pytest.mark.ac("AC-F10-050")
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("repository.path", ""),
        ("repository.backend", "AUTO"),
        ("verification.offline", 1),
        ("signing.timeoutSeconds", 0),
        ("storage.oci.subject.size", -1),
    ],
)
def test_flag_values_use_the_same_strict_scalar_contract(
    tmp_path: Path,
    key: str,
    value: object,
) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-001"):
        load_config(repository=tmp_path, flags={key: value}, environ={})


@pytest.mark.ac("AC-F10-050")
def test_config_schema_renderer_and_missing_entry_are_deterministic(tmp_path: Path) -> None:
    rendered = render_config_schema()
    assert json.loads(rendered) == generate_config_schema()
    assert rendered.endswith("\n")

    resolved = load_config(repository=tmp_path, environ={})
    with pytest.raises(KeyError, match="not-present"):
        resolved.entry("not-present")
