"""Defensive boundary tests for F-07 adapters and worker internals."""

from __future__ import annotations

import json
import multiprocessing
import os
import pickle
import subprocess
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from attest_store import FilesystemStore, GitRefStore, OciStore, OciSubject, StoreError, StoreRef
from attest_store import gitref as gitref_module
from attest_store import oci as oci_module
from attest_store._metadata import (
    StoreMetadata,
    metadata_bytes,
    parse_metadata,
    validate_bundle,
    validate_digest,
    validate_location,
    validate_stored_time,
)
from attest_store.errors import store_error
from attest_store.fallback import put_with_fallback

_DIGEST = "7" * 64
_SUBJECT = OciSubject(
    media_type="application/vnd.oci.image.manifest.v1+json",
    digest=f"sha256:{'b' * 64}",
    size=12,
)


def _initialize_bare(path: Path) -> None:
    subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True)


@pytest.mark.parametrize("value", [None, b"a" * 64, "A" * 64, "a" * 63, "g" * 64])
def test_digest_and_bundle_input_boundaries(value: object) -> None:
    with pytest.raises(StoreError) as captured:
        validate_digest(value)
    assert captured.value.code == "ERR-STORE-405"

    if not isinstance(value, bytes):
        with pytest.raises(StoreError) as captured:
            validate_bundle(value)
        assert captured.value.code == "ERR-STORE-405"


@pytest.mark.parametrize(
    "location",
    ["", "line\nbreak", "https://user:password@example.test/repo", "https://[invalid"],
)
def test_public_location_rejects_controls_credentials_and_invalid_urls(location: str) -> None:
    with pytest.raises(StoreError) as captured:
        validate_location(location)
    assert captured.value.code == "ERR-STORE-405"


def test_metadata_time_canonicality_and_error_pickling(stored_at: datetime) -> None:
    with pytest.raises(StoreError):
        validate_stored_time(stored_at.replace(microsecond=1))
    metadata = StoreMetadata(
        digest=_DIGEST,
        bundle_digest="8" * 64,
        size=1,
        stored_at=stored_at,
    )
    raw = metadata_bytes(metadata)
    assert parse_metadata(raw) == metadata
    for malformed in [
        b"[]",
        b'{"version":1,"version":1}',
        b"{" + b" " * 4097 + b"}",
        raw.replace(b'"size":1', b'"size":true'),
        raw.replace(b'"version":1', b'"version":2'),
        raw.replace(b"2026-09-14T12:00:00Z", b"2026-09-14 12:00:00Z"),
    ]:
        with pytest.raises(StoreError) as captured:
            parse_metadata(malformed)
        assert captured.value.code == "ERR-STORE-404"

    error = store_error("ERR-STORE-402", fallback_path="/safe/fallback")
    restored = pickle.loads(pickle.dumps(error))
    assert restored.code == error.code
    assert restored.fallback_path == error.fallback_path
    assert str(restored) == str(error)


def test_filesystem_orphans_lock_and_replacement_fail_closed(
    tmp_path: Path, stored_at: datetime
) -> None:
    orphan = tmp_path / f"{_DIGEST}.sigstore.json"
    orphan.write_bytes(b"orphan")
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    with pytest.raises(StoreError) as captured:
        store.list()
    assert captured.value.code == "ERR-STORE-404"
    orphan.unlink()
    (tmp_path / ".attest-store.lock").unlink()

    outside = tmp_path.parent / f"{tmp_path.name}-lock-target"
    outside.write_bytes(b"unchanged")
    (tmp_path / ".attest-store.lock").symlink_to(outside)
    with pytest.raises(StoreError) as captured:
        store.put(_DIGEST, b"bundle")
    assert captured.value.code == "ERR-STORE-404"
    assert outside.read_bytes() == b"unchanged"


def test_filesystem_detects_configured_directory_replacement(tmp_path: Path) -> None:
    configured = tmp_path / "store"
    configured.mkdir()
    store = FilesystemStore(configured)
    moved = tmp_path / "moved"
    configured.rename(moved)
    configured.mkdir()

    with pytest.raises(StoreError) as captured:
        store.list()
    assert captured.value.code == "ERR-STORE-404"


