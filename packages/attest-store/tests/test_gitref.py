"""GitRefStore conformance, push, and adversarial tests."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

import pytest

from attest_store import FilesystemStore, GitRefStore, StoreError
from attest_store import gitref as gitref_module

type GitBackend = Literal["pygit2", "subprocess"]

_DIGEST = "3" * 64
_OTHER_DIGEST = "4" * 64
_BACKENDS: tuple[GitBackend, ...] = ("pygit2", "subprocess")


def _run_git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        input=input_bytes,
        check=True,
        capture_output=True,
    ).stdout


def _initialize_repository(path: Path) -> None:
    _run_git(path.parent, "init", str(path))
    _run_git(path, "config", "user.name", "Test User")
    _run_git(path, "config", "user.email", "test@example.invalid")
    (path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _run_git(path, "add", "tracked.txt")
    _run_git(path, "commit", "-m", "initial")


def _git_snapshot(path: Path) -> dict[str, bytes]:
    return {
        "head": _run_git(path, "rev-parse", "HEAD"),
        "branches": _run_git(path, "for-each-ref", "refs/heads"),
        "tags": _run_git(path, "for-each-ref", "refs/tags"),
        "notes": _run_git(path, "for-each-ref", "refs/notes"),
        "status": _run_git(path, "status", "--porcelain=v1", "-z"),
        "index": (path / ".git" / "index").read_bytes(),
    }


def _bundle(log_index: int | str | None, *, marker: str) -> bytes:
    entry: dict[str, object] = {"logIndex": log_index} if log_index is not None else {}
    return json.dumps(
        {
            "marker": marker,
            "verificationMaterial": {"tlogEntries": [entry]},
        },
        separators=(",", ":"),
    ).encode()


def _put_git_from_process(
    repository: str, backend: GitBackend, digest: str, bundle: bytes
) -> tuple[str, str]:
    script = """
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from attest_store import GitRefStore

