"""Closed sidecar protocol tests for F-03."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from attest_collect import CollectContext, SidecarCollector

CLAIM_ID = "01890f5e-7b8a-7cc3-98c4-dc0c0c07398f"


@pytest.fixture(autouse=True)
def _isolate_shared_repository(single_add_repo: Any) -> Iterator[None]:
    marker = single_add_repo.path / ".attest"
    if marker.exists():
        shutil.rmtree(marker)
    yield
    if marker.exists():
        shutil.rmtree(marker)


def _context(case: Any) -> CollectContext:
    return CollectContext(case.path, case.base, case.head)


def _directory(repository: Path) -> Path:
    value = repository / ".attest" / "claims.d"
    value.mkdir(parents=True, exist_ok=True)
    return value


def _payload(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "0.1.0",
        "claimId": CLAIM_ID,
        "agent": {"name": "codex-cli", "version": "1.2.3"},
        "model": {"provider": "openai", "name": "gpt-5"},
        "sessionId": "session-1",
        "promptDigest": "b" * 64,
        "scope": {"paths": ["src/a.py"]},
        "claimedAt": "2099-01-01T00:00:00Z",
    }
    value.update(changes)
    return value


def _write(repository: Path, payload: object, *, filename: str | None = None) -> Path:
    path = _directory(repository) / (filename or f"{CLAIM_ID}.json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.ac("AC-F03-020")
def test_complete_sidecar_maps_to_closed_claim(single_add_repo: Any) -> None:
    path = _write(single_add_repo.path, _payload())

    result = SidecarCollector().collect(_context(single_add_repo))

    assert result.warnings == ()
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.model_dump() == {
        "claimId": CLAIM_ID,
        "agent": {"name": "codex-cli", "version": "1.2.3"},
        "model": {"provider": "openai", "name": "gpt-5"},
        "sessionId": "session-1",
        "promptDigest": "b" * 64,
        "scope": {"paths": ["src/a.py"]},
        "source": {
            "kind": "sidecar",
            "reference": f".attest/claims.d/{CLAIM_ID}.json",
            "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "claimedAt": "2099-01-01T00:00:00Z",
    }


@pytest.mark.parametrize(
    ("payload", "filename"),
    [
        (_payload(schemaVersion="0.2.0"), None),
        (_payload(unknown=True), None),
        (_payload(source={"kind": "manual"}), None),
        (_payload(claimId="not-an-id"), None),
        (_payload(scope={"paths": ["café.py"]}), None),
        (_payload(), "01890f5e-7b8a-7cc3-a8c4-dc0c0c07398f.json"),
        ([], None),
    ],
)
def test_invalid_sidecar_shapes_are_isolated_warnings(
    single_add_repo: Any, payload: object, filename: str | None
) -> None:
    _write(single_add_repo.path, payload, filename=filename)

    result = SidecarCollector().collect(_context(single_add_repo))

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-111"]


@pytest.mark.parametrize("raw", [b"\xef\xbb\xbf{}", b"\xff", b"{} trailing"])
def test_bom_non_utf8_and_trailing_json_are_malformed(single_add_repo: Any, raw: bytes) -> None:
    path = _directory(single_add_repo.path) / f"{CLAIM_ID}.json"
    path.write_bytes(raw)

    result = SidecarCollector().collect(_context(single_add_repo))

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == ["ERR-COLLECT-111"]


def test_symlink_and_non_regular_entries_are_not_followed(single_add_repo: Any) -> None:
    directory = _directory(single_add_repo.path)
    target = single_add_repo.path / "outside.json"
    target.write_text(json.dumps(_payload()), encoding="utf-8")
    symlink = directory / f"{CLAIM_ID}.json"
    symlink.symlink_to(target)
    fifo = directory / "01890f5e-7b8a-7cc3-a8c4-dc0c0c07398f.json"
    os.mkfifo(fifo)

    result = SidecarCollector().collect(_context(single_add_repo))

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == [
        "ERR-COLLECT-111",
        "ERR-COLLECT-111",
    ]


def test_missing_directory_is_silent_and_non_directory_warns(single_add_repo: Any) -> None:
    missing = SidecarCollector().collect(_context(single_add_repo))
    assert missing == type(missing)(claims=(), warnings=())

    marker = single_add_repo.path / ".attest"
    marker.mkdir()
    (marker / "claims.d").write_text("not a directory", encoding="utf-8")
    malformed = SidecarCollector().collect(_context(single_add_repo))
    assert [warning.code for warning in malformed.warnings] == ["ERR-COLLECT-112"]


def test_prompt_warning_survives_other_sidecar_validation_failure(single_add_repo: Any) -> None:
    _write(single_add_repo.path, _payload(prompt="never expose", unknown=True))

    result = SidecarCollector().collect(_context(single_add_repo))

    assert result.claims == ()
    assert [warning.code for warning in result.warnings] == [
        "ERR-COLLECT-111",
        "WARN-COLLECT-003",
    ]
    assert all("never expose" not in warning.message for warning in result.warnings)
