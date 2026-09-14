"""Create-only Git-ref storage governed by BRD-F07, ADR-014, and ADR-043."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess  # nosec B404
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal, Protocol, cast

from attest_store._metadata import (
    StoreMetadata,
    bundle_digest,
    is_positive_timeout,
    metadata_bytes,
    normalize_time,
    parse_metadata,
    validate_bundle,
    validate_content,
    validate_digest,
    validate_location,
    validate_since,
)
from attest_store.errors import StoreError, StoreErrorCode, store_error
from attest_store.filesystem import FilesystemStore
from attest_store.protocols import StoreRef

type GitBackend = Literal["auto", "pygit2", "subprocess"]

_DEFAULT_SUBPROCESS_TIMEOUT = timedelta(seconds=30)
_MAX_LOCATOR_INSPECTION_BYTES = 1024 * 1024
_SAFE_GIT_CONFIG = ("core.fsmonitor=false", f"core.hooksPath={os.devnull}")
_OID_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_REF_PATTERN = re.compile(
    r"refs/attestations/(?P<digest>[0-9a-f]{64})"
    r"(?:-(?:(?:0|[1-9][0-9]*)(?:-[0-9a-f]{64})?|sha256-[0-9a-f]{64}))?"
)
_TAG_PATTERN = re.compile(
    rb"object (?P<object>[0-9a-f]{40}|[0-9a-f]{64})\n"
    rb"type blob\n"
    rb"tag (?P<tag>[^\n]+)\n"
    rb"tagger attest <attest@invalid> (?P<seconds>-?[0-9]+) \+0000\n"
    rb"\n(?P<metadata>.*)\n",
    re.DOTALL,
)
_UNREACHABLE_PATTERNS: Final = (
    b"could not resolve host",
    b"could not resolve hostname",
    b"failed to connect",
    b"connection timed out",
    b"connection refused",
    b"connection reset",
    b"network is unreachable",
    b"no route to host",
    b"unable to access",
    b"unable to look up",
    b"does not appear to be a git repository",
    b"couldn't connect",
    b"could not read from remote repository",
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _repository_path(value: object) -> Path:
    if not isinstance(value, Path | str):
        raise store_error("ERR-STORE-405")
    path = Path(value)
    try:
        if (
            not path.is_absolute()
            or any(ord(character) < 32 for character in os.fspath(path))
            or path.is_symlink()
            or not path.is_dir()
        ):
            raise store_error("ERR-STORE-405")
        resolved = path.resolve(strict=True)
        _repository_identity(resolved, "ERR-STORE-405")
    except StoreError:
        raise
    except (OSError, RuntimeError):
        raise store_error("ERR-STORE-405") from None
    else:
        return resolved


def _repository_identity(path: Path, code: StoreErrorCode) -> tuple[int, int]:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError:
        raise store_error(code) from None
    if path.is_symlink() or not stat.S_ISDIR(status.st_mode):
        raise store_error(code)
    return status.st_dev, status.st_ino


def _configured_clock(value: object) -> Callable[[], datetime]:
    if not callable(value):
        raise store_error("ERR-STORE-405")
    return cast(Callable[[], datetime], value)


def _configured_timeout(value: object) -> timedelta:
    if not is_positive_timeout(value):
        raise store_error("ERR-STORE-405")
    return value


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _non_negative_log_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return None


def _extract_log_index(bundle: bytes) -> int | None:
    if len(bundle) > _MAX_LOCATOR_INSPECTION_BYTES:
        return None
    try:
        decoded: object = json.loads(bundle, object_pairs_hook=_object_pairs)
        if not isinstance(decoded, dict):
            return None
        material = cast(dict[str, object], decoded).get("verificationMaterial")
        if not isinstance(material, dict):
            return None
        entries = cast(dict[str, object], material).get("tlogEntries")
        if not isinstance(entries, list):
            return None
        indices = {
            parsed
            for entry in entries
            if isinstance(entry, dict)
            if (parsed := _non_negative_log_index(cast(dict[str, object], entry).get("logIndex")))
            is not None
        }
    except (RecursionError, TypeError, ValueError, UnicodeError):
        return None
    if len(indices) != 1:
        return None
    return next(iter(indices))


class _GitObjects(Protocol):
    def list_refs(self, prefix: str) -> list[tuple[str, str]]: ...

    def read_object(self, object_id: str, expected_type: str) -> bytes: ...

    def write_object(self, object_type: str, content: bytes) -> str: ...

    def create_ref(self, name: str, object_id: str) -> bool: ...


class _Pygit2Objects:
    def __init__(self, repository_path: Path) -> None:
        try:
            import pygit2

            self._repository_path = repository_path
            self._repository_identity = _repository_identity(repository_path, "ERR-STORE-405")
            self._repository: pygit2.Repository = pygit2.Repository(str(repository_path))
        except (ImportError, OSError, ValueError):
            raise store_error("ERR-STORE-405") from None
        except Exception:
            raise store_error("ERR-STORE-405") from None

    @classmethod
    def is_available(cls) -> bool:
        try:
            import pygit2  # noqa: F401
        except (ImportError, OSError):
            return False
        return True

    def _validate_repository(self) -> None:
        if (
            _repository_identity(self._repository_path, "ERR-STORE-404")
            != self._repository_identity
        ):
            raise store_error("ERR-STORE-404")

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        self._validate_repository()
        try:
            return sorted(
                (name, str(self._repository.references[name].target))
                for name in self._repository.references
                if name.startswith(prefix)
            )
        except Exception:
            raise store_error("ERR-STORE-404") from None

    def read_object(self, object_id: str, expected_type: str) -> bytes:
        import pygit2

        self._validate_repository()
        expected = {"blob": pygit2.GIT_OBJECT_BLOB, "tag": pygit2.GIT_OBJECT_TAG}[expected_type]
        try:
            object_type, data = self._repository.odb.read(pygit2.Oid(hex=object_id))
        except Exception:
            raise store_error("ERR-STORE-404") from None
        if object_type != expected:
            raise store_error("ERR-STORE-404")
        return data

    def write_object(self, object_type: str, content: bytes) -> str:
        import pygit2

        self._validate_repository()
        selected = {"blob": pygit2.GIT_OBJECT_BLOB, "tag": pygit2.GIT_OBJECT_TAG}[object_type]
        try:
            return str(self._repository.odb.write(selected, content))
        except Exception:
            raise store_error("ERR-STORE-404") from None

    def create_ref(self, name: str, object_id: str) -> bool:
        import pygit2

        self._validate_repository()
        try:
            self._repository.create_reference(name, pygit2.Oid(hex=object_id), force=False)
        except pygit2.AlreadyExistsError:
            return False
        except OSError:
            # libgit2 reports another process's transient ref lock as OSError.
            return False
        except Exception:
            raise store_error("ERR-STORE-404") from None
        return True


class _SubprocessObjects:
    def __init__(self, repository_path: Path, timeout: timedelta) -> None:
        executable = shutil.which("git")
        if executable is None:
            raise store_error("ERR-STORE-405")
        self._executable = executable
        self._repository_path = repository_path
        self._repository_identity = _repository_identity(repository_path, "ERR-STORE-405")
        self._timeout_seconds = timeout.total_seconds()
        try:
            result = self._run("rev-parse", "--git-dir")
        except (OSError, subprocess.TimeoutExpired):
            raise store_error("ERR-STORE-405") from None
        if result.returncode != 0:
            raise store_error("ERR-STORE-405")

    def _run(
        self, *arguments: str, input_bytes: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        if (
            _repository_identity(self._repository_path, "ERR-STORE-404")
            != self._repository_identity
        ):
            raise store_error("ERR-STORE-404")
        command = [self._executable, "--no-replace-objects"]
        for setting in _SAFE_GIT_CONFIG:
            command.extend(("-c", setting))
        command.extend(("-C", os.fspath(self._repository_path), *arguments))
        return subprocess.run(  # noqa: S603  # nosec B603
            command,
            input=input_bytes,
            capture_output=True,
            check=False,
            env=_git_environment(),
            timeout=self._timeout_seconds,
        )

    def _local_run(
        self, *arguments: str, input_bytes: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return self._run(*arguments, input_bytes=input_bytes)
        except (OSError, subprocess.TimeoutExpired):
            raise store_error("ERR-STORE-404") from None

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        result = self._local_run("for-each-ref", "--format=%(refname)%00%(objectname)", prefix)
        if result.returncode != 0:
            raise store_error("ERR-STORE-404")
        references: list[tuple[str, str]] = []
        try:
            for line in result.stdout.splitlines():
                name_bytes, object_bytes = line.split(b"\0", 1)
                name = name_bytes.decode("ascii")
                object_id = object_bytes.decode("ascii")
                if name.startswith(prefix):
                    references.append((name, object_id))
        except (UnicodeError, ValueError):
            raise store_error("ERR-STORE-404") from None
        return sorted(references)

    def read_object(self, object_id: str, expected_type: str) -> bytes:
        if _OID_PATTERN.fullmatch(object_id) is None:
            raise store_error("ERR-STORE-404")
        type_result = self._local_run("cat-file", "-t", object_id)
        if type_result.returncode != 0 or type_result.stdout != f"{expected_type}\n".encode():
            raise store_error("ERR-STORE-404")
        content_result = self._local_run("cat-file", expected_type, object_id)
        if content_result.returncode != 0:
            raise store_error("ERR-STORE-404")
        return content_result.stdout

    def write_object(self, object_type: str, content: bytes) -> str:
        arguments = ["hash-object", "-w", "--stdin"]
        if object_type != "blob":
            arguments[1:1] = ["-t", object_type]
        result = self._local_run(*arguments, input_bytes=content)
        try:
            object_id = result.stdout.decode("ascii").strip()
        except UnicodeError:
            raise store_error("ERR-STORE-404") from None
        if result.returncode != 0 or _OID_PATTERN.fullmatch(object_id) is None:
            raise store_error("ERR-STORE-404")
        return object_id

    def create_ref(self, name: str, object_id: str) -> bool:
        result = self._local_run("update-ref", name, object_id, "")
        if result.returncode == 0:
            return True
        if self.list_refs(name):
            return False
        raise store_error("ERR-STORE-404")

    def push(self, remote: str, reference: str) -> subprocess.CompletedProcess[bytes]:
        return self._run("push", "--porcelain", "--", remote, f"{reference}:{reference}")


def _read_reference(objects: _GitObjects, name: str, object_id: str) -> tuple[StoreRef, bytes]:
    match = _REF_PATTERN.fullmatch(name)
    if match is None or _OID_PATTERN.fullmatch(object_id) is None:
        raise store_error("ERR-STORE-404")
    tag_match = _TAG_PATTERN.fullmatch(objects.read_object(object_id, "tag"))
    if tag_match is None:
        raise store_error("ERR-STORE-404")
    try:
        target = tag_match.group("object").decode("ascii")
        tag_name = tag_match.group("tag").decode("utf-8")
        seconds = int(tag_match.group("seconds"))
    except (UnicodeError, ValueError):
        raise store_error("ERR-STORE-404") from None
    metadata = parse_metadata(tag_match.group("metadata"))
    if (
        tag_name != name.removeprefix("refs/")
        or seconds != int(metadata.stored_at.timestamp())
        or metadata.digest != match.group("digest")
    ):
        raise store_error("ERR-STORE-404")
    bundle = objects.read_object(target, "blob")
    validate_content(metadata, match.group("digest"), bundle)
    return (
        StoreRef(
            backend="git-ref",
            digest=metadata.digest,
            bundle_digest=metadata.bundle_digest,
            location=name,
            stored_at=metadata.stored_at,
        ),
        bundle,
    )


def _tag_bytes(blob_id: str, reference: str, metadata: StoreMetadata) -> bytes:
    seconds = int(metadata.stored_at.timestamp())
    header = (
        f"object {blob_id}\n"
        "type blob\n"
        f"tag {reference.removeprefix('refs/')}\n"
        f"tagger attest <attest@invalid> {seconds} +0000\n\n"
    ).encode()
    return header + metadata_bytes(metadata) + b"\n"


def _validate_reference(value: object) -> StoreRef:
    if (
        not isinstance(value, StoreRef)
        or value.backend != "git-ref"
        or _REF_PATTERN.fullmatch(value.location) is None
    ):
        raise store_error("ERR-STORE-405")
    return value


class GitRefStore:
    """Store exact Bundles as blobs behind hash-bound metadata tag refs."""

    def __init__(
        self,
        repository: Path | str,
        *,
        backend: GitBackend = "auto",
        clock: Callable[[], datetime] = _utc_now,
        subprocess_timeout: timedelta = _DEFAULT_SUBPROCESS_TIMEOUT,
    ) -> None:
        repository_path = _repository_path(repository)
        validated_clock = _configured_clock(clock)
        timeout = _configured_timeout(subprocess_timeout)
        if backend not in ("auto", "pygit2", "subprocess"):
            raise store_error("ERR-STORE-405")
        if backend == "pygit2" or (backend == "auto" and _Pygit2Objects.is_available()):
            objects: _GitObjects = _Pygit2Objects(repository_path)
            selected: Literal["pygit2", "subprocess"] = "pygit2"
        else:
            objects = _SubprocessObjects(repository_path, timeout)
            selected = "subprocess"
        self._repository = repository_path
        self._objects = objects
        self._backend = selected
        self._clock = validated_clock
        self._timeout = timeout

    @property
    def backend(self) -> Literal["pygit2", "subprocess"]:
        """Report the selected local Git implementation."""
        return self._backend

    def _entries(self, digest: str | None = None) -> list[tuple[StoreRef, bytes]]:
        entries = [
            _read_reference(self._objects, name, object_id)
            for name, object_id in self._objects.list_refs("refs/attestations/")
        ]
        if digest is None:
            return entries
        return [entry for entry in entries if entry[0].digest == digest]

    def put(self, digest: str, bundle: bytes) -> StoreRef:
        """Create one Git attestation ref without network access (REQ-F07-020/030/040)."""
        validated_digest = validate_digest(digest)
        validated_bundle = validate_bundle(bundle)
        try:
            stored_at = normalize_time(self._clock())
        except StoreError:
            raise
        except Exception:
            raise store_error("ERR-STORE-405") from None
        digest_of_bundle = bundle_digest(validated_bundle)
        metadata = StoreMetadata(
            digest=validated_digest,
            bundle_digest=digest_of_bundle,
            size=len(validated_bundle),
            stored_at=stored_at,
        )
        prefix = f"refs/attestations/{validated_digest}"
        log_index = _extract_log_index(validated_bundle)

        for _ in range(256):
            entries = self._entries(validated_digest)
            by_location = {reference.location: (reference, raw) for reference, raw in entries}
            for reference, raw in entries:
                if reference.bundle_digest == digest_of_bundle:
                    if raw != validated_bundle:
                        raise store_error("ERR-STORE-404")
                    return reference

            if prefix not in by_location:
                candidate = prefix
            elif log_index is None:
                candidate = f"{prefix}-sha256-{digest_of_bundle}"
            else:
                indexed = f"{prefix}-{log_index}"
                candidate = f"{indexed}-{digest_of_bundle}" if indexed in by_location else indexed
            if candidate in by_location:
                reference, raw = by_location[candidate]
                if reference.bundle_digest == digest_of_bundle and raw == validated_bundle:
                    return reference
                raise store_error("ERR-STORE-404")

            blob_id = self._objects.write_object("blob", validated_bundle)
            tag_id = self._objects.write_object("tag", _tag_bytes(blob_id, candidate, metadata))
            if self._objects.create_ref(candidate, tag_id):
                return StoreRef(
                    backend="git-ref",
                    digest=validated_digest,
                    bundle_digest=digest_of_bundle,
                    location=candidate,
                    stored_at=stored_at,
                )
        raise store_error("ERR-STORE-404")

    def get(self, digest: str) -> list[bytes]:
        """Return exact Git Bundle blobs in digest order without verification."""
        entries = self._entries(validate_digest(digest))
        if not entries:
            raise store_error("ERR-STORE-403")
        entries.sort(key=lambda entry: entry[0].bundle_digest)
        return [bundle for _, bundle in entries]

    def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
        """List complete Git-ref entries by persisted storage time."""
        threshold = validate_since(since)
        references = [reference for reference, _ in self._entries()]
        if threshold is not None:
            references = [reference for reference in references if reference.stored_at >= threshold]
        return iter(
            sorted(
                references,
                key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
            )
        )

    def push(
        self,
        reference: StoreRef,
        remote: str,
        fallback: FilesystemStore,
    ) -> StoreRef:
        """Push exactly one returned ref without force and preserve failures locally."""
        validated_reference = _validate_reference(reference)
        validated_remote = validate_location(remote)
        if validated_remote.startswith("-") or not isinstance(fallback, FilesystemStore):
            raise store_error("ERR-STORE-405")
        current = {
            item.location: (item, bundle)
            for item, bundle in self._entries(validated_reference.digest)
        }.get(validated_reference.location)
        if current is None or current[0] != validated_reference:
            raise store_error("ERR-STORE-404")
        bundle = current[1]
        try:
            result = _SubprocessObjects(self._repository, self._timeout).push(
                validated_remote, validated_reference.location
            )
            if result.returncode == 0:
                return validated_reference
            lowered = result.stderr.lower()
            code: StoreErrorCode = (
                "ERR-STORE-402"
                if any(pattern in lowered for pattern in _UNREACHABLE_PATTERNS)
                else "ERR-STORE-401"
            )
            primary_error = store_error(code)
        except (OSError, subprocess.TimeoutExpired):
            primary_error = store_error("ERR-STORE-402")
        except StoreError as error:
            primary_error = (
                error
                if error.code in ("ERR-STORE-401", "ERR-STORE-402")
                else store_error("ERR-STORE-402")
            )

        try:
            fallback_reference = fallback.put(validated_reference.digest, bundle)
        except StoreError:
            raise store_error("ERR-STORE-406") from primary_error
        raise store_error(
            primary_error.code, fallback_path=fallback_reference.location
        ) from primary_error