store = GitRefStore(
    Path(sys.argv[1]),
    backend=sys.argv[2],
    clock=lambda: datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC),
)
reference = store.put(sys.argv[3], bytes.fromhex(sys.argv[4]))
print(json.dumps([reference.location, reference.bundle_digest]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, repository, backend, digest, bundle.hex()],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    location, digest_of_bundle = cast(list[str], json.loads(result.stdout))
    return location, digest_of_bundle


@pytest.mark.ac("AC-F07-020")
@pytest.mark.ac("AC-F07-030")
@pytest.mark.ac("AC-F07-040")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_git_backends_create_exact_objects_refs_and_no_other_state(
    tmp_path: Path, stored_at: datetime, backend: GitBackend
) -> None:
    """REQ-F07-020/030/040: denied egress leaves only local objects and refs."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    _run_git(repository, "remote", "add", "denied", "http://127.0.0.1:1/blocked.git")
    before = _git_snapshot(repository)
    store = GitRefStore(repository, backend=backend, clock=lambda: stored_at)
    raw = _bundle(17, marker="first")

    first = store.put(_DIGEST, raw)
    duplicate = store.put(_DIGEST, raw)
    after = _git_snapshot(repository)

    assert first == duplicate
    assert first.location == f"refs/attestations/{_DIGEST}"
    assert before == after
    tag_oid = _run_git(repository, "rev-parse", first.location).decode().strip()
    assert _run_git(repository, "cat-file", "-t", tag_oid) == b"tag\n"
    tag = _run_git(repository, "cat-file", "-p", tag_oid)
    assert f"tag attestations/{_DIGEST}\n".encode() in tag
    assert b"tagger attest <attest@invalid> 1789387200 +0000\n" in tag
    blob_oid = next(
        line.removeprefix(b"object ").decode()
        for line in tag.splitlines()
        if line.startswith(b"object ")
    )
    assert _run_git(repository, "cat-file", "-t", blob_oid) == b"blob\n"
    assert _run_git(repository, "cat-file", "blob", blob_oid) == raw
    assert not _run_git(repository, "for-each-ref", "refs/tags")


@pytest.mark.ac("AC-F07-010")
@pytest.mark.ac("AC-F07-030")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_git_locator_collision_and_retrieval_are_deterministic(
    tmp_path: Path, stored_at: datetime, backend: GitBackend
) -> None:
    """REQ-F07-010/030: log-index collisions retain every exact Bundle once."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    store = GitRefStore(repository, backend=backend, clock=lambda: stored_at)
    base = _bundle(7, marker="base")
    indexed = _bundle("9", marker="indexed")
    collision = _bundle(9, marker="collision")
    unindexed = b"invalid but retrievable"

    references = [
        store.put(_DIGEST, base),
        store.put(_DIGEST, indexed),
        store.put(_DIGEST, collision),
        store.put(_DIGEST, unindexed),
    ]

    collision_digest = sha256(collision).hexdigest()
    unindexed_digest = sha256(unindexed).hexdigest()
    assert [item.location for item in references] == [
        f"refs/attestations/{_DIGEST}",
        f"refs/attestations/{_DIGEST}-9",
        f"refs/attestations/{_DIGEST}-9-{collision_digest}",
        f"refs/attestations/{_DIGEST}-sha256-{unindexed_digest}",
    ]
    assert store.get(_DIGEST) == sorted(
        [base, indexed, collision, unindexed], key=lambda value: sha256(value).digest()
    )
    assert list(store.list()) == sorted(
        references,
        key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
    )
    assert list(store.list(stored_at + timedelta(seconds=1))) == []


@pytest.mark.ac("AC-F07-070")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_git_corrupt_tag_fails_closed(
    tmp_path: Path, stored_at: datetime, backend: GitBackend
) -> None:
    """REQ-F07-070: malformed metadata objects never produce unbound bytes."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    store = GitRefStore(repository, backend=backend, clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"bundle")
    malformed_tag = (
        b"object "
        + _run_git(repository, "hash-object", "-w", "--stdin", input_bytes=b"bundle").strip()
        + b"\ntype blob\ntag wrong\ntagger attacker <attacker@example.invalid> 0 +0000\n\n{}\n"
    )
    malformed_oid = _run_git(repository, "mktag", input_bytes=malformed_tag).strip()
    _run_git(repository, "update-ref", reference.location, malformed_oid.decode())

    with pytest.raises(StoreError) as captured:
        store.get(_DIGEST)
    assert captured.value.code == "ERR-STORE-404"


@pytest.mark.ac("AC-F07-100")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_git_process_concurrency_is_create_only(tmp_path: Path, backend: GitBackend) -> None:
    """REQ-F07-100: parallel writers retain every distinct Bundle once."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    bundles = [_bundle(5, marker="same")] * 5 + [
        _bundle(5, marker=f"distinct-{index}") for index in range(5)
    ]

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(
            executor.map(
                _put_git_from_process,
                [str(repository)] * len(bundles),
                [backend] * len(bundles),
                [_DIGEST] * len(bundles),
                bundles,
            )
        )

    store = GitRefStore(repository, backend=backend)
    assert store.get(_DIGEST) == sorted(set(bundles), key=lambda value: sha256(value).digest())
    assert len(list(store.list())) == len(set(bundles))
    same_results = {
        result for result, bundle in zip(results, bundles, strict=True) if bundle == bundles[0]
    }
    assert len(same_results) == 1


@pytest.mark.ac("AC-F07-050")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_explicit_push_updates_only_same_remote_ref(
    tmp_path: Path, stored_at: datetime, backend: GitBackend
) -> None:
    """REQ-F07-040/050: successful egress is explicit, exact, and non-force."""
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    remote.mkdir()
    _initialize_repository(repository)
    _run_git(remote, "init", "--bare")
    _run_git(repository, "remote", "add", "storage", str(remote))
    store = GitRefStore(repository, backend=backend, clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"bundle")
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    fallback = FilesystemStore(fallback_dir, clock=lambda: stored_at)

    assert store.push(reference, "storage", fallback) == reference
    local_oid = _run_git(repository, "rev-parse", reference.location)
    remote_oid = _run_git(remote, "rev-parse", reference.location)
    assert local_oid == remote_oid
    assert list(fallback.list()) == []


