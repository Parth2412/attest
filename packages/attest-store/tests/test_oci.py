"""OCI 1.1 fixture-registry acceptance and adversarial tests."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from attest_store import (
    AttestationStore,
    FilesystemStore,
    GitRefStore,
    OciStore,
    OciSubject,
    StoreError,
    StoreRef,
)
from attest_store import oci as oci_module

_ARTIFACT_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
_MANIFEST_TYPE = "application/vnd.oci.image.manifest.v1+json"
_INDEX_TYPE = "application/vnd.oci.image.index.v1+json"
_EMPTY_CONFIG_TYPE = "application/vnd.oci.empty.v1+json"
_DIGEST = "5" * 64
_OTHER_DIGEST = "6" * 64


@dataclass
class _RegistryState:
    blobs: dict[str, bytes] = field(default_factory=dict)
    manifests: dict[str, bytes] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    referrers: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    delay_referrers: float = 0.0
    page_size: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class _RegistryHandler(BaseHTTPRequestHandler):
    state: _RegistryState
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def _send(self, status: int, content: bytes = b"", **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(content)))
        for key, value in headers.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()
        if self.command != "HEAD" and content:
            with suppress(BrokenPipeError):
                self.wfile.write(content)

    def _parts(self) -> tuple[list[str], dict[str, list[str]]]:
        parsed = urlsplit(self.path)
        return parsed.path.strip("/").split("/"), parse_qs(parsed.query)

    def do_HEAD(self) -> None:
        parts, _ = self._parts()
        if len(parts) == 4 and parts[:3] == ["v2", "attest", "blobs"]:
            digest = parts[3]
            with self.state.lock:
                exists = digest in self.state.blobs
            self._send(200 if exists else 404)
            return
        self._send(404)

    def do_POST(self) -> None:
        parts, _ = self._parts()
        if parts == ["v2", "attest", "blobs", "uploads"]:
            host, port = cast(tuple[str, int], self.server.server_address)
            location = f"http://{host}:{port}"
            self._send(202, Location=f"{location}/v2/attest/blobs/uploads/session")
            return
        self._send(404)

    def do_PUT(self) -> None:
        parts, query = self._parts()
        length = int(self.headers.get("Content-Length", "0"))
        content = self.rfile.read(length)
        if parts == ["v2", "attest", "blobs", "uploads", "session"]:
            digest = query.get("digest", [""])[0]
            actual = f"sha256:{sha256(content).hexdigest()}"
            if digest != actual:
                self._send(400)
                return
            with self.state.lock:
                self.state.blobs[digest] = content
            self._send(201, Docker_Content_Digest=digest)
            return
        if len(parts) == 4 and parts[:3] == ["v2", "attest", "manifests"]:
            try:
                manifest = cast(dict[str, object], json.loads(content))
                subject = cast(dict[str, object], manifest["subject"])
                subject_digest = cast(str, subject["digest"])
                annotations = cast(dict[str, str], manifest["annotations"])
            except (KeyError, TypeError, ValueError):
                self._send(400)
                return
            digest = f"sha256:{sha256(content).hexdigest()}"
            descriptor: dict[str, object] = {
                "mediaType": _MANIFEST_TYPE,
                "digest": digest,
                "size": len(content),
                "artifactType": manifest.get("artifactType"),
                "annotations": annotations,
            }
            with self.state.lock:
                self.state.manifests[digest] = content
                self.state.tags[parts[3]] = digest
                descriptors = self.state.referrers.setdefault(subject_digest, [])
                if not any(item["digest"] == digest for item in descriptors):
                    descriptors.append(descriptor)
            self._send(201, Docker_Content_Digest=digest)
            return
        self._send(404)

    def do_GET(self) -> None:
        parts, query = self._parts()
        if len(parts) == 4 and parts[:3] == ["v2", "attest", "referrers"]:
            if self.state.delay_referrers:
                time.sleep(self.state.delay_referrers)
            with self.state.lock:
                descriptors = list(self.state.referrers.get(parts[3], []))
            headers = {"Content_Type": _INDEX_TYPE}
            if self.state.page_size is not None:
                page = int(query.get("page", ["1"])[0])
                start = (page - 1) * self.state.page_size
                end = start + self.state.page_size
                if end < len(descriptors):
                    headers["Link"] = (
                        f'</v2/attest/referrers/{parts[3]}?page={page + 1}>; rel="next"'
                    )
                descriptors = descriptors[start:end]
            content = json.dumps(
                {"schemaVersion": 2, "mediaType": _INDEX_TYPE, "manifests": descriptors},
                separators=(",", ":"),
            ).encode()
            self._send(200, content, **headers)
            return
        if len(parts) == 4 and parts[:3] == ["v2", "attest", "manifests"]:
            with self.state.lock:
                digest = self.state.tags.get(parts[3], parts[3])
                manifest_content = self.state.manifests.get(digest)
            if manifest_content is None:
                self._send(404)
            else:
                self._send(
                    200,
                    manifest_content,
                    Content_Type=_MANIFEST_TYPE,
                    Docker_Content_Digest=digest,
                )
            return
        if len(parts) == 4 and parts[:3] == ["v2", "attest", "blobs"]:
            with self.state.lock:
                blob_content = self.state.blobs.get(parts[3])
            if blob_content is None:
                self._send(404)
            else:
                self._send(200, blob_content, Content_Type="application/octet-stream")
            return
        self._send(404)


@pytest.fixture
def registry() -> Iterator[tuple[str, _RegistryState]]:
    state = _RegistryState()
    handler = type("FixtureRegistryHandler", (_RegistryHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}/attest", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _subject() -> OciSubject:
    return OciSubject(media_type=_MANIFEST_TYPE, digest=f"sha256:{'a' * 64}", size=123)


def _put_oci_from_process(
    repository: str, staging_directory: str, digest: str, bundle: bytes
) -> tuple[str, str]:
    script = """
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from attest_store import OciStore, OciSubject

