"""Bounded no-follow reads and atomic application-layer writes for F-10."""

from __future__ import annotations

import json
import os
import secrets
import stat
from contextlib import suppress
from pathlib import Path
from typing import Final, Never, cast

from attest_cli.errors import CliError, CliErrorCode, cli_error

_READ_CHUNK: Final[int] = 1024 * 1024


class MissingInputError(RuntimeError):
    """Signal a missing required input without exposing its path."""


def _invalid() -> Never:
    raise ValueError


def _failed_io() -> Never:
    raise OSError


def _absolute(path: Path | str) -> Path:
    if not isinstance(path, Path | str):
        raise TypeError
    rendered = os.fspath(path)
    if not rendered or "\x00" in rendered:
        raise ValueError
    # Lexical absolute normalization is deliberate: resolve() would follow forbidden symlinks.
    return Path(os.path.abspath(rendered))  # noqa: PTH100


def _open_parent(path: Path | str) -> tuple[int, str]:
    absolute = _absolute(path)
    name = absolute.name
    if name in {"", ".", ".."}:
        raise ValueError
    descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in absolute.parts[1:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, name  # noqa: TRY300
    except Exception:
        os.close(descriptor)
        raise


def ensure_directory(path: Path | str) -> Path:
    """Create or validate one absolute directory path without following symlinks."""
    descriptor = -1
    try:
        absolute = _absolute(path)
        descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for component in absolute.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
                os.fsync(descriptor)
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=descriptor,
                )
            os.close(descriptor)
            descriptor = next_descriptor
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            _invalid()
    except CliError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise cli_error("ERR-CONFIG-004") from None
    else:
        return absolute
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISREG(left.st_mode)
        and stat.S_ISREG(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
    )


def read_regular_file(
    path: Path | str,
    *,
    maximum_size: int,
    error_code: CliErrorCode,
    distinguish_missing: bool = False,
) -> bytes:
    """Read one stable bounded regular file without following any path symlink."""
    directory_fd = -1
    file_fd = -1
    try:
        size_value = cast(object, maximum_size)
        if isinstance(size_value, bool) or not isinstance(size_value, int) or size_value < 0:
            _invalid()
        try:
            directory_fd, name = _open_parent(path)
            before_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            if distinguish_missing:
                raise MissingInputError from None
            raise
        if not stat.S_ISREG(before_path.st_mode) or before_path.st_size > maximum_size:
            _invalid()
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
        before_fd = os.fstat(file_fd)
        if not _same_file(before_path, before_fd):
            _invalid()

        chunks: list[bytes] = []
        remaining = maximum_size + 1
        while remaining:
            chunk = os.read(file_fd, min(_READ_CHUNK, remaining))
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
            or not _same_file(before_fd, after_fd)
            or not _same_file(after_fd, after_path)
        ):
            _invalid()
        return content  # noqa: TRY300
    except (CliError, MissingInputError):
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise cli_error(error_code) from None
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _reject_constant(_value: str) -> None:
    raise ValueError


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def decode_json_object(
    raw: bytes,
    *,
    error_code: CliErrorCode = "ERR-CONFIG-003",
) -> dict[str, object]:
    """Decode exactly one strict UTF-8 JSON object."""
    try:
        raw_value = cast(object, raw)
        if not isinstance(raw_value, bytes) or raw_value.startswith(b"\xef\xbb\xbf"):
            _invalid()
        text = raw.decode("utf-8", errors="strict")
        value: object = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
        if not isinstance(value, dict):
            _invalid()
        return cast(dict[str, object], value)
    except (TypeError, UnicodeError, ValueError):
        raise cli_error(error_code) from None


def read_json_object(path: Path | str, *, maximum_size: int) -> dict[str, object]:
    """Read and strictly decode one bounded JSON object."""
    return decode_json_object(
        read_regular_file(path, maximum_size=maximum_size, error_code="ERR-CONFIG-003")
    )


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _failed_io()
        view = view[written:]


def _target_stat(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def write_atomic(path: Path | str, content: bytes, *, overwrite: bool) -> None:
    """Publish exact bytes atomically, create-only unless explicit replacement is requested."""
    directory_fd = -1
    temporary_fd = -1
    temporary_name: str | None = None
    try:
        content_value = cast(object, content)
        overwrite_value = cast(object, overwrite)
        if not isinstance(content_value, bytes) or not isinstance(overwrite_value, bool):
            _invalid()
        directory_fd, name = _open_parent(path)
        original = _target_stat(directory_fd, name)
        if original is not None and (not overwrite or not stat.S_ISREG(original.st_mode)):
            _invalid()

        for _ in range(16):
            candidate = f".{name}.attest-{secrets.token_hex(12)}"
            try:
                temporary_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory_fd,
                )
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        if temporary_fd < 0 or temporary_name is None:
            _failed_io()
        os.fchmod(temporary_fd, 0o600)
        _write_all(temporary_fd, content)
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1

        current = _target_stat(directory_fd, name)
        if original is None:
            if current is not None:
                _invalid()
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=directory_fd)
            temporary_name = None
        else:
            if current is None or not _same_file(original, current):
                _invalid()
            os.replace(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_name = None
        os.fsync(directory_fd)
    except CliError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise cli_error("ERR-CONFIG-004") from None
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name is not None and directory_fd >= 0:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_fd)
        if directory_fd >= 0:
            os.close(directory_fd)
