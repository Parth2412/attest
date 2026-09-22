"""Read-only, closed sidecar claim collection governed by BRD-F03."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Final, cast

from attest_collect._strict_json import decode_json
from attest_collect.authorship import (
    AuthorshipWarning,
    ClaimCollectorResult,
    CollectContext,
    authorship_warning,
)
from attest_core import AuthorshipClaim, ClaimSource, ClaimSourceKind, encode_git_path

_SIDECAR_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schemaVersion",
        "claimId",
        "agent",
        "model",
        "sessionId",
        "promptDigest",
        "scope",
        "claimedAt",
        "prompt",
    }
)
_SCHEMA_VERSION: Final[str] = "0.1.0"
_UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"


class _SidecarValidationError(ValueError):
    has_prompt: bool

    def __init__(self, *, has_prompt: bool) -> None:
        self.has_prompt = has_prompt
        super().__init__()


def _reference(raw_name: bytes) -> str:
    return f".attest/claims.d/{encode_git_path(raw_name)}"


def _directory_fd(directory: Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    return os.open(directory, flags)


def _read_regular(directory_fd: int, name: str) -> bytes:
    raw_name = os.fsencode(name)
    details = os.stat(raw_name, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise OSError
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(raw_name, flags, dir_fd=directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def _validated_claim(
    payload: dict[str, object],
    filename: str,
    reference: str,
    raw: bytes,
) -> AuthorshipClaim:
    if not set(payload) <= _SIDECAR_FIELDS:
        raise ValueError
    if payload.get("schemaVersion") != _SCHEMA_VERSION:
        raise ValueError
    claim_id = payload.get("claimId")
    if not isinstance(claim_id, str) or filename != f"{claim_id}.json":
        raise ValueError
    values = {
        key: value for key, value in payload.items() if key not in {"schemaVersion", "prompt"}
    }
    values["source"] = ClaimSource(
        kind=ClaimSourceKind.SIDECAR,
        reference=reference,
        digest=hashlib.sha256(raw).hexdigest(),
    )
    return AuthorshipClaim.model_validate(values)


def _claim(raw: bytes, filename: str, reference: str) -> tuple[AuthorshipClaim, bool]:
    if raw.startswith(_UTF8_BOM):
        raise ValueError
    parsed = decode_json(raw.decode("utf-8"))
    if not isinstance(parsed, dict) or any(not isinstance(key, str) for key in parsed):
        raise ValueError
    payload = cast(dict[str, object], parsed)
    has_prompt = "prompt" in payload
    try:
        return _validated_claim(payload, filename, reference, raw), has_prompt
    except ValueError as error:
        raise _SidecarValidationError(has_prompt=has_prompt) from error


class SidecarCollector:
    """Collect regular sidecars while isolating malformed siblings (REQ-F03-010/130)."""

    kind = ClaimSourceKind.SIDECAR

    def collect(self, ctx: CollectContext) -> ClaimCollectorResult:
        directory = ctx.repo_path / ".attest" / "claims.d"
        try:
            directory_details = directory.lstat()
        except FileNotFoundError:
            return ClaimCollectorResult(claims=(), warnings=())
        except OSError:
            warning = authorship_warning("ERR-COLLECT-112", ".attest/claims.d")
            return ClaimCollectorResult(claims=(), warnings=(warning,))
        if not stat.S_ISDIR(directory_details.st_mode):
            warning = authorship_warning("ERR-COLLECT-112", ".attest/claims.d")
            return ClaimCollectorResult(claims=(), warnings=(warning,))

        try:
            descriptor = _directory_fd(directory)
        except OSError:
            warning = authorship_warning("ERR-COLLECT-112", ".attest/claims.d")
            return ClaimCollectorResult(claims=(), warnings=(warning,))
        try:
            names = sorted(
                os.listdir(descriptor),  # noqa: PTH208 -- retain the verified directory handle
                key=os.fsencode,
            )
        except OSError:
            os.close(descriptor)
            warning = authorship_warning("ERR-COLLECT-112", ".attest/claims.d")
            return ClaimCollectorResult(claims=(), warnings=(warning,))

        claims: list[AuthorshipClaim] = []
        warnings: list[AuthorshipWarning] = []
        try:
            for name in names:
                raw_name = os.fsencode(name)
                if not raw_name.endswith(b".json"):
                    continue
                reference = _reference(raw_name)
                has_prompt = False
                try:
                    filename = raw_name.decode("ascii")
                    raw = _read_regular(descriptor, name)
                    claim, has_prompt = _claim(raw, filename, reference)
                except _SidecarValidationError as error:
                    has_prompt = error.has_prompt
                    warnings.append(authorship_warning("ERR-COLLECT-111", reference))
                except (OSError, UnicodeError, ValueError):
                    warnings.append(authorship_warning("ERR-COLLECT-111", reference))
                else:
                    claims.append(claim)
                if has_prompt:
                    warnings.append(authorship_warning("WARN-COLLECT-003", reference))
        finally:
            os.close(descriptor)
        return ClaimCollectorResult(
            claims=tuple(claims),
            warnings=tuple(sorted(warnings, key=lambda warning: (warning.code, warning.reference))),
        )