store = OciStore(
    sys.argv[1],
    subject=OciSubject(
        media_type="application/vnd.oci.image.manifest.v1+json",
        digest=f"sha256:{'a' * 64}",
        size=123,
    ),
    staging_directory=Path(sys.argv[2]),
    insecure=True,
    clock=lambda: datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC),
)
reference = store.put(sys.argv[3], bytes.fromhex(sys.argv[4]))
print(json.dumps([reference.location, reference.bundle_digest]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, repository, staging_directory, digest, bundle.hex()],
        check=True,
        capture_output=True,
        text=True,
        timeout=130,
    )
    location, digest_of_bundle = cast(list[str], json.loads(result.stdout))
    return location, digest_of_bundle


@pytest.mark.ac("AC-F07-010")
@pytest.mark.ac("AC-F07-020")
@pytest.mark.parametrize("backend", ["filesystem", "git-pygit2", "git-subprocess", "oci"])
def test_all_backends_pass_the_same_store_contract(
    backend: str,
    tmp_path: Path,
    stored_at: datetime,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-010/020: every implementation satisfies one exact-byte contract."""
    if backend == "filesystem":
        store: AttestationStore = FilesystemStore(tmp_path, clock=lambda: stored_at)
    elif backend.startswith("git-"):
        repository = tmp_path / "repository.git"
        subprocess.run(["git", "init", "--bare", str(repository)], check=True, capture_output=True)
        store = GitRefStore(
            repository,
            backend=cast(Literal["pygit2", "subprocess"], backend.removeprefix("git-")),
            clock=lambda: stored_at,
        )
    else:
        staging = tmp_path / "staging"
        staging.mkdir()
        store = OciStore(
            registry[0],
            subject=_subject(),
            staging_directory=staging,
            insecure=True,
            clock=lambda: stored_at,
        )

    first = store.put(_DIGEST, b"second-by-hash")
    duplicate = store.put(_DIGEST, b"second-by-hash")
    second = store.put(_DIGEST, b"first-by-hash")

    assert duplicate == first
    assert store.get(_DIGEST) == sorted(
        [b"second-by-hash", b"first-by-hash"], key=lambda value: sha256(value).digest()
    )
    assert list(store.list()) == sorted(
        [first, second],
        key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
    )
    assert list(store.list(stored_at + timedelta(seconds=1))) == []
    with pytest.raises(StoreError) as captured:
        store.get(_OTHER_DIGEST)
    assert captured.value.code == "ERR-STORE-403"


@pytest.mark.ac("AC-F07-090")
def test_oci_subject_is_complete_immutable_and_validated() -> None:
    """REQ-F07-090: callers bind storage to one immutable subject descriptor."""
    subject = _subject()
    assert subject.size == 123
    with pytest.raises(FrozenInstanceError):
        subject.size = 124  # type: ignore[misc]

    for values in [
        {"media_type": "", "digest": subject.digest, "size": 1},
        {"media_type": _MANIFEST_TYPE, "digest": "a" * 64, "size": 1},
        {"media_type": _MANIFEST_TYPE, "digest": f"sha256:{'A' * 64}", "size": 1},
        {"media_type": _MANIFEST_TYPE, "digest": subject.digest, "size": -1},
    ]:
        with pytest.raises(StoreError) as captured:
            OciSubject(**values)  # type: ignore[arg-type]
        assert captured.value.code == "ERR-STORE-405"


@pytest.mark.ac("AC-F07-010")
@pytest.mark.ac("AC-F07-020")
@pytest.mark.ac("AC-F07-090")
def test_oci_put_discover_get_and_list_exact_manifest(
    tmp_path: Path,
    stored_at: datetime,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-010/020/090: OCI artifacts round-trip through subject referrers."""
    repository, state = registry
    staging = tmp_path / "staging"
    staging.mkdir()
    auth = tmp_path / "auth.json"
    auth.write_text('{"auths":{}}', encoding="utf-8")
    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        auth_config=auth,
        insecure=True,
        clock=lambda: stored_at,
    )

    first = store.put(_DIGEST, b"first")
    duplicate = store.put(_DIGEST, b"first")
    second = store.put(_DIGEST, b"second")

    assert first == duplicate
    assert first.backend == "oci"
    assert first.location.startswith(f"{repository}@sha256:")
    assert store.get(_DIGEST) == sorted(
        [b"first", b"second"], key=lambda value: sha256(value).digest()
    )
    assert list(store.list()) == sorted(
        [first, second],
        key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
    )
    assert list(store.list(stored_at + timedelta(seconds=1))) == []
    assert not list(staging.iterdir())

    manifest_digest = first.location.rsplit("@", 1)[1]
    manifest = json.loads(state.manifests[manifest_digest])
    assert manifest["artifactType"] == _ARTIFACT_TYPE
    assert manifest["subject"] == {
        "mediaType": _MANIFEST_TYPE,
        "digest": f"sha256:{'a' * 64}",
        "size": 123,
    }
    assert manifest["config"] == {
        "mediaType": _EMPTY_CONFIG_TYPE,
        "digest": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "size": 2,
    }
    assert manifest["layers"] == [
        {
            "mediaType": _ARTIFACT_TYPE,
            "digest": f"sha256:{sha256(b'first').hexdigest()}",
            "size": 5,
        }
    ]
    assert manifest["annotations"] == {
        "io.github.parth2412.attest.changeset-digest": _DIGEST,
        "io.github.parth2412.attest.bundle-digest": sha256(b"first").hexdigest(),
        "org.opencontainers.image.created": "2026-09-14T12:00:00Z",
    }