def test_filesystem_and_fallback_reject_wrong_public_values(tmp_path: Path) -> None:
    with pytest.raises(StoreError):
        FilesystemStore(cast(object, 12))  # type: ignore[arg-type]
    with pytest.raises(StoreError):
        FilesystemStore("relative")
    controlled = tmp_path / "line\nbreak"
    controlled.mkdir()
    with pytest.raises(StoreError):
        FilesystemStore(controlled)
    store = FilesystemStore(tmp_path)
    with pytest.raises(StoreError):
        store.put(_DIGEST, cast(bytes, bytearray(b"mutable")))
    with pytest.raises(StoreError):
        put_with_fallback(store, cast(FilesystemStore, object()), _DIGEST, b"bundle")
    with pytest.raises(StoreError):
        put_with_fallback(object(), store, _DIGEST, b"bundle")  # type: ignore[arg-type]


def test_filesystem_publication_failures_leave_no_partial_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored_at: datetime
) -> None:
    store = FilesystemStore(tmp_path, clock=lambda: stored_at)
    name = f"{_DIGEST}.sigstore.json"
    metadata = metadata_bytes(
        StoreMetadata(
            digest=_DIGEST,
            bundle_digest=sha256(b"bundle").hexdigest(),
            size=6,
            stored_at=stored_at,
        )
    )
    original_fsync = os.fsync

    with store._locked(exclusive=True) as directory_fd:

        def fail_directory_sync(descriptor: int) -> None:
            if descriptor == directory_fd:
                raise OSError
            original_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", fail_directory_sync)
        with pytest.raises(StoreError) as captured:
            store._publish_pair(directory_fd, name, b"bundle", metadata)

    assert captured.value.code == "ERR-STORE-404"
    assert not (tmp_path / name).exists()
    assert not (tmp_path / f"{name}.store.json").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_filesystem_temporary_write_and_non_file_entry_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemStore(tmp_path)
    with store._locked(exclusive=True) as directory_fd:
        monkeypatch.setattr(os, "write", lambda descriptor, content: 0)
        with pytest.raises(StoreError) as captured:
            store._write_temporary(directory_fd, "entry", b"content")
    assert captured.value.code == "ERR-STORE-404"
    assert not list(tmp_path.glob(".*.tmp"))

    entry = tmp_path / f"{_DIGEST}.sigstore.json"
    entry.mkdir()
    with pytest.raises(StoreError) as captured:
        store.list()
    assert captured.value.code == "ERR-STORE-404"


def test_filesystem_clock_failures_are_configuration_errors(tmp_path: Path) -> None:
    def fail_clock() -> datetime:
        raise RuntimeError

    assert FilesystemStore(tmp_path).directory == tmp_path
    with pytest.raises(StoreError) as captured:
        FilesystemStore(tmp_path, clock=fail_clock).put(_DIGEST, b"bundle")
    assert captured.value.code == "ERR-STORE-405"


@pytest.mark.parametrize(
    ("bundle", "expected"),
    [
        (b"invalid", None),
        (b"[1]", None),
        (b'{"verificationMaterial":{}}', None),
        (b'{"verificationMaterial":{"tlogEntries":{}}}', None),
        (b'{"verificationMaterial":{"tlogEntries":[{"logIndex":true}]}}', None),
        (b'{"verificationMaterial":{"tlogEntries":[{"logIndex":-1}]}}', None),
        (rb'{"verificationMaterial":{"tlogEntries":[{"logIndex":"\u0661"}]}}', None),
        (
            b'{"verificationMaterial":{"tlogEntries":[{"logIndex":1},{"logIndex":2}]}}',
            None,
        ),
        (
            b'{"verificationMaterial":{"tlogEntries":[{"logIndex":3},{"logIndex":"3"}]}}',
            3,
        ),
    ],
)
def test_log_index_locator_extraction_is_bounded_and_unambiguous(
    bundle: bytes, expected: int | None
) -> None:
    assert gitref_module._extract_log_index(bundle) == expected
    assert gitref_module._extract_log_index(b" " * (1024 * 1024 + 1)) is None


