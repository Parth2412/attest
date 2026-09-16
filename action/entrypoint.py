"""Closed, fail-safe GitHub container Action adapter for the attest CLI."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import subprocess  # nosec B404
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Never, TextIO

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

_ATTEST_EXECUTABLE: Final[Path] = Path("/opt/venv/bin/attest")
_GIT_EXECUTABLE: Final[Path] = Path("/usr/bin/git")
_EVENT_LIMIT: Final[int] = 1024 * 1024
_POLICY_LIMIT: Final[int] = 1024 * 1024
_BUNDLE_LIMIT: Final[int] = 64 * 1024 * 1024
_OID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{40}")
_DIGEST_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
_ERROR_PATTERN: Final[re.Pattern[str]] = re.compile(r"ERR-[A-Z]+-[0-9]{3}")
_REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
_AUTHORSHIP_MODES: Final[frozenset[str]] = frozenset(
    {"human-authored", "ai-assisted", "ai-authored", "unknown"}
)
_REVIEW_STATES: Final[frozenset[str]] = frozenset(
    {"approved", "changes-requested", "commented", "none", "unknown"}
)
_DECISIONS: Final[frozenset[str]] = frozenset({"allow", "warn", "deny"})
_ACTION_INPUT_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {
        "INPUT_MODE",
        "INPUT_POLICY",
        "INPUT_BUNDLE",
        "INPUT_PUSH-ATTESTATION",
        "INPUT_FAIL-ON-VIOLATION",
    }
)
_CLI_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {
        "GITHUB_ACTIONS",
        "GITHUB_BASE_REF",
        "GITHUB_EVENT_NAME",
        "GITHUB_HEAD_REF",
        "GITHUB_REF",
        "GITHUB_REF_NAME",
        "GITHUB_REF_TYPE",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_SERVER_URL",
        "GITHUB_SHA",
        "GITHUB_WORKFLOW_REF",
    }
)


@dataclass(frozen=True, slots=True)
class ActionInputs:
    """Validated closed Action inputs."""

    mode: str
    policy: str | None
    bundle: str | None
    push_attestation: bool | None
    fail_on_violation: bool | None


@dataclass(frozen=True, slots=True)
class EventContext:
    """Validated immutable event coordinates."""

    name: str
    event_path: Path
    base_revision: str
    head_revision: str
    target_branch: str
    checkout_revision: str


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Repository coordinates after completeness checks."""

    repository: Path
    event: EventContext
    comparison_base: str


@dataclass(frozen=True, slots=True)
class ReportFacts:
    """Validated public facts extracted from one typed CLI report."""

    digest: str
    decision: str
    authorship_mode: str
    review_required: bool | str
    review_state: str
    human_approvals: int
    attestation_ref: str | None


@dataclass(frozen=True, slots=True)
class ActionError(RuntimeError):
    """Carry one static Action-boundary diagnostic."""

    code: str
    message: str
    remediation: str
    exit_code: int


_ERRORS: Final[dict[str, ActionError]] = {
    "ERR-CONFIG-007": ActionError(
        "ERR-CONFIG-007",
        "The Action input or GitHub event is unsupported, malformed, inconsistent, or forbidden",
        "Use only the documented inputs on a branch pull_request or branch push event",
        2,
    ),
    "ERR-CONFIG-008": ActionError(
        "ERR-CONFIG-008",
        "Repository history is shallow, incomplete, or missing a required comparison object",
        "Configure checkout with fetch-depth: 0 and ensure both comparison objects exist",
        2,
    ),
    "ERR-SIGN-301": ActionError(
        "ERR-SIGN-301",
        "The run mode has no ambient GitHub OIDC signing identity",
        "Add permissions: id-token: write; do not add a token input",
        2,
    ),
    "ERR-INTERNAL-001": ActionError(
        "ERR-INTERNAL-001",
        "An unexpected internal failure occurred",
        "Retry once and report the Action version and stable error code if it persists",
        1,
    ),
}


