"""Validate the exact reviewed F-11 candidate before release promotion."""

# ruff: noqa: TRY003  # Release-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NoReturn

DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REFERENCE: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*image:[ \t]+docker://ghcr\.io/parth2412/attest@(sha256:[0-9a-f]{64})[ \t]*$",
    re.MULTILINE,
)
SOURCE_REFERENCE: Final[re.Pattern[str]] = re.compile(
    r"ghcr\.io/parth2412/attest@(sha256:[0-9a-f]{64})\Z"
)
EXPECTED_FILES: Final[frozenset[str]] = frozenset(
    {
        "build-metadata.json",
        "context-digest.txt",
        "context-manifest.json",
        "image-digest.txt",
        "layers-linux-amd64.json",
        "layers-linux-arm64.json",
        "manifest.json",
        "manifest-linux-amd64.json",
        "manifest-linux-arm64.json",
        "provenance.slsa.json",
        "sbom.spdx.json",
    }
)
EXPECTED_SOURCE_EVIDENCE_FILES: Final[frozenset[str]] = frozenset(
    {
        "runtime-components.openvex.json",
        "runtime-components.spdx.json",
        "source-artifact-digest.txt",
        "source-artifact-manifest.json",
        "source-artifact-reference.txt",
        "source-attestation-verification.json",
        "source-attestation.jsonl",
        "source-manifest.json",
    }
)
EXPECTED_RUNTIME_SOURCE_FILES: Final[frozenset[str]] = frozenset(
    {
        "Dockerfile",
        "SOURCE-MANIFEST.json",
        "curl-8.23.0.tar.xz",
        "curl-COPYING",
        "git-2.52.0.tar.xz",
        "git-COPYING",
        "runtime-components.openvex.json",
        "runtime-components.spdx.json",
        "runtime-sources.json",
    }
)
EXPECTED_COMPONENTS: Final[dict[str, dict[str, str]]] = {
    "curl": {
        "version": "8.23.0",
        "license": "curl",
        "purl": "pkg:generic/curl@8.23.0",
        "cpe": "cpe:2.3:a:haxx:curl:8.23.0:*:*:*:*:*:*:*",
        "archive": "curl-8.23.0.tar.xz",
        "algorithm": "sha512",
        "digest": (
            "69cf0feafdc79fbad007cf2fc977b777ce6ccb05d01afd17b5a42f8bedbfcc342"
            "fc3a48193faa7f3eafe6800cd7d07948916e8733db1b9de60287ed06219b840"
        ),
    },
    "git": {
        "version": "2.52.0",
        "license": "GPL-2.0-only",
        "purl": "pkg:generic/git@2.52.0",
        "cpe": "cpe:2.3:a:git-scm:git:2.52.0:*:*:*:*:*:*:*",
        "archive": "git-2.52.0.tar.xz",
        "algorithm": "sha256",
        "digest": "3cd8fee86f69a949cb610fee8cd9264e6873d07fa58411f6060b3d62729ed7c5",
    },
}
PLATFORMS: Final[frozenset[str]] = frozenset({"linux/amd64", "linux/arm64"})
PLATFORM_MANIFESTS: Final[dict[str, str]] = {
    "linux/amd64": "manifest-linux-amd64.json",
    "linux/arm64": "manifest-linux-arm64.json",
}
ZSTD_LAYER_MEDIA_TYPE: Final[str] = "application/vnd.oci.image.layer.v1.tar+zstd"
MAX_FILE_BYTES: Final[int] = 32 * 1024 * 1024


class CandidateValidationError(ValueError):
    """Candidate evidence differs from the reviewed release contract."""


def _fail(message: str) -> NoReturn:
    raise CandidateValidationError(message)