def test_git_constructor_not_found_and_auto_fallback_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository.git"
    _initialize_bare(repository)
    with pytest.raises(StoreError):
        GitRefStore(repository, backend=cast(object, "invalid"))  # type: ignore[arg-type]
    with pytest.raises(StoreError):
        GitRefStore(repository, subprocess_timeout=timedelta(0))
    with pytest.raises(StoreError):
        GitRefStore(repository, clock=cast(object, "invalid"))  # type: ignore[arg-type]
    with pytest.raises(StoreError):
        GitRefStore(tmp_path / "missing")

    monkeypatch.setattr(
        gitref_module._Pygit2Objects, "is_available", classmethod(lambda cls: False)
    )
    store = GitRefStore(repository, backend="auto")
    assert store.backend == "subprocess"
    with pytest.raises(StoreError) as captured:
        store.get(_DIGEST)
    assert captured.value.code == "ERR-STORE-403"


def test_git_rejects_malformed_namespace_and_push_inputs(
    tmp_path: Path, stored_at: datetime
) -> None:
    repository = tmp_path / "repository.git"
    _initialize_bare(repository)
    store = GitRefStore(repository, backend="subprocess", clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"bundle")
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    fallback = FilesystemStore(fallback_dir, clock=lambda: stored_at)

    for remote in ["", "-option", "https://user:secret@example.test/repo"]:
        with pytest.raises(StoreError) as captured:
            store.push(reference, remote, fallback)
        assert captured.value.code == "ERR-STORE-405"
    wrong = StoreRef(
        backend="filesystem",
        digest=_DIGEST,
        bundle_digest=reference.bundle_digest,
        location="/safe",
        stored_at=stored_at,
    )
    with pytest.raises(StoreError):
        store.push(wrong, "origin", fallback)

    blob = subprocess.run(
        ["git", f"--git-dir={repository}", "hash-object", "-w", "--stdin"],
        input=b"bad",
        check=True,
        capture_output=True,
    ).stdout.strip()
    subprocess.run(
        ["git", f"--git-dir={repository}", "update-ref", f"refs/attestations/{'9' * 64}/bad", blob],
        check=True,
    )
    with pytest.raises(StoreError) as captured:
        store.list()
    assert captured.value.code == "ERR-STORE-404"


def _completed(
    returncode: int, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_git_subprocess_adapter_translates_malformed_and_failed_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository.git"
    _initialize_bare(repository)
    objects = gitref_module._SubprocessObjects(repository, timedelta(seconds=1))

    monkeypatch.setattr(
        objects,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("git", 1)),
    )
    with pytest.raises(StoreError):
        objects._local_run("status")

    for result in [_completed(1), _completed(0, b"malformed\n")]:
        monkeypatch.setattr(objects, "_run", lambda *args, result=result, **kwargs: result)
        with pytest.raises(StoreError):
            objects.list_refs("refs/attestations/")

    with pytest.raises(StoreError):
        objects.read_object("invalid", "blob")
    monkeypatch.setattr(objects, "_run", lambda *args, **kwargs: _completed(0, b"tag\n"))
    with pytest.raises(StoreError):
        objects.read_object("a" * 40, "blob")
    reads = iter([_completed(0, b"blob\n"), _completed(1)])
    monkeypatch.setattr(objects, "_run", lambda *args, **kwargs: next(reads))
    with pytest.raises(StoreError):
        objects.read_object("a" * 40, "blob")

    for result in [_completed(0, b"\xff"), _completed(0, b"not-an-object-id\n")]:
        monkeypatch.setattr(objects, "_run", lambda *args, result=result, **kwargs: result)
        with pytest.raises(StoreError):
            objects.write_object("tag", b"content")

    updates = iter([_completed(1), _completed(0)])
    monkeypatch.setattr(objects, "_run", lambda *args, **kwargs: next(updates))
    with pytest.raises(StoreError):
        objects.create_ref(f"refs/attestations/{_DIGEST}", "a" * 40)