def _raise(code: str) -> Never:
    raise _ERRORS[code]


def _invalid() -> Never:
    _raise("ERR-CONFIG-007")


def _object_pairs(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> Never:
    raise ValueError


def _value_error() -> Never:
    raise ValueError


def _type_error() -> Never:
    raise TypeError


def _decode_json(raw: bytes) -> JsonObject:
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            _value_error()
        decoded: JsonValue = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
        if not isinstance(decoded, dict):
            _type_error()
    except (RecursionError, TypeError, UnicodeError, ValueError):
        _invalid()
    else:
        return decoded


def _write_all(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError
        remaining = remaining[written:]


def _open_absolute_parent(path: Path) -> tuple[int, str]:
    if not path.is_absolute() or any(ord(character) < 32 for character in os.fspath(path)):
        raise ValueError
    name = path.name
    if name in {"", ".", ".."}:
        raise ValueError
    descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except Exception:
        os.close(descriptor)
        raise
    else:
        return descriptor, name


def _same_regular_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISREG(left.st_mode)
        and stat.S_ISREG(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _read_absolute_regular(path: Path, *, maximum_size: int) -> bytes:
    directory_fd = -1
    file_fd = -1
    try:
        directory_fd, name = _open_absolute_parent(path)
        before_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before_path.st_mode) or before_path.st_size > maximum_size:
            raise ValueError
        file_fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
        before_fd = os.fstat(file_fd)
        if not _same_regular_file(before_path, before_fd):
            raise ValueError
        chunks: list[bytes] = []
        remaining = maximum_size + 1
        while remaining:
            chunk = os.read(file_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after_fd = os.fstat(file_fd)
        after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(content) > maximum_size
            or len(content) != before_fd.st_size
            or not _same_regular_file(before_fd, after_fd)
            or not _same_regular_file(after_fd, after_path)
        ):
            raise ValueError
        content.decode("utf-8", errors="strict")
        return content
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _append_absolute_regular(path: Path, content: bytes) -> None:
    directory_fd = -1
    file_fd = -1
    try:
        directory_fd, name = _open_absolute_parent(path)
        before_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before_path.st_mode):
            raise ValueError
        file_fd = os.open(
            name,
            os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
        before_fd = os.fstat(file_fd)
        if not _same_regular_file(before_path, before_fd):
            raise ValueError
        _write_all(file_fd, content)
        os.fsync(file_fd)
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _repository_relative(value: str) -> PurePosixPath:
    if (
        not value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
        or "\\" in value
    ):
        _invalid()
    path = PurePosixPath(value)
    if path.is_absolute() or path == PurePosixPath(".") or any(part == ".." for part in path.parts):
        _invalid()
    return path


def _read_repository_file(
    repository: Path,
    value: str,
    *,
    maximum_size: int,
    json_file: bool,
) -> Path:
    relative = _repository_relative(value)
    path = repository.joinpath(*relative.parts)
    try:
        raw = _read_absolute_regular(path, maximum_size=maximum_size)
        if json_file:
            _decode_json(raw)
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError):
        _invalid()
    return path


def _parse_boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    _invalid()


def _parse_inputs(arguments: Sequence[str], environ: Mapping[str, str]) -> ActionInputs:
    allowed = {
        "--mode",
        "--policy",
        "--bundle",
        "--push-attestation",
        "--fail-on-violation",
    }
    if any(
        name.startswith("INPUT_") and name not in _ACTION_INPUT_ENVIRONMENTS for name in environ
    ):
        _invalid()
    values: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in allowed or option in values or index + 1 >= len(arguments):
            _invalid()
        values[option] = arguments[index + 1]
        index += 2
    mode = values.get("--mode")
    if mode not in {"run", "verify", "gate"}:
        _invalid()

    policy_value = values.get("--policy") or None
    bundle_value = values.get("--bundle") or None
    push_value = values.get("--push-attestation") or None
    fail_value = values.get("--fail-on-violation") or None
    policy = policy_value
    bundle = bundle_value

    if mode == "run":
        if bundle_value is not None:
            _invalid()
        policy = ".attest/policy.yaml" if policy is None else policy
        push = True if push_value is None else _parse_boolean(push_value)
        fail = True if fail_value is None else _parse_boolean(fail_value)
    elif mode == "verify":
        if policy_value is not None or push_value is not None or fail_value is not None:
            _invalid()
        if bundle is None:
            _invalid()
        push = None
        fail = None
    else:
        if push_value is not None:
            _invalid()
        if bundle is None:
            _invalid()
        policy = ".attest/policy.yaml" if policy is None else policy
        push = None
        fail = True if fail_value is None else _parse_boolean(fail_value)

    if policy is not None:
        _repository_relative(policy)
    if bundle is not None:
        _repository_relative(bundle)
    return ActionInputs(mode, policy, bundle, push, fail)


def _nonempty_environment(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value or any(ord(character) < 32 for character in value):
        _invalid()
    return value


def _require_oid(value: JsonValue) -> str:
    if not isinstance(value, str) or _OID_PATTERN.fullmatch(value) is None or value == "0" * 40:
        _invalid()
    return value


def _require_string(value: JsonValue) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        _invalid()
    return value


def _require_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        _invalid()
    return value


def _require_repository(value: JsonValue) -> str:
    rendered = _require_string(value)
    if _REPOSITORY_PATTERN.fullmatch(rendered) is None or any(
        part in {".", ".."} for part in rendered.split("/")
    ):
        _invalid()
    return rendered


def _require_branch(value: JsonValue) -> str:
    rendered = _require_string(value)
    if rendered.startswith("refs/") or "*" in rendered:
        _invalid()
    return rendered


def _event_payload(environ: Mapping[str, str]) -> tuple[Path, JsonObject]:
    event_path = Path(_nonempty_environment(environ, "GITHUB_EVENT_PATH"))
    try:
        payload = _decode_json(_read_absolute_regular(event_path, maximum_size=_EVENT_LIMIT))
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError):
        _invalid()
    return event_path, payload


def _resolve_push_event(
    environ: Mapping[str, str], event_path: Path, payload: JsonObject
) -> EventContext:
    before = _require_oid(payload.get("before"))
    after = _require_oid(payload.get("after"))
    if payload.get("created") is not False or payload.get("deleted") is not False:
        _invalid()
    reference = _require_string(payload.get("ref"))
    prefix = "refs/heads/"
    if not reference.startswith(prefix):
        _invalid()
    branch = _require_branch(reference.removeprefix(prefix))
    repository = _require_repository(_require_object(payload.get("repository")).get("full_name"))
    if (
        repository != _nonempty_environment(environ, "GITHUB_REPOSITORY")
        or reference != _nonempty_environment(environ, "GITHUB_REF")
        or branch != _nonempty_environment(environ, "GITHUB_REF_NAME")
        or environ.get("GITHUB_REF_TYPE") != "branch"
        or after != _nonempty_environment(environ, "GITHUB_SHA")
    ):
        _invalid()
    return EventContext("push", event_path, before, after, branch, after)


def _positive_integer(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid()
    return value


def _resolve_pull_request_event(
    environ: Mapping[str, str], event_path: Path, payload: JsonObject
) -> EventContext:
    _require_string(payload.get("action"))
    number = _positive_integer(payload.get("number"))
    repository = _require_repository(_require_object(payload.get("repository")).get("full_name"))
    pull_request = _require_object(payload.get("pull_request"))
    base = _require_object(pull_request.get("base"))
    head = _require_object(pull_request.get("head"))
    base_repository = _require_repository(_require_object(base.get("repo")).get("full_name"))
    _require_repository(_require_object(head.get("repo")).get("full_name"))
    base_revision = _require_oid(base.get("sha"))
    head_revision = _require_oid(head.get("sha"))
    base_branch = _require_branch(base.get("ref"))
    head_branch = _require_branch(head.get("ref"))
    checkout_revision = _nonempty_environment(environ, "GITHUB_SHA")
    if _OID_PATTERN.fullmatch(checkout_revision) is None:
        _invalid()
    if (
        repository != _nonempty_environment(environ, "GITHUB_REPOSITORY")
        or base_repository != repository
        or _nonempty_environment(environ, "GITHUB_REF") != f"refs/pull/{number}/merge"
        or environ.get("GITHUB_BASE_REF") != base_branch
        or environ.get("GITHUB_HEAD_REF") != head_branch
    ):
        _invalid()
    return EventContext(
        "pull_request",
        event_path,
        base_revision,
        head_revision,
        base_branch,
        checkout_revision,
    )


def _resolve_event(environ: Mapping[str, str]) -> EventContext:
    if (
        environ.get("GITHUB_ACTIONS") != "true"
        or environ.get("GITHUB_SERVER_URL") != "https://github.com"
    ):
        _invalid()
    name = _nonempty_environment(environ, "GITHUB_EVENT_NAME")
    if name not in {"push", "pull_request"}:
        _invalid()
    event_path, payload = _event_payload(environ)
    if name == "push":
        return _resolve_push_event(environ, event_path, payload)
    return _resolve_pull_request_event(environ, event_path, payload)


def _repository_path(environ: Mapping[str, str]) -> Path:
    path = Path(_nonempty_environment(environ, "GITHUB_WORKSPACE"))
    try:
        status = path.stat(follow_symlinks=False)
        if (
            not path.is_absolute()
            or path.is_symlink()
            or not stat.S_ISDIR(status.st_mode)
            or any(ord(character) < 32 for character in os.fspath(path))
        ):
            _invalid()
        resolved = path.resolve(strict=True)
    except ActionError:
        raise
    except (OSError, RuntimeError, ValueError):
        _invalid()
    return resolved


def _git_environment(home: Path) -> dict[str, str]:
    return {
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": os.fspath(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _git(
    repository: Path,
    home: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        os.fspath(_GIT_EXECUTABLE),
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        f"safe.directory={repository}",
        "-C",
        os.fspath(repository),
        *arguments,
    ]
    return subprocess.run(  # noqa: S603  # nosec B603
        command,
        check=False,
        capture_output=True,
        env=_git_environment(home),
        timeout=30,
    )


def _complete_repository(repository: Path, event: EventContext, home: Path) -> RuntimeContext:
    try:
        shallow = _git(repository, home, "rev-parse", "--is-shallow-repository")
        if shallow.returncode != 0 or shallow.stdout.strip() == b"true":
            _raise("ERR-CONFIG-008")
        revisions = {event.base_revision, event.head_revision, event.checkout_revision}
        for revision in revisions:
            result = _git(repository, home, "cat-file", "-e", f"{revision}^{{commit}}")
            if result.returncode != 0:
                _raise("ERR-CONFIG-008")
        if event.name == "pull_request":
            result = _git(repository, home, "merge-base", event.base_revision, event.head_revision)
            comparison_base = result.stdout.decode("ascii", errors="strict").strip()
            if result.returncode != 0 or _OID_PATTERN.fullmatch(comparison_base) is None:
                _raise("ERR-CONFIG-008")
        else:
            comparison_base = event.base_revision
        comparison = _git(
            repository,
            home,
            "diff-tree",
            "-r",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--no-commit-id",
            comparison_base,
            event.head_revision,
            "--",
        )
        if comparison.returncode != 0:
            _raise("ERR-CONFIG-008")
    except ActionError:
        raise
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        _raise("ERR-CONFIG-008")
    return RuntimeContext(repository, event, comparison_base)


def _require_oidc(environ: Mapping[str, str]) -> None:
    url = environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    token = environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if (
        not isinstance(url, str)
        or not url.startswith("https://")
        or any(ord(character) < 32 for character in url)
        or not isinstance(token, str)
        or not token
        or any(character.isspace() for character in token)
    ):
        _raise("ERR-SIGN-301")


def _prepare_home(home: Path, repository: Path) -> None:
    home.mkdir(mode=0o700)
    config = home / ".gitconfig"
    result = subprocess.run(  # noqa: S603  # nosec B603
        [
            os.fspath(_GIT_EXECUTABLE),
            "config",
            "--file",
            os.fspath(config),
            "--add",
            "safe.directory",
            os.fspath(repository),
        ],
        check=False,
        capture_output=True,
        env=_git_environment(home),
        timeout=30,
    )
    if result.returncode != 0:
        _raise("ERR-INTERNAL-001")
    config.chmod(0o600)


def _sanitized_environment(
    source: Mapping[str, str],
    inputs: ActionInputs,
    home: Path,
    attest_executable: Path,
) -> dict[str, str]:
    environment = {
        name: value
        for name in _CLI_ENVIRONMENTS
        if isinstance((value := source.get(name)), str) and value
    }
    environment.update(
        HOME=os.fspath(home),
        LANG="C.UTF-8",
        LC_ALL="C",
        NO_COLOR="1",
        PATH=f"{attest_executable.parent}:/usr/bin:/bin",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PYTHONSAFEPATH="1",
        PYTHONUNBUFFERED="1",
        PYTHONUTF8="1",
    )
    revision = source.get("ATTEST_BUILD_REVISION")
    if isinstance(revision, str) and _OID_PATTERN.fullmatch(revision) is not None:
        environment["ATTEST_BUILD_REVISION"] = revision
    if inputs.mode == "run":
        for name in (
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "GITHUB_TOKEN",
        ):
            value = source.get(name)
            if isinstance(value, str) and value:
                environment[name] = value
    return environment


def _cli_arguments(
    inputs: ActionInputs,
    runtime: RuntimeContext,
    temporary: Path,
    policy_path: Path | None,
    bundle_path: Path | None,
    attest_executable: Path,
) -> tuple[list[str], Path]:
    executable = os.fspath(attest_executable)
    common = ["--repository", os.fspath(runtime.repository)]
    if inputs.mode == "run":
        output = temporary / "bundle.sigstore.json"
        arguments = [
            executable,
            "run",
            "--output",
            os.fspath(output),
            "--work-directory",
            os.fspath(temporary / "work"),
            *common,
        ]
        if policy_path is None:
            _raise("ERR-INTERNAL-001")
        arguments.extend(["--policy", os.fspath(policy_path)])
        if runtime.event.name == "pull_request":
            arguments.extend(["--github-event", os.fspath(runtime.event.event_path)])
        else:
            arguments.extend(
                [
                    "--base",
                    runtime.comparison_base,
                    "--head",
                    runtime.event.head_revision,
                    "--target-branch",
                    runtime.event.target_branch,
                ]
            )
        if inputs.push_attestation is False:
            arguments.extend(
                [
                    "--store-backend",
                    "filesystem",
                    "--store-directory",
                    os.fspath(temporary / "store"),
                    "--fallback-directory",
                    os.fspath(temporary / "fallback"),
                ]
            )
    elif inputs.mode == "verify":
        if bundle_path is None:
            _raise("ERR-INTERNAL-001")
        output = bundle_path
        arguments = [
            executable,
            "verify",
            "--input",
            os.fspath(bundle_path),
            *common,
            "--base",
            runtime.comparison_base,
            "--head",
            runtime.event.head_revision,
        ]
    else:
        if bundle_path is None or policy_path is None:
            _raise("ERR-INTERNAL-001")
        output = bundle_path
        arguments = [
            executable,
            "gate",
            "--input",
            os.fspath(bundle_path),
            *common,
            "--base",
            runtime.comparison_base,
            "--head",
            runtime.event.head_revision,
            "--target-branch",
            runtime.event.target_branch,
            "--policy",
            os.fspath(policy_path),
        ]
    arguments.extend(["--json", "--no-color"])
    return arguments, output


def _run_cli(
    arguments: Sequence[str],
    *,
    environment: Mapping[str, str],
    repository: Path,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(  # noqa: S603  # nosec B603
            list(arguments),
            check=False,
            capture_output=True,
            cwd=repository,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        _raise("ERR-INTERNAL-001")


def _mapping(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        _raise("ERR-INTERNAL-001")
    return value


def _list(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        _raise("ERR-INTERNAL-001")
    return value


def _closed_string(value: JsonValue, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        _raise("ERR-INTERNAL-001")
    return value


def _bounded_output_string(value: JsonValue) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 16 * 1024
        or any(ord(character) < 32 for character in value)
    ):
        _raise("ERR-INTERNAL-001")
    return value


def _verification(report: JsonObject) -> JsonObject:
    data = _mapping(report.get("data"))
    verification = _mapping(data.get("verification"))
    if verification.get("status") not in {"verified", "verified-untrusted-environment"}:
        _raise("ERR-INTERNAL-001")
    return verification


def _report_facts(report: JsonObject, inputs: ActionInputs) -> ReportFacts:
    verification = _verification(report)
    statement = _mapping(verification.get("statement"))
    subjects = _list(statement.get("subject"))
    if len(subjects) != 1:
        _raise("ERR-INTERNAL-001")
    subject = _mapping(subjects[0])
    if subject.get("name") != "changeset":
        _raise("ERR-INTERNAL-001")
    digest_value = _mapping(subject.get("digest")).get("sha256")
    if not isinstance(digest_value, str) or _DIGEST_PATTERN.fullmatch(digest_value) is None:
        _raise("ERR-INTERNAL-001")
    predicate = _mapping(statement.get("predicate"))
    authorship = _mapping(predicate.get("authorship"))
    authorship_mode = _closed_string(authorship.get("mode"), _AUTHORSHIP_MODES)
    review = _mapping(predicate.get("review"))
    review_state = _closed_string(review.get("state"), _REVIEW_STATES)
    review_required = review.get("required")
    if not isinstance(review_required, bool) and review_required != "unknown":
        _raise("ERR-INTERNAL-001")
    human_approvals = review.get("humanApprovals")
    if (
        isinstance(human_approvals, bool)
        or not isinstance(human_approvals, int)
        or human_approvals < 0
    ):
        _raise("ERR-INTERNAL-001")

    if inputs.mode == "verify":
        decision = "verified"
        attestation_ref = inputs.bundle
    else:
        data = _mapping(report.get("data"))
        decision_data = _mapping(data.get("decision"))
        decision = _closed_string(decision_data.get("outcome"), _DECISIONS)
        decision_exit = decision_data.get("exitCode")
        if (
            isinstance(decision_exit, bool)
            or not isinstance(decision_exit, int)
            or decision_exit != report.get("exitCode")
            or report.get("outcome")
            != {"allow": "success", "warn": "warning", "deny": "denied"}[decision]
        ):
            _raise("ERR-INTERNAL-001")
        if inputs.mode == "run" and inputs.push_attestation is True:
            attestation_ref = _bounded_output_string(_mapping(data.get("storeRef")).get("location"))
        elif inputs.mode == "gate":
            attestation_ref = inputs.bundle
        else:
            attestation_ref = None
    return ReportFacts(
        digest_value,
        decision,
        authorship_mode,
        review_required,
        review_state,
        human_approvals,
        attestation_ref,
    )


def _safe_diagnostic(
    report: JsonObject,
    *,
    secrets_to_reject: frozenset[str],
) -> ActionError:
    error = _mapping(report.get("error"))
    code = error.get("code")
    message = error.get("message")
    remediation = error.get("remediation")
    if (
        not isinstance(code, str)
        or _ERROR_PATTERN.fullmatch(code) is None
        or not isinstance(message, str)
        or not isinstance(remediation, str)
        or not message
        or not remediation
        or len(message) > 2000
        or len(remediation) > 2000
        or any(ord(character) < 32 for character in message + remediation)
        or any(secret and secret in message + remediation for secret in secrets_to_reject)
    ):
        _raise("ERR-INTERNAL-001")
    exit_code = report.get("exitCode")
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or exit_code not in range(1, 7)
    ):
        _raise("ERR-INTERNAL-001")
    return ActionError(code, message, remediation, exit_code)


def _parse_report(process: subprocess.CompletedProcess[bytes], mode: str) -> JsonObject:
    if len(process.stdout) > 64 * 1024 * 1024:
        _raise("ERR-INTERNAL-001")
    try:
        report = _decode_json(process.stdout)
    except ActionError:
        _raise("ERR-INTERNAL-001")
    exit_code = report.get("exitCode")
    outcome = report.get("outcome")
    if (
        report.get("schemaVersion") != "0.1.0"
        or report.get("command") != mode
        or isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or exit_code != process.returncode
        or exit_code not in range(7)
    ):
        _raise("ERR-INTERNAL-001")
    if outcome in {"success", "warning"}:
        if exit_code != 0:
            _raise("ERR-INTERNAL-001")
    elif outcome == "denied":
        if mode not in {"gate", "run"} or exit_code not in {3, 4, 5}:
            _raise("ERR-INTERNAL-001")
    elif outcome == "failed":
        if exit_code not in {1, 2, 4, 5, 6}:
            _raise("ERR-INTERNAL-001")
    else:
        _raise("ERR-INTERNAL-001")
    return report


def _extract_log_index(path: Path) -> str | None:
    try:
        bundle = _decode_json(_read_absolute_regular(path, maximum_size=_BUNDLE_LIMIT))
        material = _mapping(bundle.get("verificationMaterial"))
        entries = _list(material.get("tlogEntries"))
        if len(entries) != 1:
            return None
        value = _mapping(entries[0]).get("logIndex")
        if isinstance(value, bool):
            _raise("ERR-INTERNAL-001")
        if isinstance(value, int):
            if value < 0:
                _raise("ERR-INTERNAL-001")
            return str(value)
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            parsed = int(value)
            if str(parsed) != value:
                _raise("ERR-INTERNAL-001")
            return value
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, UnicodeError, ValueError):
        _raise("ERR-INTERNAL-001")
    else:
        return None


def _environment_path(environ: Mapping[str, str], name: str) -> Path:
    return Path(_nonempty_environment(environ, name))


def _write_output(environ: Mapping[str, str], name: str, value: str) -> None:
    if not value or any(ord(character) < 32 and character != "\n" for character in value):
        _raise("ERR-INTERNAL-001")
    for _ in range(16):
        delimiter = f"attest_{secrets.token_hex(16)}"
        if delimiter not in value:
            break
    else:
        _raise("ERR-INTERNAL-001")
    rendered = f"{name}<<{delimiter}\n{value}\n{delimiter}\n".encode()
    try:
        _append_absolute_regular(_environment_path(environ, "GITHUB_OUTPUT"), rendered)
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        _raise("ERR-INTERNAL-001")


def _write_summary(environ: Mapping[str, str], facts: ReportFacts) -> None:
    required = (
        "unknown" if facts.review_required == "unknown" else str(facts.review_required).lower()
    )
    content = (
        "## attest result\n\n"
        "| Fact | Value |\n"
        "| --- | --- |\n"
        f"| Decision | `{facts.decision}` |\n"
        f"| Authorship mode | `{facts.authorship_mode}` |\n"
        f"| Review required | `{required}` |\n"
        f"| Review state | `{facts.review_state}` |\n"
        f"| Human approvals | `{facts.human_approvals}` |\n"
    ).encode()
    try:
        _append_absolute_regular(_environment_path(environ, "GITHUB_STEP_SUMMARY"), content)
    except ActionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        _raise("ERR-INTERNAL-001")


def _emit_error(error: ActionError, stderr: TextIO) -> None:
    document = {
        "error": {
            "code": error.code,
            "message": error.message,
            "remediation": error.remediation,
        }
    }
    stderr.write(json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n")
    stderr.flush()


def _policy_exit_is_advisory(report: JsonObject, inputs: ActionInputs) -> bool:
    if inputs.mode == "verify" or inputs.fail_on_violation is not False:
        return False
    exit_code = report.get("exitCode")
    if exit_code not in {3, 5}:
        return False
    data = report.get("data")
    if not isinstance(data, dict):
        return False
    decision = data.get("decision")
    return (
        isinstance(decision, dict)
        and decision.get("outcome") == "deny"
        and decision.get("exitCode") == exit_code
    )


def run_action(
    arguments: Sequence[str],
    environ: Mapping[str, str],
    *,
    stderr: TextIO,
    attest_executable: Path = _ATTEST_EXECUTABLE,
) -> int:
    """Execute one closed Action invocation and return its process exit."""
    try:
        inputs = _parse_inputs(arguments, environ)
        if inputs.mode == "run":
            _require_oidc(environ)
        event = _resolve_event(environ)
        repository = _repository_path(environ)
        with tempfile.TemporaryDirectory(prefix="attest-action-") as temporary_name:
            temporary = Path(temporary_name).resolve(strict=True)
            home = temporary / "home"
            _prepare_home(home, repository)
            runtime = _complete_repository(repository, event, home)
            policy_path = (
                None
                if inputs.policy is None
                else _read_repository_file(
                    repository,
                    inputs.policy,
                    maximum_size=_POLICY_LIMIT,
                    json_file=False,
                )
            )
            bundle_path = (
                None
                if inputs.bundle is None
                else _read_repository_file(
                    repository,
                    inputs.bundle,
                    maximum_size=_BUNDLE_LIMIT,
                    json_file=True,
                )
            )
            if inputs.mode in {"verify", "gate"}:
                if inputs.bundle is None:
                    _raise("ERR-INTERNAL-001")
                _write_output(environ, "attestation-ref", inputs.bundle)
            cli_arguments, output_bundle = _cli_arguments(
                inputs,
                runtime,
                temporary,
                policy_path,
                bundle_path,
                attest_executable,
            )
            environment = _sanitized_environment(environ, inputs, home, attest_executable)
            process = _run_cli(
                cli_arguments,
                environment=environment,
                repository=repository,
            )
            report = _parse_report(process, inputs.mode)
            if report.get("outcome") == "failed":
                secrets_to_reject = frozenset(
                    value
                    for name in (
                        "GITHUB_TOKEN",
                        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
                    )
                    if isinstance((value := environ.get(name)), str)
                )
                error = _safe_diagnostic(report, secrets_to_reject=secrets_to_reject)
                _emit_error(error, stderr)
                return process.returncode

            facts = _report_facts(report, inputs)
            log_index = _extract_log_index(output_bundle)
            _write_output(environ, "changeset-digest", facts.digest)
            if facts.attestation_ref is not None and inputs.mode == "run":
                _write_output(environ, "attestation-ref", facts.attestation_ref)
            _write_output(environ, "decision", facts.decision)
            if log_index is not None:
                _write_output(environ, "log-index", log_index)
            _write_summary(environ, facts)
            if _policy_exit_is_advisory(report, inputs):
                return 0
            return process.returncode
    except ActionError as action_error:
        _emit_error(action_error, stderr)
        return action_error.exit_code
    except Exception:
        internal_error = _ERRORS["ERR-INTERNAL-001"]
        _emit_error(internal_error, stderr)
        return internal_error.exit_code


def main() -> int:
    """Run the production Action boundary."""
    return run_action(sys.argv[1:], os.environ, stderr=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