@pytest.mark.ac("AC-F07-050")
@pytest.mark.parametrize(
    ("remote_kind", "expected_code"),
    [("rejected", "ERR-STORE-401"), ("unreachable", "ERR-STORE-402")],
)
def test_push_failure_is_classified_sanitized_and_preserved(
    tmp_path: Path,
    stored_at: datetime,
    remote_kind: str,
    expected_code: str,
) -> None:
    """REQ-F07-050/080: push errors expose codes and an exact local recovery path."""
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    _initialize_repository(repository)
    if remote_kind == "rejected":
        remote.mkdir()
        _run_git(remote, "init", "--bare")
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\necho secret-upstream-diagnostic >&2\nexit 1\n", encoding="utf-8"
        )
        hook.chmod(0o700)
    _run_git(repository, "remote", "add", "storage", str(remote))
    store = GitRefStore(repository, backend="subprocess", clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"preserve-me")
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    fallback = FilesystemStore(fallback_dir, clock=lambda: stored_at)

    with pytest.raises(StoreError) as captured:
        store.push(reference, "storage", fallback)

    assert captured.value.code == expected_code
    if expected_code == "ERR-STORE-401":
        assert "contents: write" in captured.value.remediation
        assert "refs/attestations/*" in captured.value.remediation
    assert captured.value.fallback_path == str(fallback_dir / f"{_DIGEST}.sigstore.json")
    assert "secret-upstream-diagnostic" not in str(captured.value)
    assert fallback.get(_DIGEST) == [b"preserve-me"]
    assert _run_git(repository, "rev-parse", reference.location)


@pytest.mark.ac("AC-F07-050")
def test_push_deadline_is_unreachable_and_preserved_locally(
    tmp_path: Path, stored_at: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-F07-050/080: an expired push is coded and retains exact fallback bytes."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    store = GitRefStore(repository, backend="subprocess", clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"deadline-bundle")
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    fallback = FilesystemStore(fallback_dir, clock=lambda: stored_at)
    expired = subprocess.TimeoutExpired("git push", 1)

    def expire_push(
        self: gitref_module._SubprocessObjects, remote: str, location: str
    ) -> subprocess.CompletedProcess[bytes]:
        raise expired

    monkeypatch.setattr(gitref_module._SubprocessObjects, "push", expire_push)
    with pytest.raises(StoreError) as captured:
        store.push(reference, "origin", fallback)

    assert captured.value.code == "ERR-STORE-402"
    assert captured.value.fallback_path == str(fallback_dir / f"{_DIGEST}.sigstore.json")
    assert fallback.get(_DIGEST) == [b"deadline-bundle"]


@pytest.mark.ac("AC-F07-110")
def test_git_subprocess_environment_and_deadline_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-F07-110: Git execution has no shell, inherited Git controls, or missing timeout."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_repository(repository)
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", "/outside")
    calls: list[dict[str, object]] = []
    original_run = subprocess.run

    def observed_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(dict(kwargs))
        return cast(
            subprocess.CompletedProcess[bytes],
            original_run(*args, **kwargs),  # type: ignore[call-overload]
        )

    monkeypatch.setattr(subprocess, "run", observed_run)
    store = GitRefStore(repository, backend="subprocess", subprocess_timeout=timedelta(seconds=3))
    store.put(_OTHER_DIGEST, b"bundle")

    assert calls
    assert all(call.get("timeout") == 3.0 for call in calls)
    assert all(call.get("shell") is None for call in calls)
    assert all("GIT_OBJECT_DIRECTORY" not in call["env"] for call in calls)  # type: ignore[operator]


@pytest.mark.ac("AC-F07-110")
@pytest.mark.parametrize("backend", _BACKENDS)
def test_git_repository_replacement_fails_before_any_write(
    tmp_path: Path, stored_at: datetime, backend: GitBackend
) -> None:
    """REQ-F07-110: replacing the configured repository cannot redirect object writes."""
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    _initialize_repository(repository)
    _initialize_repository(outside)
    store = GitRefStore(repository, backend=backend, clock=lambda: stored_at)
    outside_before = _git_snapshot(outside)
    repository.rename(tmp_path / "moved-repository")
    repository.symlink_to(outside, target_is_directory=True)

    with pytest.raises(StoreError) as captured:
        store.put(_DIGEST, b"must-not-escape")

    assert captured.value.code == "ERR-STORE-404"
    assert _git_snapshot(outside) == outside_before
    assert not _run_git(outside, "for-each-ref", "refs/attestations/")