def test_git_push_double_failure_reports_recovery_failure(
    tmp_path: Path, stored_at: datetime
) -> None:
    repository = tmp_path / "repository.git"
    _initialize_bare(repository)
    store = GitRefStore(repository, backend="subprocess", clock=lambda: stored_at)
    reference = store.put(_DIGEST, b"bundle")
    fallback_directory = tmp_path / "fallback"
    fallback_directory.mkdir()
    fallback = FilesystemStore(fallback_directory, clock=lambda: stored_at)
    fallback_directory.rename(tmp_path / "moved-fallback")

    with pytest.raises(StoreError) as captured:
        store.push(reference, str(tmp_path / "missing-remote.git"), fallback)
    assert captured.value.code == "ERR-STORE-406"
    assert captured.value.fallback_path is None


@dataclass
class _FakeResponse:
    status_code: int
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


class _SequenceClient:
    def __init__(self, responses: list[_FakeResponse], *, fail: bool = False) -> None:
        self._responses = iter(responses)
        self._fail = fail

    def do_request(self, *args: object, **kwargs: object) -> _FakeResponse:
        if self._fail:
            raise OSError
        return next(self._responses)


def _index(manifests: object = None) -> bytes:
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [] if manifests is None else manifests,
        },
        separators=(",", ":"),
    ).encode()


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (_FakeResponse(500), "ERR-STORE-402"),
        (_FakeResponse(200, b"[]"), "ERR-STORE-404"),
        (_FakeResponse(200, _index([1])), "ERR-STORE-404"),
        (_FakeResponse(200, _index(), {"Link": "malformed"}), "ERR-STORE-404"),
        (
            _FakeResponse(
                200,
                _index(),
                {"Link": '<https://evil.test/v2/attest/referrers/x>; rel="next"'},
            ),
            "ERR-STORE-404",
        ),
        (
            _FakeResponse(200, _index(), {"Link": '</v2/other/referrers/x>; rel="next"'}),
            "ERR-STORE-404",
        ),
    ],
)
def test_referrers_responses_fail_closed(response: _FakeResponse, code: str) -> None:
    client = cast(oci_module._Client, _SequenceClient([response]))
    with pytest.raises(StoreError) as captured:
        oci_module._referrer_descriptors(client, "https://registry.test/v2/attest", _SUBJECT)
    assert captured.value.code == code


def test_oci_json_descriptor_and_request_boundaries() -> None:
    for raw in [b"[]", b'{"a":1,"a":2}', b"{" + b" " * (4 * 1024 * 1024 + 1)]:
        with pytest.raises(StoreError):
            oci_module._json_object(raw)
    for descriptor_value in [None, "sha512:" + "a" * 64, "sha256:" + "A" * 64]:
        with pytest.raises(StoreError):
            oci_module._descriptor_digest(descriptor_value)
    for size_value in [True, -1, "1"]:
        with pytest.raises(StoreError):
            oci_module._descriptor_size(size_value)
    for annotation_value in [None, {1: "value"}, {"key": 1}]:
        with pytest.raises(StoreError):
            oci_module._annotations(annotation_value)
    with pytest.raises(StoreError) as captured:
        oci_module._request(
            cast(oci_module._Client, _SequenceClient([], fail=True)),
            "https://registry.test",
            headers={},
        )
    assert captured.value.code == "ERR-STORE-402"


