"""Deadline-isolated OCI 1.1 storage governed by BRD-F07 and ADR-043."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import re
import secrets
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal, Protocol, cast
from urllib.parse import urlsplit

from attest_store._metadata import (
    bundle_digest,
    format_time,
    is_positive_timeout,
    normalize_time,
    parse_time,
    validate_bundle,
    validate_digest,
    validate_since,
)
from attest_store.errors import StoreError, StoreErrorCode, store_error
from attest_store.protocols import StoreRef

_ARTIFACT_TYPE: Final = "application/vnd.dev.sigstore.bundle.v0.3+json"
_MANIFEST_TYPE: Final = "application/vnd.oci.image.manifest.v1+json"
_INDEX_TYPE: Final = "application/vnd.oci.image.index.v1+json"
_EMPTY_CONFIG_TYPE: Final = "application/vnd.oci.empty.v1+json"
_EMPTY_CONFIG_DIGEST: Final = (
    "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
)
_CHANGESET_ANNOTATION: Final = "io.github.parth2412.attest.changeset-digest"
_BUNDLE_ANNOTATION: Final = "io.github.parth2412.attest.bundle-digest"
_CREATED_ANNOTATION: Final = "org.opencontainers.image.created"
_DEFAULT_OPERATION_TIMEOUT = timedelta(seconds=120)
_PROCESS_SHUTDOWN_GRACE_SECONDS = 1.0
_PROCESS_POLL_SECONDS = 0.05
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_REFERRER_PAGES = 1000
_MEDIA_TYPE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*"
)
_OCI_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_REGISTRY_PATTERN = re.compile(
    r"(?:localhost|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::[0-9]{1,5})?"
)
_REPOSITORY_COMPONENT = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


class _Response(Protocol):
    status_code: int
    content: bytes
    headers: Mapping[str, str]


class _Auth(Protocol):
    def load_configs(self, container: object, configs: list[str] | None = None) -> object: ...


class _Container(Protocol):
    registry: str
    api_prefix: str


class _Client(Protocol):
    prefix: str
    auth: _Auth

    def get_container(self, name: str) -> _Container: ...

    def upload_blob(self, blob: str, container: object, layer: dict[str, object]) -> _Response: ...

    def upload_manifest(self, manifest: dict[str, object], container: object) -> _Response: ...

    def do_request(
        self,
        url: str,
        method: str = "GET",
        data: dict[str, object] | bytes | None = None,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        stream: bool = False,
    ) -> _Response: ...


type OciClientFactory = Callable[[bool, bool | str], _Client]
type _Operation = Literal["put", "get", "list"]
type _OperationResult = StoreRef | list[StoreRef] | list[bytes]


class _SendConnection(Protocol):
    def send(self, value: object) -> None: ...

    def close(self) -> None: ...


class _ReceiveConnection(Protocol):
    def poll(self, timeout: float = 0.0) -> bool: ...

    def recv(self) -> object: ...

    def close(self) -> None: ...


class _Process(Protocol):
    def start(self) -> None: ...

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OciSubject:
    """Identify one immutable OCI manifest subject (REQ-F07-090)."""

    media_type: str
    digest: str
    size: int

    def __post_init__(self) -> None:
        if not _valid_subject_parts(self.media_type, self.digest, self.size):
            raise store_error("ERR-STORE-405")


@dataclass(frozen=True, slots=True)
class _OciConfig:
    repository: str
    subject: OciSubject
    staging_directory: str
    staging_identity: tuple[int, int]
    auth_config: str | None
    insecure: bool
    tls_verify: bool | str
    client_factory: OciClientFactory


@dataclass(frozen=True, slots=True)
class _WorkerSuccess:
    result: _OperationResult


@dataclass(frozen=True, slots=True)
class _WorkerFailure:
    code: StoreErrorCode


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _valid_subject_parts(media_type: object, digest: object, size: object) -> bool:
    return (
        isinstance(media_type, str)
        and _MEDIA_TYPE_PATTERN.fullmatch(media_type) is not None
        and isinstance(digest, str)
        and _OCI_DIGEST_PATTERN.fullmatch(digest) is not None
        and not isinstance(size, bool)
        and isinstance(size, int)
        and size >= 0
    )


def _configured_subject(value: object) -> OciSubject:
    if not isinstance(value, OciSubject):
        raise store_error("ERR-STORE-405")
    return value


def _configured_insecure(value: object) -> bool:
    if not isinstance(value, bool):
        raise store_error("ERR-STORE-405")
    return value


def _default_client_factory(insecure: bool, tls_verify: bool | str) -> _Client:
    from oras.client import OrasClient  # type: ignore[import-untyped]

    return cast(_Client, OrasClient(insecure=insecure, tls_verify=tls_verify))


def _configured_factory(value: object) -> OciClientFactory:
    if not callable(value):
        raise store_error("ERR-STORE-405")
    return cast(OciClientFactory, value)


def _configured_clock(value: object) -> Callable[[], datetime]:
    if not callable(value):
        raise store_error("ERR-STORE-405")
    return cast(Callable[[], datetime], value)


def _configured_repository(value: object) -> str:
    if not isinstance(value, str) or not value or "://" in value or "@" in value:
        raise store_error("ERR-STORE-405")
    if any(ord(character) < 33 for character in value) or "?" in value or "#" in value:
        raise store_error("ERR-STORE-405")
    components = value.split("/")
    if (
        len(components) < 2
        or _REGISTRY_PATTERN.fullmatch(components[0]) is None
        or any(_REPOSITORY_COMPONENT.fullmatch(component) is None for component in components[1:])
    ):
        raise store_error("ERR-STORE-405")
    registry_port = components[0].rsplit(":", 1)
    if len(registry_port) == 2 and int(registry_port[1]) > 65535:
        raise store_error("ERR-STORE-405")
    return value


def _configured_file(value: object, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, Path | str):
        raise store_error("ERR-STORE-405")
    path = Path(value)
    try:
        if (
            not path.is_absolute()
            or any(ord(character) < 32 for character in os.fspath(path))
            or path.is_symlink()
            or not path.is_file()
        ):
            raise store_error("ERR-STORE-405")
        return str(path.resolve(strict=True))
    except StoreError:
        raise
    except (OSError, RuntimeError):
        raise store_error("ERR-STORE-405") from None


def _configured_directory(value: object) -> tuple[str, tuple[int, int]]:
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
        status = resolved.stat(follow_symlinks=False)
        return str(resolved), (status.st_dev, status.st_ino)
    except StoreError:
        raise
    except (OSError, RuntimeError):
        raise store_error("ERR-STORE-405") from None


def _configured_tls(value: object) -> bool | str:
    if isinstance(value, bool):
        return value
    path = _configured_file(value, required=True)
    if path is None:  # pragma: no cover - required=True proves this unreachable
        raise store_error("ERR-STORE-405")
    return path


def _validate_staging(config: _OciConfig) -> Path:
    path = Path(config.staging_directory)
    try:
        status = path.stat(follow_symlinks=False)
    except OSError:
        raise store_error("ERR-STORE-404") from None
    if (
        path.is_symlink()
        or not path.is_dir()
        or (status.st_dev, status.st_ino) != config.staging_identity
    ):
        raise store_error("ERR-STORE-404")
    return path


def _validate_config_file(path_value: str | None) -> None:
    if path_value is None:
        return
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise store_error("ERR-STORE-404")
    except StoreError:
        raise
    except OSError:
        raise store_error("ERR-STORE-404") from None


def _no_default_docker_config(_exists: bool = True) -> None:
    return None


def _load_explicit_auth(client: _Client, container: _Container, config_path: str | None) -> None:
    if config_path is None:
        return
    import oras.utils  # type: ignore[import-untyped]

    original = oras.utils.find_docker_config
    oras.utils.find_docker_config = _no_default_docker_config
    try:
        client.auth.load_configs(container, configs=[config_path])
    finally:
        oras.utils.find_docker_config = original


def _new_client(config: _OciConfig, target: str) -> tuple[_Client, _Container, str]:
    try:
        _validate_config_file(config.auth_config)
        _validate_config_file(config.tls_verify if isinstance(config.tls_verify, str) else None)
        client = config.client_factory(config.insecure, config.tls_verify)
        container = client.get_container(target)
        _load_explicit_auth(client, container, config.auth_config)
        base_url = f"{client.prefix}://{container.registry}/v2/{container.api_prefix}"
    except StoreError:
        raise
    except Exception:
        raise store_error("ERR-STORE-402") from None
    return client, container, base_url


def _check_response(response: _Response, allowed: tuple[int, ...], code: StoreErrorCode) -> None:
    if response.status_code not in allowed:
        raise store_error(code)


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _json_object(raw: bytes) -> dict[str, object]:
    if len(raw) > _MAX_JSON_BYTES:
        raise store_error("ERR-STORE-404")
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_object_pairs)
    except (RecursionError, TypeError, ValueError, UnicodeError):
        raise store_error("ERR-STORE-404") from None
    if not isinstance(decoded, dict):
        raise store_error("ERR-STORE-404")
    return cast(dict[str, object], decoded)


def _descriptor_digest(value: object) -> str:
    if not isinstance(value, str) or _OCI_DIGEST_PATTERN.fullmatch(value) is None:
        raise store_error("ERR-STORE-404")
    return value


def _descriptor_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise store_error("ERR-STORE-404")
    return value


def _stored_digest(value: object) -> str:
    try:
        return validate_digest(value)
    except StoreError:
        raise store_error("ERR-STORE-404") from None


def _annotations(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise store_error("ERR-STORE-404")
    annotations = cast(dict[object, object], value)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in annotations.items()):
        raise store_error("ERR-STORE-404")
    return cast(dict[str, str], annotations)


def _subject_wire(subject: OciSubject) -> dict[str, object]:
    return {"mediaType": subject.media_type, "digest": subject.digest, "size": subject.size}


def _request(client: _Client, url: str, *, headers: dict[str, str]) -> _Response:
    try:
        return client.do_request(url, "GET", headers=headers)
    except Exception:
        raise store_error("ERR-STORE-402") from None


def _referrer_descriptors(
    client: _Client,
    base_url: str,
    subject: OciSubject,
) -> list[dict[str, object]]:
    endpoint = f"{base_url}/referrers/{subject.digest}"
    url = endpoint
    visited: set[str] = set()
    descriptors: list[dict[str, object]] = []
    for _ in range(_MAX_REFERRER_PAGES):
        if url in visited:
            raise store_error("ERR-STORE-404")
        visited.add(url)
        response = _request(client, url, headers={"Accept": _INDEX_TYPE})
        _check_response(response, (200,), "ERR-STORE-402")
        index = _json_object(response.content)
        manifests = index.get("manifests")
        if (
            index.get("schemaVersion") != 2
            or index.get("mediaType") != _INDEX_TYPE
            or not isinstance(manifests, list)
        ):
            raise store_error("ERR-STORE-404")
        for descriptor in manifests:
            if not isinstance(descriptor, dict):
                raise store_error("ERR-STORE-404")
            descriptors.append(cast(dict[str, object], descriptor))
        link = response.headers.get("Link")
        if link is None:
            return descriptors
        match = re.fullmatch(r'<(?P<target>[^>]+)>;\s*rel="next"', link)
        if match is None:
            raise store_error("ERR-STORE-404")
        target = match.group("target")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not target.startswith("/v2/"):
            raise store_error("ERR-STORE-404")
        expected_path = urlsplit(endpoint).path
        if parsed.path != expected_path:
            raise store_error("ERR-STORE-404")
        origin = endpoint.removesuffix(expected_path)
        url = f"{origin}{target}"
    raise store_error("ERR-STORE-404")


def _matching_descriptor(descriptor: dict[str, object]) -> bool:
    if descriptor.get("artifactType") != _ARTIFACT_TYPE:
        return False
    annotation_value = descriptor.get("annotations")
    if annotation_value is None:
        return False
    annotations = _annotations(annotation_value)
    attest_keys = {_CHANGESET_ANNOTATION, _BUNDLE_ANNOTATION, _CREATED_ANNOTATION}
    if not attest_keys <= set(annotations):
        if set(annotations) & attest_keys:
            raise store_error("ERR-STORE-404")
        return False
    _stored_digest(annotations[_CHANGESET_ANNOTATION])
    _stored_digest(annotations[_BUNDLE_ANNOTATION])
    parse_time(annotations[_CREATED_ANNOTATION])
    return True


def _validate_manifest(
    raw: bytes,
    descriptor: dict[str, object],
    subject: OciSubject,
) -> tuple[StoreRef, str, int]:
    descriptor_digest = _descriptor_digest(descriptor.get("digest"))
    descriptor_size = _descriptor_size(descriptor.get("size"))
    if (
        descriptor.get("mediaType") != _MANIFEST_TYPE
        or descriptor_size != len(raw)
        or descriptor_digest != f"sha256:{sha256(raw).hexdigest()}"
    ):
        raise store_error("ERR-STORE-404")
    manifest = _json_object(raw)
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("mediaType") != _MANIFEST_TYPE
        or manifest.get("artifactType") != _ARTIFACT_TYPE
        or manifest.get("subject") != _subject_wire(subject)
    ):
        raise store_error("ERR-STORE-404")
    config = manifest.get("config")
    if config != {
        "mediaType": _EMPTY_CONFIG_TYPE,
        "digest": _EMPTY_CONFIG_DIGEST,
        "size": 2,
    }:
        raise store_error("ERR-STORE-404")
    layers = manifest.get("layers")
    if not isinstance(layers, list) or len(layers) != 1 or not isinstance(layers[0], dict):
        raise store_error("ERR-STORE-404")
    layer = cast(dict[str, object], layers[0])
    layer_digest = _descriptor_digest(layer.get("digest"))
    layer_size = _descriptor_size(layer.get("size"))
    if layer.get("mediaType") != _ARTIFACT_TYPE:
        raise store_error("ERR-STORE-404")
    annotations = _annotations(manifest.get("annotations"))
    descriptor_annotations = _annotations(descriptor.get("annotations"))
    for key in (_CHANGESET_ANNOTATION, _BUNDLE_ANNOTATION, _CREATED_ANNOTATION):
        if annotations.get(key) != descriptor_annotations.get(key):
            raise store_error("ERR-STORE-404")
    digest = _stored_digest(annotations.get(_CHANGESET_ANNOTATION))
    digest_of_bundle = _stored_digest(annotations.get(_BUNDLE_ANNOTATION))
    stored_at = parse_time(annotations.get(_CREATED_ANNOTATION))
    if layer_digest != f"sha256:{digest_of_bundle}":
        raise store_error("ERR-STORE-404")
    return (
        StoreRef(
            backend="oci",
            digest=digest,
            bundle_digest=digest_of_bundle,
            location=f"{descriptor_digest}",
            stored_at=stored_at,
        ),
        layer_digest,
        layer_size,
    )


def _discover(config: _OciConfig) -> list[tuple[StoreRef, bytes]]:
    client, _, base_url = _new_client(config, f"{config.repository}:attest-discovery")
    descriptors = _referrer_descriptors(client, base_url, config.subject)
    entries: list[tuple[StoreRef, bytes]] = []
    seen_manifests: set[str] = set()
    for descriptor in descriptors:
        if not _matching_descriptor(descriptor):
            continue
        manifest_digest = _descriptor_digest(descriptor.get("digest"))
        if manifest_digest in seen_manifests:
            continue
        seen_manifests.add(manifest_digest)
        manifest_response = _request(
            client,
            f"{base_url}/manifests/{manifest_digest}",
            headers={"Accept": _MANIFEST_TYPE},
        )
        _check_response(manifest_response, (200,), "ERR-STORE-404")
        reference, layer_digest, layer_size = _validate_manifest(
            manifest_response.content, descriptor, config.subject
        )
        bundle_response = _request(
            client,
            f"{base_url}/blobs/{layer_digest}",
            headers={"Accept": _ARTIFACT_TYPE},
        )
        _check_response(bundle_response, (200,), "ERR-STORE-404")
        bundle = bundle_response.content
        if len(bundle) != layer_size or f"sha256:{bundle_digest(bundle)}" != layer_digest:
            raise store_error("ERR-STORE-404")
        entries.append(
            (
                StoreRef(
                    backend="oci",
                    digest=reference.digest,
                    bundle_digest=reference.bundle_digest,
                    location=f"{config.repository}@{manifest_digest}",
                    stored_at=reference.stored_at,
                ),
                bundle,
            )
        )

    entries.sort(
        key=lambda entry: (
            entry[0].stored_at,
            entry[0].digest,
            entry[0].bundle_digest,
            entry[0].location,
        )
    )
    deduplicated: dict[tuple[str, str], tuple[StoreRef, bytes]] = {}
    for reference, bundle in entries:
        key = (reference.digest, reference.bundle_digest)
        existing = deduplicated.get(key)
        if existing is not None and existing[1] != bundle:
            raise store_error("ERR-STORE-404")
        deduplicated.setdefault(key, (reference, bundle))
    return list(deduplicated.values())


def _temporary_file(directory: Path, label: str, content: bytes) -> Path:
    path = directory / f".{label}.{secrets.token_hex(16)}.tmp"
    descriptor = -1
    completed = False
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise store_error("ERR-STORE-404")
            view = view[written:]
        os.fsync(descriptor)
        completed = True
    except StoreError:
        raise
    except OSError:
        raise store_error("ERR-STORE-404") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed:
            with suppress(OSError):
                path.unlink(missing_ok=True)
    return path


def _upload(config: _OciConfig, digest: str, bundle: bytes, stored_at: datetime) -> StoreRef:
    staging = _validate_staging(config)
    digest_of_bundle = bundle_digest(bundle)
    for reference, existing in _discover(config):
        if reference.digest == digest and reference.bundle_digest == digest_of_bundle:
            if existing != bundle:
                raise store_error("ERR-STORE-404")
            return reference

    identity = sha256(f"{digest}\0{digest_of_bundle}".encode()).hexdigest()
    target = f"{config.repository}:attest-{identity}"
    client, container, _ = _new_client(config, target)
    bundle_path: Path | None = None
    config_path: Path | None = None
    layer: dict[str, object] = {
        "mediaType": _ARTIFACT_TYPE,
        "digest": f"sha256:{digest_of_bundle}",
        "size": len(bundle),
    }
    empty_config: dict[str, object] = {
        "mediaType": _EMPTY_CONFIG_TYPE,
        "digest": _EMPTY_CONFIG_DIGEST,
        "size": 2,
    }
    annotations = {
        _CHANGESET_ANNOTATION: digest,
        _BUNDLE_ANNOTATION: digest_of_bundle,
        _CREATED_ANNOTATION: format_time(stored_at),
    }
    manifest: dict[str, object] = {
        "schemaVersion": 2,
        "mediaType": _MANIFEST_TYPE,
        "artifactType": _ARTIFACT_TYPE,
        "config": empty_config,
        "layers": [layer],
        "subject": _subject_wire(config.subject),
        "annotations": annotations,
    }
    try:
        bundle_path = _temporary_file(staging, "bundle", bundle)
        config_path = _temporary_file(staging, "config", b"{}")
        try:
            bundle_response = client.upload_blob(str(bundle_path), container, layer)
            _check_response(bundle_response, (200, 201, 202), "ERR-STORE-402")
            config_response = client.upload_blob(str(config_path), container, empty_config)
            _check_response(config_response, (200, 201, 202), "ERR-STORE-402")
            manifest_response = client.upload_manifest(manifest, container)
            _check_response(manifest_response, (200, 201, 202), "ERR-STORE-402")
        except StoreError:
            raise
        except Exception:
            raise store_error("ERR-STORE-402") from None
        manifest_digest = _descriptor_digest(manifest_response.headers.get("Docker-Content-Digest"))
    finally:
        try:
            if bundle_path is not None:
                bundle_path.unlink(missing_ok=True)
            if config_path is not None:
                config_path.unlink(missing_ok=True)
        except OSError:
            raise store_error("ERR-STORE-404") from None
    return StoreRef(
        backend="oci",
        digest=digest,
        bundle_digest=digest_of_bundle,
        location=f"{config.repository}@{manifest_digest}",
        stored_at=stored_at,
    )


def _operate(
    config: _OciConfig,
    operation: _Operation,
    digest: str | None,
    bundle: bytes | None,
    stored_at: datetime | None,
    since: datetime | None,
) -> _OperationResult:
    _validate_staging(config)
    if operation == "put":
        if digest is None or bundle is None or stored_at is None:
            raise store_error("ERR-STORE-405")
        return _upload(config, digest, bundle, stored_at)
    entries = _discover(config)
    if operation == "get":
        selected = [(reference, raw) for reference, raw in entries if reference.digest == digest]
        if not selected:
            raise store_error("ERR-STORE-403")
        selected.sort(key=lambda entry: entry[0].bundle_digest)
        return [raw for _, raw in selected]
    references = [reference for reference, _ in entries]
    if since is not None:
        references = [reference for reference in references if reference.stored_at >= since]
    return references


def _oci_worker(
    connection: _SendConnection,
    config: _OciConfig,
    operation: _Operation,
    digest: str | None,
    bundle: bytes | None,
    stored_at: datetime | None,
    since: datetime | None,
) -> None:
    logging.disable(logging.CRITICAL)
    try:
        message: _WorkerSuccess | _WorkerFailure = _WorkerSuccess(
            _operate(config, operation, digest, bundle, stored_at, since)
        )
    except StoreError as error:
        message = _WorkerFailure(error.code)
    except Exception:
        message = _WorkerFailure("ERR-STORE-402")
    try:
        connection.send(message)
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        connection.close()


def _terminate_process(process: _Process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(_PROCESS_SHUTDOWN_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def _execute_operation(
    config: _OciConfig,
    operation: _Operation,
    timeout: timedelta,
    *,
    digest: str | None = None,
    bundle: bytes | None = None,
    stored_at: datetime | None = None,
    since: datetime | None = None,
) -> _OperationResult:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_oci_worker,
        args=(send, config, operation, digest, bundle, stored_at, since),
        name="attest-oci-store",
    )
    deadline = time.monotonic() + timeout.total_seconds()
    message: object | None = None
    try:
        try:
            process.start()
        except Exception:
            raise store_error("ERR-STORE-405") from None
        finally:
            send.close()
        while process.is_alive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process(process)
                raise store_error("ERR-STORE-402")
            if receive.poll(min(_PROCESS_POLL_SECONDS, remaining)):
                try:
                    message = receive.recv()
                except (EOFError, OSError):
                    message = None
                break
        remaining = deadline - time.monotonic()
        process.join(max(0.0, remaining))
        if process.is_alive():
            _terminate_process(process)
            raise store_error("ERR-STORE-402")
        if message is None and receive.poll():
            try:
                message = receive.recv()
            except (EOFError, OSError):
                message = None
        if isinstance(message, _WorkerFailure):
            raise store_error(message.code)
        if isinstance(message, _WorkerSuccess):
            return message.result
        raise store_error("ERR-STORE-402")
    finally:
        receive.close()
        if process.is_alive():
            _terminate_process(process)
        process.close()


class OciStore:
    """Attach and discover exact Bundle layers through OCI 1.1 referrers."""

    def __init__(
        self,
        repository: str,
        *,
        subject: OciSubject,
        staging_directory: Path | str,
        auth_config: Path | str | None = None,
        insecure: bool = False,
        tls_verify: bool | Path | str = True,
        operation_timeout: timedelta = _DEFAULT_OPERATION_TIMEOUT,
        clock: Callable[[], datetime] = _utc_now,
        client_factory: OciClientFactory = _default_client_factory,
    ) -> None:
        configured_repository = _configured_repository(repository)
        configured_subject = _configured_subject(subject)
        configured_insecure = _configured_insecure(insecure)
        staging_path, staging_identity = _configured_directory(staging_directory)
        configured_auth = _configured_file(auth_config, required=False)
        configured_tls = _configured_tls(tls_verify)
        if not is_positive_timeout(operation_timeout):
            raise store_error("ERR-STORE-405")
        self._config = _OciConfig(
            repository=configured_repository,
            subject=configured_subject,
            staging_directory=staging_path,
            staging_identity=staging_identity,
            auth_config=configured_auth,
            insecure=configured_insecure,
            tls_verify=configured_tls,
            client_factory=_configured_factory(client_factory),
        )
        self._timeout = operation_timeout
        self._clock = _configured_clock(clock)

    @property
    def subject(self) -> OciSubject:
        """Return the immutable configured subject descriptor."""
        return self._config.subject

    def put(self, digest: str, bundle: bytes) -> StoreRef:
        """Attach one exact Bundle manifest under a hard deadline."""
        validated_digest = validate_digest(digest)
        validated_bundle = validate_bundle(bundle)
        try:
            stored_at = normalize_time(self._clock())
        except StoreError:
            raise
        except Exception:
            raise store_error("ERR-STORE-405") from None
        result = _execute_operation(
            self._config,
            "put",
            self._timeout,
            digest=validated_digest,
            bundle=validated_bundle,
            stored_at=stored_at,
        )
        if not isinstance(result, StoreRef):
            raise store_error("ERR-STORE-404")
        return result

    def get(self, digest: str) -> list[bytes]:
        """Return exact referrer Bundle layers in Bundle-digest order."""
        result = _execute_operation(
            self._config,
            "get",
            self._timeout,
            digest=validate_digest(digest),
        )
        if not isinstance(result, list) or not all(isinstance(item, bytes) for item in result):
            raise store_error("ERR-STORE-404")
        return cast(list[bytes], result)

    def list(self, since: datetime | None = None) -> Iterator[StoreRef]:
        """List deduplicated complete referrers by persisted storage time."""
        result = _execute_operation(
            self._config,
            "list",
            self._timeout,
            since=validate_since(since),
        )
        if not isinstance(result, list) or not all(isinstance(item, StoreRef) for item in result):
            raise store_error("ERR-STORE-404")
        return iter(cast(list[StoreRef], result))