@pytest.mark.ac("AC-F07-090")
def test_oci_core_follows_pagination_and_deduplicates_manifest_descriptors(
    tmp_path: Path,
    stored_at: datetime,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-090/100: the worker core follows bounded same-origin Referrers pages."""
    repository, state = registry
    staging = tmp_path / "staging"
    staging.mkdir()
    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        insecure=True,
        clock=lambda: stored_at,
    )
    config = store._config
    first = cast(
        StoreRef,
        oci_module._operate(config, "put", _DIGEST, b"first", stored_at, None),
    )
    second = cast(
        StoreRef,
        oci_module._operate(config, "put", _DIGEST, b"second", stored_at, None),
    )
    assert (
        cast(StoreRef, oci_module._operate(config, "put", _DIGEST, b"first", stored_at, None))
        == first
    )
    with state.lock:
        descriptors = state.referrers[_subject().digest]
        descriptors.append(dict(descriptors[0]))
        descriptors.append({"artifactType": "application/example", "annotations": {}})
        state.page_size = 1

    retrieved = cast(
        list[bytes],
        oci_module._operate(config, "get", _DIGEST, None, None, None),
    )
    listed = cast(
        list[StoreRef],
        oci_module._operate(config, "list", None, None, None, stored_at),
    )
    listed_without_filter = cast(
        list[StoreRef],
        oci_module._operate(config, "list", None, None, None, None),
    )

    assert retrieved == sorted([b"first", b"second"], key=lambda value: sha256(value).digest())
    assert listed == sorted(
        [first, second],
        key=lambda item: (item.stored_at, item.digest, item.bundle_digest, item.location),
    )
    assert listed_without_filter == listed
    with pytest.raises(StoreError) as captured:
        oci_module._operate(config, "get", _OTHER_DIGEST, None, None, None)
    assert captured.value.code == "ERR-STORE-403"
    assert not list(staging.iterdir())


@pytest.mark.ac("AC-F07-100")
def test_oci_process_concurrency_is_complete_and_deduplicated(
    tmp_path: Path,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-100: process writers retain every exact OCI Bundle once."""
    repository, _ = registry
    staging = tmp_path / "staging"
    staging.mkdir()
    bundles = [b"same"] * 5 + [f"distinct-{index}".encode() for index in range(5)]

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(
            executor.map(
                _put_oci_from_process,
                [repository] * len(bundles),
                [str(staging)] * len(bundles),
                [_DIGEST] * len(bundles),
                bundles,
            )
        )

    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        insecure=True,
    )
    expected = sorted(set(bundles), key=lambda value: sha256(value).digest())
    assert store.get(_DIGEST) == expected
    assert len(list(store.list())) == len(expected)
    same_results = {
        result for result, bundle in zip(results, bundles, strict=True) if bundle == b"same"
    }
    assert len(same_results) == 1
    assert not list(staging.iterdir())


