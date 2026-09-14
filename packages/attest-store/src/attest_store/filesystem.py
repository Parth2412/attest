"""Containment-safe filesystem storage governed by BRD-F07 and ADR-043."""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from attest_store._metadata import (
    StoreMetadata,
    bundle_digest,
    metadata_bytes,
    normalize_time,
    parse_metadata,
    validate_bundle,
    validate_content,
    validate_digest,
    validate_since,
)
from attest_store.errors import StoreError, store_error
from attest_store.protocols import StoreRef

_LOCK_NAME: Final = ".attest-store.lock"
_ENTRY_PATTERN: Final = re.compile(
    r"(?P<digest>[0-9a-f]{64})(?:\.(?P<suffix>[1-9][0-9]*))?\.sigstore\.json"
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _configured_path(value: object) -> Path:
    if not isinstance(value, Path | str):
        raise store_error("ERR-STORE-405")
    path = Path(value)
    if any(ord(character) < 32 for character in os.fspath(path)):
        raise store_error("ERR-STORE-405")
    return path


def _configured_clock(value: object) -> Callable[[], datetime]:
    if not callable(value):
        raise store_error("ERR-STORE-405")
    return cast(Callable[[], datetime], value)


class FilesystemStore:
    """Store exact Bundle bytes and companion metadata in one directory."""

    def __init__(self, directory: Path | str, *, clock: Callable[[], datetime] = _utc_now) -> None:
        configured = _configured_path(directory)
        validated_clock = _configured_clock(clock)
        try:
            if not configured.is_absolute() or configured.is_symlink() or not configured.is_dir():
                raise store_error("ERR-STORE-405")
            resolved = configured.resolve(strict=True)
            opened = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY)
            try:
                opened_stat = os.fstat(opened)
                path_stat = resolved.stat(follow_symlinks=False)
                if (opened_stat.st_dev, opened_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
                    raise store_error("ERR-STORE-405")
            finally:
                os.close(opened)
        except StoreError:
            raise
        except (OSError, RuntimeError):
            raise store_error("ERR-STORE-405") from None
        self._directory = resolved
        self._device_inode = (path_stat.st_dev, path_stat.st_ino)
        self._clock = validated_clock

    @property
    def directory(self) -> Path:
        """Return the resolved configured fallback directory."""
        return self._directory

    def _open_directory(self) -> int:
        try:
            descriptor = os.open(self._directory, os.O_RDONLY | os.O_DIRECTORY)
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != self._device_inode:
                os.close(descriptor)
                raise store_error("ERR-STORE-404")
        except StoreError:
            raise
        except OSError:
            raise store_error("ERR-STORE-404") from None
        else:
            return descriptor

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[int]:
        directory_fd = self._open_directory()
        lock_fd = -1
        try:
            flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
            lock_fd = os.open(_LOCK_NAME, flags, 0o600, dir_fd=directory_fd)
            lock_stat = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode):
                raise store_error("ERR-STORE-404")
            fcntl.flock(lock_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield directory_fd
        except StoreError:
            raise
        except OSError:
            raise store_error("ERR-STORE-404") from None
        finally:
            if lock_fd >= 0:
                os.close(lock_fd)
            os.close(directory_fd)

    @staticmethod
    def _read_file(directory_fd: int, name: str) -> bytes:
        descriptor = -1
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise store_error("ERR-STORE-404")
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        except StoreError:
            raise
        except OSError:
            raise store_error("ERR-STORE-404") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _entry_names(directory_fd: int) -> list[str]:
        try:
            names = os.listdir(directory_fd)
        except OSError:
            raise store_error("ERR-STORE-404") from None
        candidates = {
            name.removesuffix(".store.json") if name.endswith(".store.json") else name
            for name in names
        }
        return sorted(name for name in candidates if _ENTRY_PATTERN.fullmatch(name) is not None)

    def _read_entry(self, directory_fd: int, name: str) -> tuple[StoreRef, bytes]:
        match = _ENTRY_PATTERN.fullmatch(name)
        if match is None:
            raise store_error("ERR-STORE-404")
        digest = match.group("digest")
        bundle = self._read_file(directory_fd, name)
        metadata = parse_metadata(self._read_file(directory_fd, f"{name}.store.json"))
        validate_content(metadata, digest, bundle)
        reference = StoreRef(
            backend="filesystem",
            digest=digest,
            bundle_digest=metadata.bundle_digest,
            location=str(self._directory / name),
            stored_at=metadata.stored_at,
        )
        return reference, bundle

    @staticmethod
    def _write_all(descriptor: int, content: bytes) -> None:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise store_error("ERR-STORE-404")
            view = view[written:]

    @staticmethod
    def _write_temporary(directory_fd: int, name: str, content: bytes) -> str:
        temporary = f".{name}.{secrets.token_hex(16)}.tmp"
        descriptor = -1
        completed = False
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            FilesystemStore._write_all(descriptor, content)
            os.fsync(descriptor)
            completed = True
        except StoreError:
            raise
        except OSError:
            raise store_error("ERR-STORE-404") from None
        else:
            return temporary
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not completed:
                FilesystemStore._unlink_if_present(directory_fd, temporary)

    @staticmethod
    def _unlink_if_present(directory_fd: int, name: str) -> None:
        with suppress(FileNotFoundError):
            os.unlink(name, dir_fd=directory_fd)

    def _publish_pair(
        self,
        directory_fd: int,
        name: str,
        bundle: bytes,
        metadata: bytes,
    ) -> None:
        metadata_name = f"{name}.store.json"
        bundle_temporary = self._write_temporary(directory_fd, name, bundle)
        metadata_temporary = ""
        bundle_published = False
        metadata_published = False
        try:
            metadata_temporary = self._write_temporary(directory_fd, metadata_name, metadata)
            os.link(
                bundle_temporary,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            bundle_published = True
            os.link(
                metadata_temporary,
                metadata_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            metadata_published = True
            os.fsync(directory_fd)
        except OSError:
            if bundle_published:
                self._unlink_if_present(directory_fd, name)
            if metadata_published:
                self._unlink_if_present(directory_fd, metadata_name)
            raise store_error("ERR-STORE-404") from None
        finally:
            self._unlink_if_present(directory_fd, bundle_temporary)
            if metadata_temporary:
                self._unlink_if_present(directory_fd, metadata_temporary)

    def put(self, digest: str, bundle: bytes) -> StoreRef:
        """Create one exact Bundle entry without overwriting (REQ-F07-020/060/100)."""
        validated_digest = validate_digest(digest)
        validated_bundle = validate_bundle(bundle)
        try:
            stored_at = normalize_time(self._clock())
        except StoreError:
            raise
        except Exception:
            raise store_error("ERR-STORE-405") from None
        digest_of_bundle = bundle_digest(validated_bundle)

        with self._locked(exclusive=True) as directory_fd:
            existing_names = [
                name
                for name in self._entry_names(directory_fd)
                if _ENTRY_PATTERN.fullmatch(name).group("digest") == validated_digest  # type: ignore[union-attr]
            ]
            for name in existing_names:
                reference, existing_bundle = self._read_entry(directory_fd, name)
                if reference.bundle_digest == digest_of_bundle:
                    if existing_bundle != validated_bundle:
                        raise store_error("ERR-STORE-404")
                    return reference

            occupied = set(existing_names)
            suffix = 0
            while True:
                name = (
                    f"{validated_digest}.sigstore.json"
                    if suffix == 0
                    else f"{validated_digest}.{suffix}.sigstore.json"
                )
                if name not in occupied:
                    break
                suffix += 1
            metadata = StoreMetadata(
                digest=validated_digest,
                bundle_digest=digest_of_bundle,
                size=len(validated_bundle),
                stored_at=stored_at,
            )
            self._publish_pair(
                directory_fd,
                name,
                validated_bundle,
                metadata_bytes(metadata),
            )
            return StoreRef(
                backend="filesystem",
                digest=validated_digest,
                bundle_digest=digest_of_bundle,
                location=str(self._directory / name),
                stored_at=stored_at,
            )

    def get(self, digest: str) -> list[bytes]:
        """Return exact bytes in Bundle-digest order without semantic parsing."""
        validated_digest = validate_digest(digest)
        with self._locked(exclusive=False) as directory_fd:
            entries = [
                self._read_entry(directory_fd, name)
                for name in self._entry_names(directory_fd)
                if _ENTRY_PATTERN.fullmatch(name).group("digest") == validated_digest  # type: ignore[union-attr]
            ]
        if not entries:
            raise store_error("ERR-STORE-403")
        entries.sort(key=lambda entry: entry[0].bundle_digest)
        return [bundle for _, bundle in entries]

    def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
        """List complete entries by inclusive UTC storage time."""
        threshold = validate_since(since)
        with self._locked(exclusive=False) as directory_fd:
            references = [
                self._read_entry(directory_fd, name)[0] for name in self._entry_names(directory_fd)
            ]
        if threshold is not None:
            references = [item for item in references if item.stored_at >= threshold]
        return iter(
            sorted(
                references,
                key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
            )
        )
