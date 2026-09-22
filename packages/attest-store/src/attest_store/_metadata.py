"""Shared storage metadata and validation governed by ADR-043."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TypeGuard, cast
from urllib.parse import urlsplit

from attest_core import JsonValue, canonicalize
from attest_store.errors import StoreError, store_error

_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_METADATA_FIELDS = frozenset({"version", "changeSetDigest", "bundleDigest", "size", "storedAt"})
_MAX_METADATA_BYTES = 4096


@dataclass(frozen=True, slots=True)
class StoreMetadata:
    """Represent one validated version 1 storage binding."""

    digest: str
    bundle_digest: str
    size: int
    stored_at: datetime


def validate_digest(value: object) -> str:
    """Return one canonical lowercase SHA-256 value or ERR-STORE-405."""
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise store_error("ERR-STORE-405")
    return value


def validate_bundle(value: object) -> bytes:
    """Require immutable exact bytes without interpreting Bundle semantics."""
    if not isinstance(value, bytes):
        raise store_error("ERR-STORE-405")
    return value


def validate_location(value: object) -> str:
    """Reject empty, control-bearing, or credential-bearing public locators."""
    if not isinstance(value, str) or not value or any(ord(character) < 32 for character in value):
        raise store_error("ERR-STORE-405")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise store_error("ERR-STORE-405") from None
    if parsed.scheme and (parsed.username is not None or parsed.password is not None):
        raise store_error("ERR-STORE-405")
    return value


def normalize_time(value: object) -> datetime:
    """Normalise one aware datetime to UTC at storage precision."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise store_error("ERR-STORE-405")
    return value.astimezone(UTC).replace(microsecond=0)


def validate_stored_time(value: object) -> datetime:
    """Require the canonical timestamp representation exposed by StoreRef."""
    normalised = normalize_time(value)
    if value != normalised:
        raise store_error("ERR-STORE-405")
    return normalised


def validate_since(value: object) -> datetime | None:
    """Validate and UTC-normalise an inclusive list filter."""
    if value is None:
        return None
    return normalize_time(value)


def is_positive_timeout(value: object) -> TypeGuard[timedelta]:
    """Return whether ``value`` is a finite positive timedelta."""
    return isinstance(value, timedelta) and timedelta(0) < value < timedelta.max


def format_time(value: datetime) -> str:
    """Render a validated storage timestamp as second-precision RFC 3339 UTC."""
    normalised = normalize_time(value)
    return normalised.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: object) -> datetime:
    """Parse only the canonical storage timestamp form or report corruption."""
    if not isinstance(value, str) or _TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise store_error("ERR-STORE-404")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise store_error("ERR-STORE-404") from None
    if format_time(parsed) != value:
        raise store_error("ERR-STORE-404")
    return parsed


def bundle_digest(bundle: bytes) -> str:
    """Return the lowercase SHA-256 of exact Bundle bytes."""
    return sha256(bundle).hexdigest()


def metadata_bytes(metadata: StoreMetadata) -> bytes:
    """Return the closed RFC 8785 version 1 metadata object."""
    value: dict[str, JsonValue] = {
        "version": 1,
        "changeSetDigest": metadata.digest,
        "bundleDigest": metadata.bundle_digest,
        "size": metadata.size,
        "storedAt": format_time(metadata.stored_at),
    }
    try:
        return canonicalize(value)
    except Exception:
        raise store_error("ERR-STORE-404") from None


def _closed_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise store_error("ERR-STORE-404")
        result[key] = value
    return result


def _metadata_digest(value: object) -> str:
    try:
        return validate_digest(value)
    except StoreError:
        raise store_error("ERR-STORE-404") from None


def parse_metadata(raw: bytes) -> StoreMetadata:
    """Parse, close, and canonicality-check persisted storage metadata."""
    if len(raw) > _MAX_METADATA_BYTES:
        raise store_error("ERR-STORE-404")
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_closed_object_pairs)
    except (StoreError, TypeError, ValueError, UnicodeError):
        raise store_error("ERR-STORE-404") from None
    if not isinstance(decoded, dict):
        raise store_error("ERR-STORE-404")
    value = cast(dict[str, object], decoded)
    if set(value) != _METADATA_FIELDS or value["version"] != 1:
        raise store_error("ERR-STORE-404")
    digest = _metadata_digest(value["changeSetDigest"])
    digest_of_bundle = _metadata_digest(value["bundleDigest"])
    size = value["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise store_error("ERR-STORE-404")
    metadata = StoreMetadata(
        digest=digest,
        bundle_digest=digest_of_bundle,
        size=size,
        stored_at=parse_time(value["storedAt"]),
    )
    if metadata_bytes(metadata) != raw:
        raise store_error("ERR-STORE-404")
    return metadata


def validate_content(metadata: StoreMetadata, digest: str, bundle: bytes) -> None:
    """Fail closed unless persisted metadata binds the exact content."""
    if (
        metadata.digest != digest
        or metadata.size != len(bundle)
        or metadata.bundle_digest != bundle_digest(bundle)
    ):
        raise store_error("ERR-STORE-404")