def test_oci_descriptor_filter_is_closed(stored_at: datetime) -> None:
    valid: dict[str, object] = {
        "artifactType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "annotations": {
            "io.github.parth2412.attest.changeset-digest": _DIGEST,
            "io.github.parth2412.attest.bundle-digest": "8" * 64,
            "org.opencontainers.image.created": "2026-09-14T12:00:00Z",
        },
    }
    assert oci_module._matching_descriptor({}) is False
    assert oci_module._matching_descriptor({"artifactType": valid["artifactType"]}) is False
    assert (
        oci_module._matching_descriptor(
            {"artifactType": valid["artifactType"], "annotations": {"unrelated": "value"}}
        )
        is False
    )
    for stored_annotations in [
        {"io.github.parth2412.attest.changeset-digest": _DIGEST},
        cast(
            dict[str, str],
            {
                **cast(dict[str, str], valid["annotations"]),
                "io.github.parth2412.attest.bundle-digest": "invalid",
            },
        ),
    ]:
        with pytest.raises(StoreError):
            oci_module._matching_descriptor(
                {"artifactType": valid["artifactType"], "annotations": stored_annotations}
            )
    assert oci_module._matching_descriptor(valid)
    assert stored_at.tzinfo is UTC


def _valid_manifest(stored_at: datetime) -> tuple[dict[str, object], dict[str, object], bytes]:
    bundle_digest = "8" * 64
    annotations = {
        "io.github.parth2412.attest.changeset-digest": _DIGEST,
        "io.github.parth2412.attest.bundle-digest": bundle_digest,
        "org.opencontainers.image.created": stored_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
    }
    manifest: dict[str, object] = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "artifactType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "config": {
            "mediaType": "application/vnd.oci.empty.v1+json",
            "digest": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            "size": 2,
        },
        "layers": [
            {
                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "digest": f"sha256:{bundle_digest}",
                "size": 6,
            }
        ],
        "subject": {
            "mediaType": _SUBJECT.media_type,
            "digest": _SUBJECT.digest,
            "size": _SUBJECT.size,
        },
        "annotations": annotations,
    }
    raw = json.dumps(manifest, separators=(",", ":")).encode()
    descriptor: dict[str, object] = {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "digest": f"sha256:{sha256(raw).hexdigest()}",
        "size": len(raw),
        "artifactType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "annotations": annotations,
    }
    return manifest, descriptor, raw


def test_oci_manifest_integrity_and_schema_fail_closed(stored_at: datetime) -> None:
    manifest, descriptor, raw = _valid_manifest(stored_at)
    reference, layer_digest, layer_size = oci_module._validate_manifest(raw, descriptor, _SUBJECT)
    assert reference.digest == _DIGEST
    assert layer_digest == f"sha256:{'8' * 64}"
    assert layer_size == 6

    broken_descriptor = dict(descriptor)
    broken_descriptor["size"] = len(raw) + 1
    with pytest.raises(StoreError):
        oci_module._validate_manifest(raw, broken_descriptor, _SUBJECT)

    mutations: list[dict[str, object]] = []
    for key, value in [
        ("schemaVersion", 1),
        ("config", {}),
        ("layers", []),
    ]:
        mutated = deepcopy(manifest)
        mutated[key] = value
        mutations.append(mutated)

    mutated = deepcopy(manifest)
    cast(dict[str, object], cast(list[object], mutated["layers"])[0])["mediaType"] = "invalid"
    mutations.append(mutated)
    mutated = deepcopy(manifest)
    cast(dict[str, str], mutated["annotations"])["org.opencontainers.image.created"] = (
        "2026-09-14T12:00:01Z"
    )
    mutations.append(mutated)
    mutated = deepcopy(manifest)
    cast(dict[str, object], cast(list[object], mutated["layers"])[0])["digest"] = (
        f"sha256:{'9' * 64}"
    )
    mutations.append(mutated)

    for mutated in mutations:
        mutated_raw = json.dumps(mutated, separators=(",", ":")).encode()
        mutated_descriptor = dict(descriptor)
        mutated_descriptor["digest"] = f"sha256:{sha256(mutated_raw).hexdigest()}"
        mutated_descriptor["size"] = len(mutated_raw)
        with pytest.raises(StoreError) as captured:
            oci_module._validate_manifest(mutated_raw, mutated_descriptor, _SUBJECT)
        assert captured.value.code == "ERR-STORE-404"