def _regular_bytes(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CandidateValidationError(f"missing candidate evidence: {path.name}") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        _fail(f"candidate evidence must be a regular file: {path.name}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_FILE_BYTES:
        _fail(f"candidate evidence has an invalid size: {path.name}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise CandidateValidationError(f"candidate evidence cannot be read: {path.name}") from error


def _text(path: Path) -> str:
    try:
        return _regular_bytes(path).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise CandidateValidationError(f"candidate evidence must be UTF-8: {path.name}") from error


def _json(path: Path) -> object:
    try:
        return json.loads(_text(path))
    except json.JSONDecodeError as error:
        raise CandidateValidationError(
            f"candidate evidence must be valid JSON: {path.name}"
        ) from error


def _digest_text(path: Path, label: str) -> str:
    value = _text(path)
    if not value.endswith("\n") or "\n" in value[:-1] or DIGEST.fullmatch(value[:-1]) is None:
        _fail(f"invalid {label} evidence")
    return value[:-1]


def _manifest_digest(document: dict[str, object]) -> str:
    content = {key: value for key, value in document.items() if key != "contextDigest"}
    encoded = json.dumps(content, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _validate_context(
    evidence: Path,
    current_context_manifest: Path,
    expected_context_digest: str,
) -> None:
    evidence_digest = _digest_text(evidence / "context-digest.txt", "context digest")
    if evidence_digest != expected_context_digest:
        _fail("context digest mismatch")

    evidence_manifest = _json(evidence / "context-manifest.json")
    current_manifest = _json(current_context_manifest)
    if not isinstance(evidence_manifest, dict) or not isinstance(current_manifest, dict):
        _fail("context manifest must be a JSON object")
    if evidence_manifest.get("contextDigest") != expected_context_digest:
        _fail("candidate context manifest digest mismatch")
    if current_manifest.get("contextDigest") != expected_context_digest:
        _fail("current context digest mismatch")
    if _manifest_digest(evidence_manifest) != expected_context_digest:
        _fail("candidate context manifest is not self-consistent")
    if _manifest_digest(current_manifest) != expected_context_digest:
        _fail("current context manifest is not self-consistent")
    if evidence_manifest != current_manifest:
        _fail("final context differs from the reviewed candidate")


def _platforms(manifest: object) -> tuple[dict[str, str], int]:
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
        _fail("candidate image manifest is invalid")
    descriptors = manifest.get("manifests")
    if not isinstance(descriptors, list) or not descriptors:
        _fail("candidate image manifest has no descriptors")
    runnable: dict[str, str] = {}
    attached = 0
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            _fail("candidate image descriptor is invalid")
        platform = descriptor.get("platform")
        if not isinstance(platform, dict):
            _fail("candidate image platform is invalid")
        operating_system = platform.get("os")
        architecture = platform.get("architecture")
        if not isinstance(operating_system, str) or not isinstance(architecture, str):
            _fail("candidate image platform is invalid")
        if operating_system == "unknown" and architecture == "unknown":
            attached += 1
        else:
            platform_name = f"{operating_system}/{architecture}"
            digest = descriptor.get("digest")
            if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
                _fail(f"candidate {platform_name} descriptor digest is invalid")
            if platform_name in runnable:
                _fail(f"candidate image repeats platform {platform_name}")
            runnable[platform_name] = digest
    return runnable, attached


def _validate_platform_manifest(
    evidence: Path,
    platform: str,
    expected_digest: str,
) -> None:
    name = PLATFORM_MANIFESTS[platform]
    raw = _regular_bytes(evidence / name)
    observed_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if observed_digest != expected_digest:
        _fail(f"candidate {platform} manifest digest mismatch")
    try:
        document = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidateValidationError(
            f"candidate {platform} manifest must be valid JSON"
        ) from error
    if (
        not isinstance(document, dict)
        or document.get("schemaVersion") != 2
        or document.get("mediaType") != "application/vnd.oci.image.manifest.v1+json"
    ):
        _fail(f"candidate {platform} manifest is invalid")
    layers = document.get("layers")
    if not isinstance(layers, list) or len(layers) != 4:
        _fail(f"candidate {platform} manifest does not have four layers")
    for layer in layers:
        if not isinstance(layer, dict) or layer.get("mediaType") != ZSTD_LAYER_MEDIA_TYPE:
            _fail(f"candidate {platform} image layers are not all zstd")
        digest = layer.get("digest")
        size = layer.get("size")
        if (
            not isinstance(digest, str)
            or DIGEST.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            _fail(f"candidate {platform} layer descriptor is invalid")
    layer_evidence = _json(evidence / f"layers-{platform.replace('/', '-')}.json")
    if layer_evidence != {
        "platform": platform,
        "primaryLayers": layers[:3],
        "entrypointLayer": layers[3],
    }:
        _fail(f"invalid candidate {platform} layer evidence")


def _validate_platform_evidence(path: Path, label: str) -> None:
    document = _json(path)
    if (
        not isinstance(document, dict)
        or set(document) != PLATFORMS
        or any(not isinstance(value, dict) or not value for value in document.values())
    ):
        _fail(f"invalid {label} platform evidence")


def _validate_image(evidence: Path, expected_image_digest: str) -> None:
    evidence_digest = _digest_text(evidence / "image-digest.txt", "image digest")
    if evidence_digest != expected_image_digest:
        _fail("image digest mismatch")

    manifest_bytes = _regular_bytes(evidence / "manifest.json")
    observed_digest = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
    if observed_digest != expected_image_digest:
        _fail("candidate manifest bytes do not match the reviewed image digest")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidateValidationError("candidate image manifest must be valid JSON") from error
    runnable, attached = _platforms(manifest)
    if set(runnable) != PLATFORMS or attached < 1:
        _fail("candidate image does not contain the exact platforms and attestations")
    for platform, digest in runnable.items():
        _validate_platform_manifest(evidence, platform, digest)

    metadata = _json(evidence / "build-metadata.json")
    if (
        not isinstance(metadata, dict)
        or metadata.get("containerimage.digest") != expected_image_digest
    ):
        _fail("build metadata image digest mismatch")
    descriptor = metadata.get("containerimage.descriptor")
    if not isinstance(descriptor, dict) or descriptor.get("digest") != expected_image_digest:
        _fail("build metadata descriptor mismatch")

    _validate_platform_evidence(evidence / "sbom.spdx.json", "SBOM")
    _validate_platform_evidence(evidence / "provenance.slsa.json", "provenance")


def _validate_action_manifest(action_manifest: Path, expected_image_digest: str) -> None:
    manifest = _text(action_manifest)
    matches = IMAGE_REFERENCE.findall(manifest)
    if matches != [expected_image_digest]:
        _fail("Action manifest does not pin the reviewed image digest")


def _validate_source_contract(runtime_sources: Path) -> None:
    document = _json(runtime_sources / "runtime-sources.json")
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "components"}:
        _fail("runtime source contract is invalid")
    if document.get("schemaVersion") != 1 or not isinstance(document.get("components"), list):
        _fail("runtime source contract is invalid")
    components = document["components"]
    if not isinstance(components, list) or len(components) != len(EXPECTED_COMPONENTS):
        _fail("runtime source contract has unexpected components")
    observed: dict[str, dict[str, object]] = {}
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("name"), str):
            _fail("runtime source component is invalid")
        name = component["name"]
        if name in observed:
            _fail("runtime source contract repeats a component")
        observed[name] = component
    if set(observed) != set(EXPECTED_COMPONENTS):
        _fail("runtime source contract has unexpected components")
    for name, expected in EXPECTED_COMPONENTS.items():
        component = observed[name]
        archive = component.get("archive")
        licence = component.get("licence")
        if not isinstance(archive, dict) or not isinstance(licence, dict):
            _fail(f"runtime source {name} contract is invalid")
        digest = archive.get("digest")
        if not isinstance(digest, dict):
            _fail(f"runtime source {name} digest is invalid")
        if (
            component.get("version") != expected["version"]
            or component.get("purl") != expected["purl"]
            or component.get("cpe") != expected["cpe"]
            or archive.get("filename") != expected["archive"]
            or digest.get("algorithm") != expected["algorithm"]
            or digest.get("value") != expected["digest"]
            or licence.get("spdx") != expected["license"]
        ):
            _fail(f"runtime source {name} identity mismatch")


def _validate_component_sbom(path: Path) -> None:
    document = _json(path)
    if not isinstance(document, dict) or document.get("spdxVersion") != "SPDX-2.3":
        _fail("runtime component SBOM is invalid")
    packages = document.get("packages")
    if not isinstance(packages, list) or len(packages) != len(EXPECTED_COMPONENTS):
        _fail("runtime component SBOM has unexpected packages")
    observed: dict[str, dict[str, object]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            _fail("runtime component SBOM package is invalid")
        name = package["name"]
        if name in observed:
            _fail("runtime component SBOM repeats a package")
        observed[name] = package
    if set(observed) != set(EXPECTED_COMPONENTS):
        _fail("runtime component SBOM has unexpected packages")
    for name, expected in EXPECTED_COMPONENTS.items():
        package = observed[name]
        references = package.get("externalRefs")
        if not isinstance(references, list):
            _fail(f"runtime component SBOM {name} references are invalid")
        locators = {
            reference.get("referenceType"): reference.get("referenceLocator")
            for reference in references
            if isinstance(reference, dict)
        }
        if (
            package.get("versionInfo") != expected["version"]
            or package.get("licenseDeclared") != expected["license"]
            or locators.get("purl") != expected["purl"]
            or locators.get("cpe23Type") != expected["cpe"]
        ):
            _fail(f"runtime component SBOM {name} identity mismatch")


def _validate_component_scan(path: Path) -> None:
    document = _json(path)
    if not isinstance(document, dict) or not isinstance(document.get("matches"), list):
        _fail("runtime component scan is invalid")
    source = document.get("source")
    descriptor = document.get("descriptor")
    if not isinstance(source, dict) or not isinstance(descriptor, dict):
        _fail("runtime component scan is invalid")
    target = source.get("target")
    configuration = descriptor.get("configuration")
    database = descriptor.get("db")
    if (
        source.get("type") != "sbom-file"
        or not isinstance(target, str)
        or not target.endswith("/runtime-components.spdx.json")
        or descriptor.get("name") != "grype"
        or descriptor.get("version") != "0.107.0"
        or not isinstance(configuration, dict)
        or not isinstance(configuration.get("match"), dict)
        or not isinstance(configuration["match"].get("stock"), dict)
        or configuration["match"]["stock"].get("using-cpes") is not True
        or not isinstance(database, dict)
        or not isinstance(database.get("status"), dict)
        or database["status"].get("valid") is not True
    ):
        _fail("runtime component scan is invalid")


def _validate_source_manifest(runtime_sources: Path, evidence_manifest: Path) -> None:
    runtime_manifest = _regular_bytes(runtime_sources / "SOURCE-MANIFEST.json")
    if runtime_manifest != _regular_bytes(evidence_manifest):
        _fail("source manifest evidence mismatch")
    try:
        document = json.loads(runtime_manifest)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidateValidationError("source manifest must be valid JSON") from error
    if (
        not isinstance(document, dict)
        or set(document) != {"schemaVersion", "digestAlgorithm", "files"}
        or document.get("schemaVersion") != 1
        or document.get("digestAlgorithm") != "sha256"
        or not isinstance(document.get("files"), list)
    ):
        _fail("source manifest is invalid")
    expected_paths = EXPECTED_RUNTIME_SOURCE_FILES - {"SOURCE-MANIFEST.json"}
    entries: dict[str, dict[str, object]] = {}
    for entry in document["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            _fail("source manifest entry is invalid")
        path = entry.get("path")
        if not isinstance(path, str) or path in entries:
            _fail("source manifest entry is invalid")
        entries[path] = entry
    if set(entries) != expected_paths:
        _fail("source manifest has an unexpected file set")
    for name, entry in entries.items():
        content = _regular_bytes(runtime_sources / name)
        if (
            entry.get("size") != len(content)
            or entry.get("sha256") != hashlib.sha256(content).hexdigest()
        ):
            _fail(f"source manifest mismatch: {name}")


def _validate_source(
    evidence: Path,
    runtime_sources: Path,
    component_scan: Path,
) -> str:
    _validate_exact_directory(evidence, EXPECTED_SOURCE_EVIDENCE_FILES, "source evidence")
    _validate_exact_directory(runtime_sources, EXPECTED_RUNTIME_SOURCE_FILES, "runtime source")
    source_digest = _digest_text(evidence / "source-artifact-digest.txt", "source artifact digest")
    source_reference = _text(evidence / "source-artifact-reference.txt")
    if not source_reference.endswith("\n") or "\n" in source_reference[:-1]:
        _fail("invalid source artifact reference evidence")
    match = SOURCE_REFERENCE.fullmatch(source_reference[:-1])
    if match is None or match.group(1) != source_digest:
        _fail("source artifact reference mismatch")
    manifest_bytes = _regular_bytes(evidence / "source-artifact-manifest.json")
    if f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}" != source_digest:
        _fail("source artifact manifest digest mismatch")
    try:
        artifact_manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidateValidationError("source artifact manifest must be valid JSON") from error
    if not isinstance(artifact_manifest, dict) or artifact_manifest.get("schemaVersion") != 2:
        _fail("source artifact manifest is invalid")

    _validate_source_manifest(runtime_sources, evidence / "source-manifest.json")
    component_bytes = _regular_bytes(runtime_sources / "runtime-components.spdx.json")
    if component_bytes != _regular_bytes(evidence / "runtime-components.spdx.json"):
        _fail("runtime component SBOM evidence mismatch")
    vex_bytes = _regular_bytes(runtime_sources / "runtime-components.openvex.json")
    if vex_bytes != _regular_bytes(evidence / "runtime-components.openvex.json"):
        _fail("runtime component VEX evidence mismatch")
    _validate_source_contract(runtime_sources)
    _validate_component_sbom(runtime_sources / "runtime-components.spdx.json")
    _validate_component_scan(component_scan)
    verification = _json(evidence / "source-attestation-verification.json")
    if not isinstance(verification, (dict, list)) or not verification:
        _fail("source attestation verification is invalid")
    bundle_lines = _text(evidence / "source-attestation.jsonl").splitlines()
    try:
        bundles = [json.loads(line) for line in bundle_lines]
    except json.JSONDecodeError as error:
        raise CandidateValidationError("source attestation bundle is invalid") from error
    if not bundles or any(not isinstance(bundle, dict) or not bundle for bundle in bundles):
        _fail("source attestation bundle is invalid")
    return source_reference[:-1]


def _validate_exact_directory(
    directory: Path,
    expected_files: frozenset[str],
    label: str,
) -> None:
    try:
        metadata = directory.lstat()
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise CandidateValidationError(f"{label} directory cannot be read") from error
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail(f"{label} path must be a directory")
    if {entry.name for entry in entries} != expected_files:
        _fail(f"{label} directory does not contain the exact release set")
    for entry in entries:
        _regular_bytes(entry)


def _validate_directory(evidence: Path) -> None:
    _validate_exact_directory(evidence, EXPECTED_FILES, "candidate evidence")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--source-evidence-directory", required=True, type=Path)
    parser.add_argument("--runtime-sources", required=True, type=Path)
    parser.add_argument("--component-scan", required=True, type=Path)
    parser.add_argument("--current-context-manifest", required=True, type=Path)
    parser.add_argument("--action-manifest", required=True, type=Path)
    parser.add_argument("--expected-context-digest", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate immutable candidate evidence and the final reviewed source context."""
    arguments = _parser().parse_args(argv)
    if DIGEST.fullmatch(arguments.expected_context_digest) is None:
        sys.stderr.write("candidate evidence error: invalid expected context digest\n")
        return 1
    if DIGEST.fullmatch(arguments.expected_image_digest) is None:
        sys.stderr.write("candidate evidence error: invalid expected image digest\n")
        return 1
    try:
        _validate_directory(arguments.evidence_directory)
        _validate_source(
            arguments.source_evidence_directory,
            arguments.runtime_sources,
            arguments.component_scan,
        )
        _validate_context(
            arguments.evidence_directory,
            arguments.current_context_manifest,
            arguments.expected_context_digest,
        )
        _validate_image(arguments.evidence_directory, arguments.expected_image_digest)
        _validate_action_manifest(arguments.action_manifest, arguments.expected_image_digest)
    except (CandidateValidationError, OSError) as error:
        sys.stderr.write(f"candidate evidence error: {error}\n")
        return 1
    sys.stdout.write("candidate evidence: validated exact reviewed context, source, and image\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
