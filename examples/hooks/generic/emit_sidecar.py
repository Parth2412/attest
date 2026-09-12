#!/usr/bin/env python3
"""Emit a minimal attest sidecar from a supported post-tool-use hook event."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import subprocess  # nosec B404
import sys
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

_MAX_INPUT_BYTES: Final[int] = 1_048_576
_PATCH_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Delete File: ",
    "*** Move to: ",
)
_SAFE_BYTES: Final[frozenset[int]] = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/"
)
_DIRECTORY_FLAGS: Final[int] = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _uuid7() -> str:
    timestamp_ms = time.time_ns() // 1_000_000
    value = bytearray(timestamp_ms.to_bytes(6, "big") + secrets.token_bytes(10))
    value[6] = 0x70 | (value[6] & 0x0F)
    value[8] = 0x80 | (value[8] & 0x3F)
    return str(uuid.UUID(bytes=bytes(value)))


def _encode_path(raw_path: bytes) -> str:
    return "".join(chr(byte) if byte in _SAFE_BYTES else f"%{byte:02X}" for byte in raw_path)


def _git_root(cwd: Path) -> Path | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    # ``which`` resolves the executable, and the argument vector is never interpreted by a shell.
    result = subprocess.run(  # noqa: S603  # nosec B603
        [executable, "-C", os.fspath(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return Path(os.fsdecode(result.stdout.rstrip(b"\r\n"))).resolve()
    except (OSError, UnicodeError):
        return None


def _relative_path(value: str, cwd: Path, root: Path) -> bytes | None:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    absolute = candidate.resolve()
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return b"/".join(os.fsencode(part) for part in relative.parts)


def _open_directory(parent_fd: int, name: str) -> int:
    with suppress(FileExistsError):
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    try:
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
    except OSError:
        os.close(descriptor)
        raise
    if not is_directory:
        os.close(descriptor)
        raise OSError
    return descriptor


def _claude_paths(payload: dict[str, object]) -> tuple[str, ...]:
    if payload.get("tool_name") not in {"Edit", "Write", "NotebookEdit"}:
        return ()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ()
    value = tool_input.get("file_path") or tool_input.get("notebook_path")
    return (value,) if isinstance(value, str) and value else ()


def _codex_paths(payload: dict[str, object]) -> tuple[str, ...]:
    if payload.get("tool_name") != "apply_patch":
        return ()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ()
    command = tool_input.get("command")
    if not isinstance(command, str):
        return ()
    paths: list[str] = []
    for line in command.splitlines():
        for prefix in _PATCH_PATH_PREFIXES:
            if line.startswith(prefix) and line != prefix:
                paths.append(line.removeprefix(prefix))
                break
    return tuple(paths)


def _write_claim(
    root: Path,
    *,
    agent_name: str,
    session_id: str,
    paths: tuple[str, ...],
) -> None:
    claim_id = _uuid7()
    payload = {
        "schemaVersion": "0.1.0",
        "claimId": claim_id,
        "agent": {"name": agent_name},
        "sessionId": session_id,
        "scope": {"paths": list(paths)},
        "claimedAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    root_fd = os.open(root, _DIRECTORY_FLAGS)
    attest_fd = -1
    claims_fd = -1
    try:
        attest_fd = _open_directory(root_fd, ".attest")
        claims_fd = _open_directory(attest_fd, "claims.d")
        temporary = f".{claim_id}.tmp"
        destination = f"{claim_id}.json"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=claims_fd,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(
                temporary,
                destination,
                src_dir_fd=claims_fd,
                dst_dir_fd=claims_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary, dir_fd=claims_fd)
            os.fsync(claims_fd)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=claims_fd)
    finally:
        if claims_fd >= 0:
            os.close(claims_fd)
        if attest_fd >= 0:
            os.close(attest_fd)
        os.close(root_fd)


def _emit(agent_name: str, input_kind: str) -> None:
    raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if len(raw) > _MAX_INPUT_BYTES:
        return
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        return
    payload = cast(dict[str, object], decoded)
    if payload.get("hook_event_name") != "PostToolUse":
        return
    cwd_value = payload.get("cwd")
    session_id = payload.get("session_id")
    if not isinstance(cwd_value, str) or not isinstance(session_id, str) or not session_id:
        return
    cwd = Path(cwd_value).resolve()
    root = _git_root(cwd)
    if root is None:
        return
    source_paths = _claude_paths(payload) if input_kind == "claude" else _codex_paths(payload)
    raw_paths = {
        path for value in source_paths if (path := _relative_path(value, cwd, root)) is not None
    }
    if not raw_paths:
        return
    paths = tuple(_encode_path(path) for path in sorted(raw_paths))
    _write_claim(root, agent_name=agent_name, session_id=session_id, paths=paths)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in {"claude", "codex"}:
        return 0
    try:
        _emit(sys.argv[1], sys.argv[2])
    except (OSError, OverflowError, UnicodeError, ValueError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