def test_oci_constructor_and_public_result_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    invalid_parameters: list[dict[str, object]] = [
        {"subject": cast(OciSubject, object())},
        {"insecure": cast(bool, "yes")},
        {"client_factory": cast(oci_module.OciClientFactory, object())},
        {"clock": cast(object, "bad")},
        {"tls_verify": tmp_path / "missing-ca.pem"},
        {"auth_config": tmp_path / "missing-auth.json"},
        {"auth_config": cast(Path, object())},
    ]
    for kwargs in invalid_parameters:
        parameters: dict[str, object] = {"subject": _SUBJECT, **kwargs}
        with pytest.raises(StoreError):
            OciStore(
                "registry.test/attest",
                staging_directory=staging,
                **parameters,  # type: ignore[arg-type]
            )

    with pytest.raises(StoreError):
        OciStore(
            "registry.test/attest",
            subject=_SUBJECT,
            staging_directory=cast(Path, object()),
        )

    store = OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
    )
    assert store.subject == _SUBJECT
    monkeypatch.setattr(oci_module, "_execute_operation", lambda *args, **kwargs: ["wrong"])
    with pytest.raises(StoreError):
        store.get(_DIGEST)
    with pytest.raises(StoreError):
        store.list()
    monkeypatch.setattr(oci_module, "_execute_operation", lambda *args, **kwargs: [])
    with pytest.raises(StoreError):
        store.put(_DIGEST, b"bundle")

    for repository in ["registry.test/attest\n", "registry.test:70000/attest"]:
        with pytest.raises(StoreError):
            OciStore(repository, subject=_SUBJECT, staging_directory=staging)

    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("test CA", encoding="utf-8")
    assert OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
        tls_verify=ca_file,
    )._config.tls_verify == str(ca_file)


def test_oci_staging_identity_and_clock_fail_closed(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    store = OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
        clock=lambda: (_ for _ in ()).throw(RuntimeError()),
    )
    with pytest.raises(StoreError) as captured:
        store.put(_DIGEST, b"bundle")
    assert captured.value.code == "ERR-STORE-405"

    staging.rename(tmp_path / "moved")
    with pytest.raises(StoreError) as captured:
        oci_module._operate(store._config, "list", None, None, None, None)
    assert captured.value.code == "ERR-STORE-404"

    staging.mkdir()
    with pytest.raises(StoreError) as captured:
        oci_module._operate(store._config, "list", None, None, None, None)
    assert captured.value.code == "ERR-STORE-404"

    failing_store = OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
        client_factory=lambda *args: (_ for _ in ()).throw(RuntimeError()),
    )
    with pytest.raises(StoreError) as captured:
        oci_module._new_client(failing_store._config, "registry.test/attest:tag")
    assert captured.value.code == "ERR-STORE-402"


def test_oci_temporary_failure_and_auth_replacement_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(os, "write", lambda descriptor, content: 0)
    with pytest.raises(StoreError) as captured:
        oci_module._temporary_file(staging, "bundle", b"content")
    assert captured.value.code == "ERR-STORE-404"
    assert not list(staging.iterdir())
    monkeypatch.undo()

    auth = tmp_path / "auth.json"
    auth.write_text('{"auths":{}}', encoding="utf-8")
    store = OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
        auth_config=auth,
    )
    original = tmp_path / "original-auth.json"
    auth.rename(original)
    auth.symlink_to(original)
    with pytest.raises(StoreError) as captured:
        oci_module._new_client(store._config, "registry.test/attest:tag")
    assert captured.value.code == "ERR-STORE-404"

    controlled = tmp_path / "line\nbreak"
    controlled.mkdir()
    with pytest.raises(StoreError):
        OciStore(
            "registry.test/attest",
            subject=_SUBJECT,
            staging_directory=controlled,
        )


class _FakeConnection:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.closed = False

    def send(self, value: object) -> None:
        self.messages.append(value)

    def close(self) -> None:
        self.closed = True


class _FailingSendConnection(_FakeConnection):
    def send(self, value: object) -> None:
        raise BrokenPipeError