@pytest.mark.ac("AC-F07-070")
@pytest.mark.ac("AC-F07-090")
def test_oci_corruption_and_absence_are_distinct(
    tmp_path: Path,
    stored_at: datetime,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-070/090: descriptor corruption fails while absence remains not-found."""
    repository, state = registry
    staging = tmp_path / "staging"
    staging.mkdir()
    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        insecure=True,
        clock=lambda: stored_at,
    )
    reference = store.put(_DIGEST, b"not-a-valid-bundle")

    assert store.get(_DIGEST) == [b"not-a-valid-bundle"]
    with pytest.raises(StoreError) as captured:
        store.get(_OTHER_DIGEST)
    assert captured.value.code == "ERR-STORE-403"

    manifest = json.loads(state.manifests[reference.location.rsplit("@", 1)[1]])
    layer_digest = manifest["layers"][0]["digest"]
    with state.lock:
        state.blobs[layer_digest] = b"corrupted"
    with pytest.raises(StoreError) as captured:
        store.get(_DIGEST)
    assert captured.value.code == "ERR-STORE-404"
    with pytest.raises(StoreError) as captured:
        oci_module._operate(store._config, "get", _DIGEST, None, None, None)
    assert captured.value.code == "ERR-STORE-404"


@pytest.mark.ac("AC-F07-090")
def test_oci_deadline_terminates_unbounded_oras_request(
    tmp_path: Path,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-090: the parent returns at its hard deadline despite ORAS blocking."""
    repository, state = registry
    state.delay_referrers = 1.0
    staging = tmp_path / "staging"
    staging.mkdir()
    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        insecure=True,
        operation_timeout=timedelta(milliseconds=100),
    )
    started = time.monotonic()

    with pytest.raises(StoreError) as captured:
        store.get(_DIGEST)

    assert captured.value.code == "ERR-STORE-402"
    assert time.monotonic() - started < 0.8


@pytest.mark.ac("AC-F07-110")
def test_oci_staging_and_configuration_are_explicit_and_contained(
    tmp_path: Path,
    stored_at: datetime,
    registry: tuple[str, _RegistryState],
) -> None:
    """REQ-F07-110: OCI creates temporary material only in its staging directory."""
    repository, _ = registry
    staging = tmp_path / "staging"
    outside = tmp_path / "outside"
    staging.mkdir()
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"unchanged")
    auth = tmp_path / "auth.json"
    auth.write_text('{"auths":{}}', encoding="utf-8")
    store = OciStore(
        repository,
        subject=_subject(),
        staging_directory=staging,
        auth_config=auth,
        insecure=True,
        clock=lambda: stored_at,
    )

    store.put(_DIGEST, b"bundle")

    assert not list(staging.iterdir())
    assert marker.read_bytes() == b"unchanged"
    assert auth.read_text(encoding="utf-8") == '{"auths":{}}'


def test_oci_configuration_fails_closed_before_network(tmp_path: Path) -> None:
    """REQ-F07-090/110: mutable, implicit, or unbounded configuration is rejected."""
    staging = tmp_path / "staging"
    staging.mkdir()
    subject = _subject()
    cases = [
        {"repository": "https://registry.test/attest", "subject": subject},
        {"repository": "registry.test/attest:latest", "subject": subject},
        {"repository": "user:secret@registry.test/attest", "subject": subject},
        {"repository": "registry.test/../attest", "subject": subject},
    ]
    for case in cases:
        with pytest.raises(StoreError) as captured:
            OciStore(**case, staging_directory=staging)  # type: ignore[arg-type]
        assert captured.value.code == "ERR-STORE-405"

    with pytest.raises(StoreError) as captured:
        OciStore(
            "registry.test/attest",
            subject=subject,
            staging_directory=staging,
            operation_timeout=timedelta(0),
        )
    assert captured.value.code == "ERR-STORE-405"
