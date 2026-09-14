"""FilesystemStore conformance and adversarial tests."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from attest_store import FilesystemStore, StoreError

_DIGEST = "1" * 64
_OTHER_DIGEST = "2" * 64


def _put_from_process(directory: str, digest: str, bundle: bytes) -> tuple[str, str]:
    script = """
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from attest_store import FilesystemStore

store = FilesystemStore(
    Path(sys.argv[1]),
    clock=lambda: datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC),
)
reference = store.put(sys.argv[2], bytes.fromhex(sys.argv[3]))
print(json.dumps([reference.location, reference.bundle_digest]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, directory, digest, bundle.hex()],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    location, digest_of_bundle = cast(list[str], json.loads(result.stdout))
    return location, digest_of_bundle


@pytest.mark.ac("AC-F07-010")
@pytest.mark.ac("AC-F07-020")
@pytest.mark.ac("AC-F07-060")
def test_filesystem_stores_multiple_exact_bundles_idempotently(
    tmp_path: Path, stored_at: datetime
) -> None:
    """REQ-F07-010/020/060: deterministic suffixes never overwrite exact bytes."""
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)

    first = store.put(_DIGEST, b"second-by-hash")
    duplicate = store.put(_DIGEST, b"second-by-hash")
    second = store.put(_DIGEST, b"first-by-hash")

    assert first == duplicate
    assert Path(first.location).name == f"{_DIGEST}.sigstore.json"
    assert Path(second.location).name == f"{_DIGEST}.1.sigstore.json"
    expected = sorted(
        [b"second-by-hash", b"first-by-hash"], key=lambda value: sha256(value).digest()
    )
    assert store.get(_DIGEST) == expected
    assert sorted(path.name for path in tmp_path.glob("*.sigstore.json")) == [
        f"{_DIGEST}.1.sigstore.json",
        f"{_DIGEST}.sigstore.json",
    ]
    assert not (tmp_path / f"{_DIGEST}.2.sigstore.json").exists()


@pytest.mark.ac("AC-F07-060")
def test_metadata_is_closed_canonical_and_hash_bound(tmp_path: Path, stored_at: datetime) -> None:
    """REQ-F07-060: the companion format is exact and independently auditable."""
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"bundle")
    metadata_path = Path(f"{reference.location}.store.json")
    metadata = metadata_path.read_bytes()

    assert metadata == (
        b'{"bundleDigest":"1e6ed65d77d6364eeaed5a745ba5c4985ae2b700dd85d7cf7f027bdf294a33fc",'
        b'"changeSetDigest":"1111111111111111111111111111111111111111111111111111111111111111",'
        b'"size":6,"storedAt":"2026-09-14T12:00:00Z","version":1}'
    )
    assert json.loads(metadata) == {
        "version": 1,
        "changeSetDigest": _DIGEST,
        "bundleDigest": reference.bundle_digest,
        "size": 6,
        "storedAt": "2026-09-14T12:00:00Z",
    }


@pytest.mark.ac("AC-F07-010")
def test_list_is_globally_deterministic_and_since_is_inclusive(
    tmp_path: Path, stored_at: datetime
) -> None:
    """REQ-F07-010: stored UTC metadata defines stable list and inclusive filtering."""
    moments = iter([stored_at + timedelta(seconds=2), stored_at, stored_at + timedelta(seconds=1)])
    store = FilesystemStore(tmp_path, clock=lambda: next(moments))
    late = store.put(_DIGEST, b"late")
    early = store.put(_OTHER_DIGEST, b"early")
    middle = store.put(_DIGEST, b"middle")

    assert list(store.list()) == [early, middle, late]
    assert list(store.list(stored_at + timedelta(seconds=1))) == [middle, late]
    assert list(store.list((stored_at + timedelta(seconds=1)).astimezone(tz=UTC))) == [
        middle,
        late,
    ]


@pytest.mark.ac("AC-F07-070")
@pytest.mark.parametrize("damage", ["bundle", "metadata", "size", "extra", "duplicate-key"])
def test_corruption_fails_closed_without_parsing_bundle_semantics(
    tmp_path: Path, stored_at: datetime, damage: str
) -> None:
    """REQ-F07-070: only storage integrity is enforced during retrieval."""
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"not-a-sigstore-bundle")
    bundle_path = Path(reference.location)
    metadata_path = Path(f"{reference.location}.store.json")

    if damage == "bundle":
        bundle_path.write_bytes(b"changed")
    elif damage == "metadata":
        metadata_path.write_bytes(b"not-json")
    else:
        metadata = json.loads(metadata_path.read_bytes())
        if damage == "size":
            metadata["size"] += 1
        elif damage == "extra":
            metadata["extra"] = True
        else:
            metadata_path.write_bytes(metadata_path.read_bytes()[:-1] + b',"version":1}')
            metadata = None
        if metadata is not None:
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(StoreError) as captured:
        store.get(_DIGEST)
    assert captured.value.code == "ERR-STORE-404"


@pytest.mark.ac("AC-F07-070")
def test_invalid_bundle_is_returned_but_missing_digest_is_coded(
    tmp_path: Path, stored_at: datetime
) -> None:
    """REQ-F07-010/070: absence and semantic invalidity stay distinct."""
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    store.put(_DIGEST, b"\x00invalid\xff")

    assert store.get(_DIGEST) == [b"\x00invalid\xff"]
    with pytest.raises(StoreError) as captured:
        store.get(_OTHER_DIGEST)
    assert captured.value.code == "ERR-STORE-403"


@pytest.mark.ac("AC-F07-100")
def test_process_concurrent_puts_are_complete_and_deduplicated(tmp_path: Path) -> None:
    """REQ-F07-100: cooperating processes expose no partial or duplicate entry."""
    bundles = [b"same"] * 5 + [f"distinct-{index}".encode() for index in range(5)]
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(
            executor.map(
                _put_from_process,
                [str(tmp_path)] * len(bundles),
                [_DIGEST] * len(bundles),
                bundles,
            )
        )

    store = FilesystemStore(tmp_path)
    expected = sorted(set(bundles), key=lambda value: sha256(value).digest())
    assert store.get(_DIGEST) == expected
    assert len(list(store.list())) == len(expected)
    same_results = {
        result for result, bundle in zip(results, bundles, strict=True) if bundle == b"same"
    }
    assert len(same_results) == 1
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.ac("AC-F07-110")
@pytest.mark.parametrize("target", ["bundle", "metadata"])
def test_symlink_entries_fail_closed_without_touching_target(
    tmp_path: Path, stored_at: datetime, target: str
) -> None:
    """REQ-F07-110: a symlink cannot redirect storage reads or writes."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-{target}"
    outside.write_bytes(b"outside")
    bundle_path = tmp_path / f"{_DIGEST}.sigstore.json"
    metadata_path = tmp_path / f"{_DIGEST}.sigstore.json.store.json"
    attacked = bundle_path if target == "bundle" else metadata_path
    attacked.symlink_to(outside)
    if target == "metadata":
        bundle_path.write_bytes(b"bundle")

    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    with pytest.raises(StoreError) as captured:
        store.put(_DIGEST, b"bundle")

    assert captured.value.code == "ERR-STORE-404"
    assert outside.read_bytes() == b"outside"
