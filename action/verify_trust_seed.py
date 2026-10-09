"""Verify the reviewed Action TUF cache seed from Sigstore's embedded roots."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import stat
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, Never
from urllib.parse import quote

from sigstore._internal.tuf import DEFAULT_TUF_URL, STAGING_TUF_URL
from sigstore._utils import read_embedded
from tuf.api.metadata import Root, Targets  # type: ignore[attr-defined]  # TUF omits re-exports.
from tuf.ngclient._internal.trusted_metadata_set import TrustedMetadataSet
from tuf.ngclient.config import EnvelopeType

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

_DIGEST: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
_CAPTURED_AT: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_TARGET_NAMES: Final[tuple[str, ...]] = ("signing_config.v0.2.json", "trusted_root.json")
_URLS: Final[dict[str, str]] = {
    "production": DEFAULT_TUF_URL,
    "staging": STAGING_TUF_URL,
}


class SeedError(ValueError):
    """The trust seed violates its closed cryptographic contract."""


def _invalid() -> Never:
    raise SeedError


def _object_pairs(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _load_document(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 1024 * 1024 or raw.startswith(b"\xef\xbb\xbf"):
            _invalid()
        decoded: JsonValue = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=lambda _value: _invalid(),
        )
        if not isinstance(decoded, dict):
            _invalid()
    except (OSError, RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise SeedError from error
    return decoded


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        _invalid()
    return value


def _string(value: JsonValue) -> str:
    if not isinstance(value, str):
        _invalid()
    return value


def _positive_integer(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _invalid()
    return value


def _path(value: JsonValue) -> PurePosixPath:
    rendered = _string(value)
    path = PurePosixPath(rendered)
    if (
        not rendered
        or path.is_absolute()
        or path == PurePosixPath(".")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _invalid()
    return path


def _strings(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        _invalid()
    rendered: list[str] = []
    for item in value:
        if not isinstance(item, str):
            _invalid()
        rendered.append(item)
    if len(rendered) != len(set(rendered)):
        _invalid()
    return tuple(rendered)


def _regular_files(root: Path) -> frozenset[PurePosixPath]:
    observed: set[PurePosixPath] = set()
    for path in root.rglob("*"):
        metadata = path.lstat()
        if path.is_symlink():
            _invalid()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            _invalid()
        observed.add(PurePosixPath(path.relative_to(root).as_posix()))
    return frozenset(observed)


def _source(root: Path, relative: PurePosixPath, digests: dict[PurePosixPath, str]) -> bytes:
    try:
        expected = digests[relative]
        encoded = root.joinpath(*relative.parts).read_bytes()
        if not encoded.endswith(b"\n") or b"\n" in encoded[:-1] or b"\r" in encoded:
            _invalid()
        content = base64.b64decode(encoded[:-1], validate=True)
    except (binascii.Error, KeyError, OSError, ValueError) as error:
        raise SeedError from error
    if hashlib.sha256(content).hexdigest() != expected:
        _invalid()
    return content


def _expected_runtime_files(
    environment: str,
    url: str,
    root_updates: tuple[PurePosixPath, ...],
) -> dict[PurePosixPath, PurePosixPath]:
    encoded_url = quote(url, safe="")
    data = PurePosixPath(".local/share/sigstore-python/tuf") / encoded_url
    cache = PurePosixPath(".cache/sigstore-python/tuf") / encoded_url
    expected = {
        PurePosixPath(environment) / "snapshot.json.b64": data / "snapshot.json",
        PurePosixPath(environment) / "targets.json.b64": data / "targets.json",
        **{PurePosixPath(environment) / f"{name}.b64": cache / name for name in _TARGET_NAMES},
    }
    for root_update in root_updates:
        version = root_update.name.removesuffix(".root.json.b64")
        if not version.isdigit():
            _invalid()
        expected[root_update] = data / "root_history" / root_update.name.removesuffix(".b64")
    return expected


def _verify_environment(
    root: Path,
    name: str,
    document: JsonObject,
    captured_at: datetime,
    digests: dict[PurePosixPath, str],
) -> frozenset[PurePosixPath]:
    if set(document) != {
        "rootUpdates",
        "runtimeFiles",
        "snapshot",
        "targets",
        "timestamp",
        "url",
        "versions",
    }:
        _invalid()
    url = _string(document["url"])
    if url != _URLS[name]:
        _invalid()
    root_updates = tuple(_path(value) for value in _strings(document["rootUpdates"]))
    timestamp = _path(document["timestamp"])
    snapshot = _path(document["snapshot"])
    targets = _path(document["targets"])
    environment_root = PurePosixPath(name)
    if (
        timestamp != environment_root / "timestamp.json.b64"
        or snapshot != environment_root / "snapshot.json.b64"
        or targets != environment_root / "targets.json.b64"
        or any(path.parent != environment_root for path in root_updates)
    ):
        _invalid()
    runtime_document = _object(document["runtimeFiles"])
    runtime_files = {
        _path(source): _path(destination) for source, destination in runtime_document.items()
    }
    if runtime_files != _expected_runtime_files(name, url, root_updates):
        _invalid()
    versions = _object(document["versions"])
    if set(versions) != {"root", "snapshot", "targets", "timestamp"}:
        _invalid()

    trusted = TrustedMetadataSet(read_embedded("root.json", url), EnvelopeType.METADATA)
    trusted.reference_time = captured_at
    for relative in root_updates:
        trusted.update_root(_source(root, relative, digests))
    trusted.update_timestamp(_source(root, timestamp, digests))
    trusted.update_snapshot(_source(root, snapshot, digests))
    trusted.update_delegated_targets(_source(root, targets, digests), Targets.type, Root.type)
    if {
        "root": trusted.root.version,
        "timestamp": trusted.timestamp.version,
        "snapshot": trusted.snapshot.version,
        "targets": trusted.targets.version,
    } != {role: _positive_integer(version) for role, version in versions.items()}:
        _invalid()
    for target_name in _TARGET_NAMES:
        relative = environment_root / f"{target_name}.b64"
        try:
            target = trusted.targets.targets[target_name]
        except KeyError as error:
            raise SeedError from error
        target.verify_length_and_hashes(_source(root, relative, digests))
    return frozenset({timestamp, snapshot, targets, *root_updates, *runtime_files})


def verify(root: Path) -> tuple[str, ...]:
    """Verify the complete closed seed and return its environment names."""
    if not root.is_dir() or root.is_symlink():
        _invalid()
    manifest = _load_document(root / "manifest.json")
    if set(manifest) != {"capturedAt", "encoding", "environments", "files", "schemaVersion"}:
        _invalid()
    if manifest["schemaVersion"] != 1 or manifest["encoding"] != "base64":
        _invalid()
    captured = _string(manifest["capturedAt"])
    if _CAPTURED_AT.fullmatch(captured) is None:
        _invalid()
    captured_at = datetime.fromisoformat(captured.replace("Z", "+00:00"))

    files_document = _object(manifest["files"])
    digests: dict[PurePosixPath, str] = {}
    for raw_path, raw_digest in files_document.items():
        relative = _path(raw_path)
        digest = _string(raw_digest)
        if _DIGEST.fullmatch(digest) is None or relative in digests:
            _invalid()
        digests[relative] = digest

    environments = _object(manifest["environments"])
    if set(environments) != set(_URLS):
        _invalid()
    referenced: set[PurePosixPath] = set()
    for name in sorted(_URLS):
        referenced.update(
            _verify_environment(
                root,
                name,
                _object(environments[name]),
                captured_at,
                digests,
            )
        )
    if referenced != set(digests):
        _invalid()
    if _regular_files(root) != {*digests, PurePosixPath("manifest.json")}:
        _invalid()
    for relative in digests:
        _source(root, relative, digests)
    return tuple(sorted(_URLS))


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one seed directory without exposing parser or signature diagnostics."""
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        if len(arguments) != 1:
            _invalid()
        environments = verify(Path(arguments[0]).resolve(strict=True))
    except Exception:
        sys.stderr.write("invalid TUF cache seed\n")
        return 1
    sys.stdout.write(f"verified TUF cache seed for {', '.join(environments)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
