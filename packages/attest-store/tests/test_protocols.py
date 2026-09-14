"""Acceptance tests for the public F-07 storage contract."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from attest_store import (
    AttestationStore,
    FilesystemStore,
    StoreError,
    StoreRef,
    put_with_fallback,
)
from attest_store.errors import StoreErrorCode, store_error

_DIGEST = "a" * 64


@pytest.mark.ac("AC-F07-010")
def test_public_protocol_and_store_ref_are_exact_and_immutable(stored_at: datetime) -> None:
    """REQ-F07-010: callers receive one closed immutable locator model."""
    reference = StoreRef(
        backend="filesystem",
        digest=_DIGEST,
        bundle_digest="b" * 64,
        location="/store/a.sigstore.json",
        stored_at=stored_at,
    )

    assert set(inspect.signature(AttestationStore.put).parameters) == {"self", "digest", "bundle"}
    assert set(inspect.signature(AttestationStore.get).parameters) == {"self", "digest"}
    assert set(inspect.signature(AttestationStore.list).parameters) == {"self", "since"}
    assert reference.backend == "filesystem"
    with pytest.raises(FrozenInstanceError):
        reference.location = "changed"  # type: ignore[misc]


@pytest.mark.ac("AC-F07-080")
def test_primary_failure_preserves_exact_bytes_and_reports_fallback(
    tmp_path: Path, stored_at: datetime
) -> None:
    """REQ-F07-080: a coded primary failure retains a local exact-byte copy."""

    class FailingStore:
        def put(self, digest: str, bundle: bytes) -> StoreRef:
            raise store_error("ERR-STORE-402")

        def get(self, digest: str) -> list[bytes]:
            raise NotImplementedError

        def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
            raise NotImplementedError

    fallback = FilesystemStore(tmp_path, clock=lambda: stored_at)

    with pytest.raises(StoreError) as captured:
        put_with_fallback(cast(AttestationStore, FailingStore()), fallback, _DIGEST, b"exact")

    assert captured.value.code == "ERR-STORE-402"
    assert captured.value.fallback_path == str(tmp_path / f"{_DIGEST}.sigstore.json")
    assert fallback.get(_DIGEST) == [b"exact"]


@pytest.mark.ac("AC-F07-080")
def test_double_failure_has_a_distinct_error_and_retains_primary_as_cause(
    tmp_path: Path, stored_at: datetime
) -> None:
    """REQ-F07-080: two failures cannot be reported as durable fallback success."""

    class FailingStore:
        def __init__(self, code: StoreErrorCode) -> None:
            self._code = code

        def put(self, digest: str, bundle: bytes) -> StoreRef:
            raise store_error(self._code)

        def get(self, digest: str) -> list[bytes]:
            raise NotImplementedError

        def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
            raise NotImplementedError

    class FailingFallback(FilesystemStore):
        def put(self, digest: str, bundle: bytes) -> StoreRef:
            raise store_error("ERR-STORE-404")

    primary = cast(AttestationStore, FailingStore("ERR-STORE-402"))
    fallback = FailingFallback(tmp_path, clock=lambda: stored_at)

    with pytest.raises(StoreError) as captured:
        put_with_fallback(primary, fallback, _DIGEST, b"retained-by-caller")

    assert captured.value.code == "ERR-STORE-406"
    assert isinstance(captured.value.__cause__, StoreError)
    assert captured.value.__cause__.code == "ERR-STORE-402"
    assert captured.value.fallback_path is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend", "unknown"),
        ("digest", "A" * 64),
        ("bundle_digest", "short"),
        ("location", "https://user:secret@example.test/repo"),
        ("stored_at", datetime(2026, 9, 14, tzinfo=None)),  # noqa: DTZ001
    ],
)
def test_store_ref_rejects_invalid_or_credential_bearing_values(
    field: str, value: object, stored_at: datetime
) -> None:
    """REQ-F07-110: public locators fail closed before a backend operation."""
    values: dict[str, object] = {
        "backend": "filesystem",
        "digest": _DIGEST,
        "bundle_digest": "b" * 64,
        "location": "/safe/location",
        "stored_at": stored_at,
    }
    values[field] = value

    with pytest.raises(StoreError) as captured:
        StoreRef(**values)  # type: ignore[arg-type]
    assert captured.value.code == "ERR-STORE-405"


def test_filesystem_constructor_and_since_reject_invalid_inputs(tmp_path: Path) -> None:
    """REQ-F07-110: invalid paths, clocks, and time filters are rejected."""
    missing = tmp_path / "missing"
    with pytest.raises(StoreError) as captured:
        FilesystemStore(missing)
    assert captured.value.code == "ERR-STORE-405"

    store = FilesystemStore(tmp_path)
    with pytest.raises(StoreError) as captured:
        store.list(datetime(2026, 9, 14, tzinfo=None))  # noqa: DTZ001
    assert captured.value.code == "ERR-STORE-405"

    with pytest.raises(StoreError) as captured:
        FilesystemStore(tmp_path, clock=cast(object, "not-callable"))  # type: ignore[arg-type]
    assert captured.value.code == "ERR-STORE-405"

    future = datetime.now(tz=UTC) + timedelta(days=1)
    assert list(store.list(future)) == []
