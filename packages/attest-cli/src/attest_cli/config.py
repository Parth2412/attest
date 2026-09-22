"""Closed safe-YAML configuration loading and deterministic source resolution."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Final, Literal, Never, cast

import yaml  # type: ignore[import-untyped]  # REQ-F10-050: PyYAML lacks stubs
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator
from pydantic.alias_generators import to_camel
from yaml.loader import BaseLoader  # type: ignore[import-untyped]
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode  # type: ignore[import-untyped]
from yaml.tokens import (  # type: ignore[import-untyped]
    AliasToken,
    AnchorToken,
    DirectiveToken,
    TagToken,
)

from attest_cli.errors import CliError, cli_error
from attest_cli.safe_io import read_regular_file

_CONFIG_LIMIT: Final[int] = 1024 * 1024
_MAX_DEPTH: Final[int] = 32
_CANONICAL_UINT: Final[re.Pattern[str]] = re.compile(r"(?:0|[1-9][0-9]*)")
_NULL_VALUE: Final[str] = "null configuration values are forbidden"
_INVALID_VERSION: Final[str] = "configuration version must be strict integer 1"

NonEmpty = Annotated[str, Field(strict=True, min_length=1)]
Positive = Annotated[int, Field(strict=True, ge=1)]
NonNegative = Annotated[int, Field(strict=True, ge=0)]


def _invalid() -> Never:
    raise ValueError


class _ConfigModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError(_NULL_VALUE)
        return value


class RepositoryConfig(_ConfigModel):
    path: NonEmpty | None = None
    backend: Literal["auto", "pygit2", "subprocess"] | None = None


class GitHubConfig(_ConfigModel):
    event_path: NonEmpty | None = None


class SigningConfig(_ConfigModel):
    environment: Literal["production", "staging"] | None = None
    timeout_seconds: Positive | None = None


class VerificationConfig(_ConfigModel):
    identity: NonEmpty | None = None
    issuer: NonEmpty | None = None
    environment: Literal["production", "staging"] | None = None
    offline: StrictBool | None = None
    trust_config_file: NonEmpty | None = None


class PolicyConfig(_ConfigModel):
    path: NonEmpty | None = None


class StorageGitConfig(_ConfigModel):
    remote: NonEmpty | None = None
    timeout_seconds: Positive | None = None


class StorageOciSubjectConfig(_ConfigModel):
    media_type: NonEmpty | None = None
    digest: NonEmpty | None = None
    size: NonNegative | None = None


class StorageOciConfig(_ConfigModel):
    repository: NonEmpty | None = None
    subject: StorageOciSubjectConfig | None = None
    staging_directory: NonEmpty | None = None
    auth_config_file: NonEmpty | None = None
    insecure: StrictBool | None = None
    tls_verify: StrictBool | None = None
    timeout_seconds: Positive | None = None


class StorageConfig(_ConfigModel):
    backend: Literal["git-ref", "filesystem", "oci"] | None = None
    directory: NonEmpty | None = None
    fallback_directory: NonEmpty | None = None
    git: StorageGitConfig | None = None
    oci: StorageOciConfig | None = None


class ConfigDocument(_ConfigModel):
    version: Literal[1]
    repository: RepositoryConfig | None = None
    github: GitHubConfig | None = None
    signing: SigningConfig | None = None
    verification: VerificationConfig | None = None
    policy: PolicyConfig | None = None
    storage: StorageConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def _strict_version(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if any(item is None for item in value.values()):
            raise ValueError(_NULL_VALUE)
        version = value.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise ValueError(_INVALID_VERSION)
        return value


FieldKind = Literal["string", "positive", "nonnegative", "boolean"]


@dataclass(frozen=True, slots=True)
class ConfigField:
    key: str
    environment: str | None
    default: object
    kind: FieldKind
    choices: tuple[str, ...] = ()
    secret_bearing: bool = False


CONFIG_FIELDS: Final[tuple[ConfigField, ...]] = (
    ConfigField("repository.path", "ATTEST_REPOSITORY", ".", "string"),
    ConfigField(
        "repository.backend",
        "ATTEST_GIT_BACKEND",
        "auto",
        "string",
        ("auto", "pygit2", "subprocess"),
    ),
    ConfigField("github.eventPath", "ATTEST_GITHUB_EVENT_PATH", None, "string"),
    ConfigField(
        "signing.environment",
        "ATTEST_SIGNING_ENVIRONMENT",
        "production",
        "string",
        ("production", "staging"),
    ),
    ConfigField("signing.timeoutSeconds", "ATTEST_SIGNING_TIMEOUT_SECONDS", 120, "positive"),
    ConfigField("verification.identity", "ATTEST_IDENTITY", None, "string"),
    ConfigField("verification.issuer", "ATTEST_ISSUER", None, "string"),
    ConfigField(
        "verification.environment",
        "ATTEST_VERIFY_ENVIRONMENT",
        "production",
        "string",
        ("production", "staging"),
    ),
    ConfigField("verification.offline", "ATTEST_VERIFY_OFFLINE", True, "boolean"),
    ConfigField("verification.trustConfigFile", "ATTEST_TRUST_CONFIG_FILE", None, "string"),
    ConfigField("policy.path", "ATTEST_POLICY_PATH", ".attest/policy.yaml", "string"),
    ConfigField(
        "storage.backend",
        "ATTEST_STORE_BACKEND",
        "git-ref",
        "string",
        ("git-ref", "filesystem", "oci"),
    ),
    ConfigField("storage.directory", "ATTEST_STORE_DIRECTORY", ".attest/bundles", "string"),
    ConfigField(
        "storage.fallbackDirectory",
        "ATTEST_FALLBACK_DIRECTORY",
        ".attest/fallback",
        "string",
    ),
    ConfigField("storage.git.remote", "ATTEST_GIT_REMOTE", "origin", "string"),
    ConfigField("storage.git.timeoutSeconds", "ATTEST_GIT_TIMEOUT_SECONDS", 120, "positive"),
    ConfigField("storage.oci.repository", "ATTEST_OCI_REPOSITORY", None, "string"),
    ConfigField(
        "storage.oci.subject.mediaType",
        "ATTEST_OCI_SUBJECT_MEDIA_TYPE",
        None,
        "string",
    ),
    ConfigField("storage.oci.subject.digest", "ATTEST_OCI_SUBJECT_DIGEST", None, "string"),
    ConfigField("storage.oci.subject.size", "ATTEST_OCI_SUBJECT_SIZE", None, "nonnegative"),
    ConfigField(
        "storage.oci.stagingDirectory",
        "ATTEST_OCI_STAGING_DIRECTORY",
        None,
        "string",
    ),
    ConfigField(
        "storage.oci.authConfigFile",
        "ATTEST_OCI_AUTH_CONFIG_FILE",
        None,
        "string",
        secret_bearing=True,
    ),
    ConfigField("storage.oci.insecure", "ATTEST_OCI_INSECURE", False, "boolean"),
    ConfigField("storage.oci.tlsVerify", "ATTEST_OCI_TLS_VERIFY", True, "boolean"),
    ConfigField("storage.oci.timeoutSeconds", "ATTEST_OCI_TIMEOUT_SECONDS", 120, "positive"),
)
_FIELDS_BY_KEY: Final[dict[str, ConfigField]] = {item.key: item for item in CONFIG_FIELDS}


@dataclass(frozen=True, slots=True)
class ResolvedEntry:
    key: str
    value: object
    source: str
    configured: bool | None = None
    _resolved_value: object = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    entries: tuple[ResolvedEntry, ...]

    def entry(self, key: str) -> ResolvedEntry:
        for item in self.entries:
            if item.key == key:
                return item
        raise KeyError(key)

    def value(self, key: str) -> object:
        return self.entry(key)._resolved_value

    def source(self, key: str) -> str:
        return self.entry(key).source


def _scalar(node: ScalarNode) -> object:
    value = node.value
    if node.style is not None:
        return value
    if value in {"", "~", "null", "Null", "NULL"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if _CANONICAL_UINT.fullmatch(value) is not None:
        return int(value)
    return value


def _construct(node: Node, depth: int) -> object:
    if depth > _MAX_DEPTH:
        raise ValueError
    if isinstance(node, ScalarNode):
        return _scalar(node)
    if isinstance(node, SequenceNode):
        return [_construct(item, depth + 1) for item in node.value]
    if isinstance(node, MappingNode):
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode):
                _invalid()
            key_value = _scalar(key_node)
            if not isinstance(key_value, str) or not key_value or key_value == "<<":
                raise ValueError
            if key_value in result:
                raise ValueError
            result[key_value] = _construct(value_node, depth + 1)
        return result
    raise ValueError


def _parse_yaml(raw: bytes) -> object:
    raw_value = cast(object, raw)
    if (
        not isinstance(raw_value, bytes)
        or len(raw_value) > _CONFIG_LIMIT
        or raw_value.startswith(b"\xef\xbb\xbf")
    ):
        raise ValueError
    text = raw.decode("utf-8", errors="strict")
    tokens = yaml.scan(text, Loader=BaseLoader)
    if any(
        isinstance(token, AliasToken | AnchorToken | DirectiveToken | TagToken) for token in tokens
    ):
        _invalid()
    documents = list(yaml.compose_all(text, Loader=BaseLoader))
    if len(documents) != 1 or documents[0] is None:
        raise ValueError
    return _construct(documents[0], 1)


def parse_config(raw: bytes, display_path: str) -> ConfigDocument:
    """Parse exact safe-YAML bytes into the closed version 1 model."""
    try:
        path_value = cast(object, display_path)
        if not isinstance(path_value, str) or not path_value:
            _invalid()
        value = _parse_yaml(raw)
        return ConfigDocument.model_validate(value)
    except (TypeError, UnicodeError, ValueError, ValidationError, yaml.YAMLError):
        raise cli_error("ERR-CONFIG-002") from None


def generate_config_schema() -> dict[str, object]:
    """Generate the configuration Draft 2020-12 schema from the runtime model."""
    schema = ConfigDocument.model_json_schema(by_alias=True, mode="validation")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}


def render_config_schema() -> str:
    """Render deterministic configuration schema text."""
    return json.dumps(generate_config_schema(), indent=2, sort_keys=True) + "\n"


def _flatten(value: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, Mapping):
            result.update(_flatten(cast(Mapping[str, object], item), name))
        else:
            result[name] = item
    return result


def _validate_value(definition: ConfigField, value: object) -> object:
    if definition.kind == "string":
        if not isinstance(value, str) or not value:
            raise ValueError
        if definition.choices and value not in definition.choices:
            raise ValueError
        return value
    if definition.kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError
        return value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError
    if definition.kind == "positive" and value < 1:
        raise ValueError
    return value


def _environment_value(definition: ConfigField, value: str) -> object:
    if not isinstance(value, str):
        _invalid()
    if definition.kind == "boolean":
        lowered = value.lower() if value.isascii() else value
        if lowered not in {"true", "false"}:
            raise ValueError
        return lowered == "true"
    if definition.kind in {"positive", "nonnegative"}:
        if _CANONICAL_UINT.fullmatch(value) is None:
            raise ValueError
        parsed = int(value)
        if definition.kind == "positive" and parsed < 1:
            raise ValueError
        return parsed
    return _validate_value(definition, value)


def _configuration_path(
    repository: Path,
    explicit_path: Path | None,
    flags: Mapping[str, object],
    environ: Mapping[str, str],
) -> Path | None:
    if explicit_path is not None:
        return explicit_path
    definition = _FIELDS_BY_KEY["repository.path"]
    flag_selector = flags.get("repository.path")
    if flag_selector is not None:
        selector = _validate_value(definition, flag_selector)
    elif "ATTEST_REPOSITORY" in environ:
        selector = _environment_value(definition, environ["ATTEST_REPOSITORY"])
    else:
        selector = repository
    selected_repository = Path(cast(str | Path, selector))
    candidate = selected_repository / ".attest" / "config.yaml"
    return candidate if candidate.exists() or candidate.is_symlink() else None


def _validate_resolved(entries: Sequence[ResolvedEntry]) -> None:
    values = {item.key: item._resolved_value for item in entries}
    sources = {item.key: item.source for item in entries}
    if values["verification.trustConfigFile"] is not None and (
        sources["verification.environment"] != "builtin"
        or sources["verification.offline"] != "builtin"
    ):
        raise cli_error("ERR-CONFIG-001")
    backend = values["storage.backend"]
    if backend == "oci" and any(
        values[key] is None
        for key in (
            "storage.oci.repository",
            "storage.oci.subject.mediaType",
            "storage.oci.subject.digest",
            "storage.oci.subject.size",
            "storage.oci.stagingDirectory",
        )
    ):
        raise cli_error("ERR-CONFIG-001")
    if backend == "filesystem" and values["storage.directory"] is None:
        raise cli_error("ERR-CONFIG-001")
    if backend == "git-ref" and (
        values["repository.path"] is None or values["storage.git.remote"] is None
    ):
        raise cli_error("ERR-CONFIG-001")
    if values["storage.fallbackDirectory"] is None:
        raise cli_error("ERR-CONFIG-001")


def load_config(
    *,
    repository: Path,
    explicit_path: Path | None = None,
    flags: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
    trusted_github: bool = False,
) -> ResolvedConfig:
    """Resolve flags, environment, one config file, ambient input, then built-ins."""
    try:
        supplied_flags = {} if flags is None else dict(flags)
        supplied_environment = {} if environ is None else dict(environ)
        if set(supplied_flags) - set(_FIELDS_BY_KEY) or any(
            _FIELDS_BY_KEY[key].secret_bearing for key in supplied_flags
        ):
            _invalid()
        config_path = _configuration_path(
            repository,
            explicit_path,
            supplied_flags,
            supplied_environment,
        )
        if explicit_path is not None and not explicit_path.exists():
            raise cli_error("ERR-CONFIG-002")
        if config_path is None:
            document = None
            config_source = None
        else:
            raw = read_regular_file(
                config_path,
                maximum_size=_CONFIG_LIMIT,
                error_code="ERR-CONFIG-002",
            )
            document = parse_config(raw, str(config_path))
            config_source = f"config:{config_path}"
        configured = (
            {}
            if document is None
            else _flatten(
                document.model_dump(by_alias=True, exclude_none=True, exclude={"version"})
            )
        )

        entries: list[ResolvedEntry] = []
        for definition in CONFIG_FIELDS:
            if definition.key in supplied_flags and supplied_flags[definition.key] is not None:
                resolved_value = _validate_value(definition, supplied_flags[definition.key])
                source = "flag"
            elif (
                definition.environment is not None
                and definition.environment in supplied_environment
            ):
                resolved_value = _environment_value(
                    definition,
                    supplied_environment[definition.environment],
                )
                source = f"environment:{definition.environment}"
            elif definition.key in configured:
                resolved_value = _validate_value(definition, configured[definition.key])
                source = cast(str, config_source)
            elif (
                definition.key == "github.eventPath"
                and trusted_github
                and "GITHUB_EVENT_PATH" in supplied_environment
            ):
                resolved_value = _validate_value(
                    definition,
                    supplied_environment["GITHUB_EVENT_PATH"],
                )
                source = "ambient:GITHUB_EVENT_PATH"
            else:
                resolved_value = definition.default
                source = "builtin"
            public_value = None if definition.secret_bearing else resolved_value
            entries.append(
                ResolvedEntry(
                    key=definition.key,
                    value=public_value,
                    source=source,
                    configured=bool(resolved_value) if definition.secret_bearing else None,
                    _resolved_value=resolved_value,
                )
            )
        _validate_resolved(entries)
        return ResolvedConfig(tuple(entries))
    except CliError:
        raise
    except (OSError, TypeError, ValueError):
        raise cli_error("ERR-CONFIG-001") from None