class _ReceiveConnection:
    def __init__(self, message: object | None, *, receive_error: bool = False) -> None:
        self.message = message
        self.receive_error = receive_error
        self.closed = False

    def poll(self, timeout: float = 0.0) -> bool:
        return self.message is not None or self.receive_error

    def recv(self) -> object:
        if self.receive_error:
            raise EOFError
        return self.message

    def close(self) -> None:
        self.closed = True


class _Process:
    def __init__(self, *, start_error: bool = False, stubborn: bool = False) -> None:
        self.start_error = start_error
        self.stubborn = stubborn
        self.alive = False
        self.terminated = False
        self.killed = False
        self.closed = False

    def start(self) -> None:
        if self.start_error:
            raise RuntimeError

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        if not self.stubborn:
            self.alive = False

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def join(self, timeout: float | None = None) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _ProcessContext:
    def __init__(
        self,
        process: _Process,
        receive: _ReceiveConnection,
        send: _FakeConnection,
    ) -> None:
        self.process = process
        self.receive = receive
        self.send = send

    def Pipe(  # noqa: N802
        self, *, duplex: bool
    ) -> tuple[_ReceiveConnection, _FakeConnection]:
        assert duplex is False
        return self.receive, self.send

    def Process(self, **kwargs: object) -> _Process:  # noqa: N802
        assert kwargs["target"] is oci_module._oci_worker
        return self.process


def test_oci_worker_translates_known_and_unknown_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    store = OciStore(
        "registry.test/attest",
        subject=_SUBJECT,
        staging_directory=staging,
    )
    connection = _FakeConnection()
    monkeypatch.setattr(oci_module, "_operate", lambda *args: (_ for _ in ()).throw(ValueError()))
    oci_module._oci_worker(connection, store._config, "list", None, None, None, None)
    assert connection.closed
    assert cast(oci_module._WorkerFailure, connection.messages[0]).code == "ERR-STORE-402"

    connection = _FakeConnection()
    monkeypatch.setattr(
        oci_module,
        "_operate",
        lambda *args: (_ for _ in ()).throw(store_error("ERR-STORE-403")),
    )
    oci_module._oci_worker(connection, store._config, "list", None, None, None, None)
    assert cast(oci_module._WorkerFailure, connection.messages[0]).code == "ERR-STORE-403"

    failing_connection = _FailingSendConnection()
    monkeypatch.setattr(oci_module, "_operate", lambda *args: [])
    oci_module._oci_worker(failing_connection, store._config, "list", None, None, None, None)
    assert failing_connection.closed


def test_oci_supervisor_handles_worker_protocol_and_start_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    config = OciStore("registry.test/attest", subject=_SUBJECT, staging_directory=staging)._config

    for message, expected in [
        (oci_module._WorkerSuccess([]), []),
        (oci_module._WorkerFailure("ERR-STORE-403"), "ERR-STORE-403"),
        (None, "ERR-STORE-402"),
    ]:
        process = _Process()
        receive = _ReceiveConnection(message)
        context = _ProcessContext(process, receive, _FakeConnection())
        monkeypatch.setattr(
            multiprocessing,
            "get_context",
            lambda method, context=context: context,
        )
        if isinstance(expected, list):
            assert (
                oci_module._execute_operation(config, "list", timedelta(milliseconds=50))
                == expected
            )
        else:
            with pytest.raises(StoreError) as captured:
                oci_module._execute_operation(config, "list", timedelta(milliseconds=50))
            assert captured.value.code == expected
        assert receive.closed
        assert process.closed

    process = _Process(start_error=True)
    context = _ProcessContext(process, _ReceiveConnection(None), _FakeConnection())
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: context)
    with pytest.raises(StoreError) as captured:
        oci_module._execute_operation(config, "list", timedelta(milliseconds=50))
    assert captured.value.code == "ERR-STORE-405"


def test_oci_termination_escalates_for_stubborn_worker() -> None:
    process = _Process(stubborn=True)
    process.alive = True
    oci_module._terminate_process(process)
    assert process.terminated
    assert process.killed
    assert not process.alive
