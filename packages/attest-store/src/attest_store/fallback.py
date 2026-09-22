"""Explicit local fallback composition governed by BRD-F07."""

from __future__ import annotations

from attest_store._metadata import validate_bundle, validate_digest
from attest_store.errors import StoreError, store_error
from attest_store.filesystem import FilesystemStore
from attest_store.protocols import AttestationStore, StoreRef


def _configured_primary(value: object) -> AttestationStore:
    if not isinstance(value, AttestationStore):
        raise store_error("ERR-STORE-405")
    return value


def put_with_fallback(
    primary: AttestationStore,
    fallback: FilesystemStore,
    digest: str,
    bundle: bytes,
) -> StoreRef:
    """Preserve exact bytes locally after one coded primary failure (REQ-F07-080)."""
    validated_digest = validate_digest(digest)
    validated_bundle = validate_bundle(bundle)
    validated_primary = _configured_primary(primary)
    if not isinstance(fallback, FilesystemStore):
        raise store_error("ERR-STORE-405")
    try:
        return validated_primary.put(validated_digest, validated_bundle)
    except StoreError as primary_error:
        try:
            reference = fallback.put(validated_digest, validated_bundle)
        except StoreError:
            raise store_error("ERR-STORE-406") from primary_error
        raise store_error(primary_error.code, fallback_path=reference.location) from primary_error
